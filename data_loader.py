"""
data_loader.py
한국(KOSPI, KOSDAQ) 및 미국(S&P 500, NASDAQ) 증시의 배당주 데이터를 수집하고
투자 분석 지표, 시계열 주가 및 배당 이력, 서식 적용 엑셀 다운로드를 제공하는 모듈.
"""

import sys
# Python 3.12+ 및 Streamlit Cloud 환경에서 pykrx의 pkg_resources 모듈 임포트 에러 방지용 shim
try:
    import pkg_resources
except Exception:
    try:
        import setuptools.command
        import pkg_resources
    except Exception:
        import types
        pkg_mock = types.ModuleType("pkg_resources")
        pkg_mock.resource_filename = lambda *args, **kwargs: ""
        pkg_mock.resource_string = lambda *args, **kwargs: b""
        pkg_mock.Requirement = type("Requirement", (), {"parse": lambda s: s})
        pkg_mock.get_distribution = lambda *args, **kwargs: type("Dist", (), {"version": "1.0.0"})()
        sys.modules["pkg_resources"] = pkg_mock

import os
import io
import datetime
import pandas as pd
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# 1. KRX 계정 인증 설정
def init_krx_credentials():
    """00 API Key 디렉토리의 KRX 계정 파일, 환경변수 또는 Streamlit Secrets 확인"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            for id_key in ['KRX_ID', 'krx_id', 'krx-id', 'Krx_Id']:
                if id_key in st.secrets and st.secrets[id_key]:
                    os.environ['KRX_ID'] = str(st.secrets[id_key]).strip()
                    break
            for pw_key in ['KRX_PW', 'krx_pw', 'krx-pw', 'Krx_Pw']:
                if pw_key in st.secrets and st.secrets[pw_key]:
                    os.environ['KRX_PW'] = str(st.secrets[pw_key]).strip()
                    break
            for sec_name in ['krx', 'KRX', 'Krx']:
                if sec_name in st.secrets:
                    sec = st.secrets[sec_name]
                    if isinstance(sec, dict):
                        if 'id' in sec and not os.getenv('KRX_ID'):
                            os.environ['KRX_ID'] = str(sec['id']).strip()
                        if 'pw' in sec and not os.getenv('KRX_PW'):
                            os.environ['KRX_PW'] = str(sec['pw']).strip()
    except Exception:
        pass

    if not os.getenv('KRX_ID') or not os.getenv('KRX_PW'):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        api_key_path = os.path.join(parent_dir, "00 API Key", "KRX ID&PW.txt")
        if os.path.exists(api_key_path):
            try:
                with open(api_key_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ID :") or line.startswith("ID:"):
                            os.environ['KRX_ID'] = line.split(":", 1)[1].strip()
                        elif line.startswith("PW :") or line.startswith("PW:"):
                            os.environ['KRX_PW'] = line.split(":", 1)[1].strip()
            except Exception as e:
                print(f"KRX 인증 파일 읽기 오류: {e}")

init_krx_credentials()

# 라이브러리 안전 로딩
try:
    from pykrx import stock
    HAS_PYKRX = True
except Exception:
    stock = None
    HAS_PYKRX = False

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    yf = None
    HAS_YF = False

try:
    import FinanceDataReader as fdr
    HAS_FDR = True
except Exception:
    fdr = None
    HAS_FDR = False

from concurrent.futures import ThreadPoolExecutor

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
MASTER_FILE = os.path.join(CURRENT_DIR, "dividend_stocks_master.csv")

# 분기배당 실시하는 대표 국내 기업 목록
QUARTERLY_KR_STOCKS = {
    '005930', '005935', '000660', '005380', '000270', '055550', '105560', '086790',
    '316140', '017670', '030200', '032640', '034730', '005490', '036570', '035420',
    '051910', '012330', '003670'
}


def evaluate_dividend_safety(payout_ratio, div_yield, eps=1.0, market=""):
    """
    배당 안전성 평가 로직 (안전, 보통, 주의)
    """
    if pd.isna(payout_ratio) or payout_ratio is None:
        if eps is not None and eps <= 0:
            return "🔴 주의 (적자 배당)"
        return "🟡 보통"
    
    try:
        payout_ratio = float(payout_ratio)
    except Exception:
        return "🟡 보통"

    try:
        div_yield = float(div_yield)
    except Exception:
        div_yield = 0.0

    if payout_ratio > 100:
        return "🔴 주의 (과다 배당)"
    elif payout_ratio > 75 or div_yield > 12:
        return "🟡 보통 (고배당 주의)"
    elif 10 <= payout_ratio <= 75:
        return "🟢 안전 (안정적)"
    elif payout_ratio < 10:
        return "🟢 안전 (저성향)"
    return "🟡 보통"


def get_latest_business_date():
    """
    가장 최근 거래 완료된 영업일 YYYY-MM-DD 반환.
    한국 장 마감 시간(15:30) 및 일별 정산(16:00)을 고려:
    - 평일 16:00 이전에는 아직 당일 종가가 확정되지 않았으므로 '전일(또는 직전 평일)'을 기준일로 설정
    - 평일 16:00 이후에는 '당일'을 최신 영업일로 설정
    - 주말(토, 일)에는 '직전 금요일'을 최신 영업일로 설정
    """
    # 1. pykrx 연결 가능한 경우 최우선으로 거래소 최근 영업일 조회
    if HAS_PYKRX and stock:
        try:
            krx_day = stock.get_nearest_business_day_in_a_week()
            if krx_day and len(krx_day) == 8:
                return f"{krx_day[:4]}-{krx_day[4:6]}-{krx_day[6:]}"
        except Exception:
            pass

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)

    # 평일 16:00 이전이거나 주말이면 어제(또는 직전 평일)부터 탐색
    start_offset = 0 if (now_kst.weekday() < 5 and now_kst.hour >= 16) else 1

    for i in range(start_offset, start_offset + 10):
        d = now_kst - datetime.timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime('%Y-%m-%d')

    return (now_kst - datetime.timedelta(days=1)).strftime('%Y-%m-%d')


def update_market_data_for_date(target_date):
    """
    지정된 최신 기준일(target_date: YYYY-MM-DD)에 맞추어 4개 시장(KOSPI, KOSDAQ, S&P 500, NASDAQ)
    TOP 100 배당주 데이터를 수집 및 갱신하고 캐시와 마스터 파일에 동시 저장합니다.
    """
    clean_date = target_date.replace('-', '').strip()
    cache_path = os.path.join(CACHE_DIR, f"dividend_summary_{clean_date}.csv")
    print(f"[data_loader] {target_date} ({clean_date}) 기준 최신 시장 데이터 업데이트 시작...")
    df_parts = []

    # 1. 한국 시장 (KOSPI, KOSDAQ) - pykrx 펀더멘털 수집 후 포털 확정 종가 및 시가총액 2차 동기화
    if HAS_PYKRX and stock:
        for market_name in ['KOSPI', 'KOSDAQ']:
            try:
                fund = stock.get_market_fundamental_by_ticker(clean_date, market=market_name)
                cap = stock.get_market_cap_by_ticker(clean_date, market=market_name)
                sec = stock.get_market_sector_classifications(clean_date, market=market_name)

                df_kr = pd.DataFrame(index=fund.index)
                df_kr['티커'] = fund.index
                df_kr['종목명'] = sec['종목명'] if '종목명' in sec.columns else [stock.get_market_ticker_name(t) for t in fund.index]
                df_kr['시장'] = market_name
                df_kr['업종'] = sec['업종명'] if '업종명' in sec.columns else '기타'
                df_kr['현재가'] = cap['종가'].astype(float)
                df_kr['시가총액'] = cap['시가총액'].astype(float)
                df_kr['상장주식수'] = cap['상장주식수'].astype(float) if '상장주식수' in cap.columns else 0.0
                df_kr['배당금'] = fund['DPS'].astype(float)
                df_kr['배당수익률'] = fund['DIV'].astype(float)
                df_kr['EPS'] = fund['EPS'].astype(float)

                # 스팩 및 배당금 0 종목 제외
                df_kr = df_kr[~df_kr['종목명'].str.contains('스팩', na=False)]
                df_kr = df_kr[df_kr['배당수익률'] > 0]
                df_kr = df_kr[df_kr['배당금'] > 0]
                df_kr = df_kr[df_kr['시가총액'] >= 100_000_000]

                # 배당성향 1차 계산
                df_kr['배당성향'] = np.where(
                    (df_kr['EPS'] > 0) & (df_kr['배당금'] > 0),
                    np.round((df_kr['배당금'] / df_kr['EPS']) * 100, 2),
                    np.nan
                )

                # 배당수익률 기준 정렬 후 상위 120개 후보군 선별 (확정 종가 보정 후 최종 100개 확정)
                df_candidate = df_kr.sort_values(by='배당수익률', ascending=False).head(120).copy().reset_index(drop=True)
                cand_tickers = df_candidate['티커'].tolist()

                # 네이버 증권 공식 fchart API 직접 병렬 동기화 (네이버 실거래 확정 종가 100% 일치)
                import xml.etree.ElementTree as et
                import requests
                from requests.adapters import HTTPAdapter

                price_map_kr = {}
                session = requests.Session()
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
                session.mount('https://', adapter)

                def fetch_naver_portal_price(t_code):
                    try:
                        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={t_code}&timeframe=day&count=1&requestType=0"
                        r = session.get(url, timeout=1.5)
                        node = et.fromstring(r.text).find('.//item')
                        if node is not None:
                            val = float(node.get('data').split('|')[4])
                            if val > 0:
                                return t_code, val
                    except Exception:
                        pass
                    return t_code, None

                with ThreadPoolExecutor(max_workers=15) as executor:
                    fchart_res = list(executor.map(fetch_naver_portal_price, cand_tickers))

                for t_code, p_val in fchart_res:
                    if p_val is not None and p_val > 0:
                        price_map_kr[t_code] = p_val

                # 확정 종가 반영 및 시가총액/배당수익률 재계산
                for idx, row in df_candidate.iterrows():
                    sym = row['티커']
                    if sym in price_map_kr:
                        new_price = price_map_kr[sym]
                        shrs = row['상장주식수']
                        old_price = row['현재가']

                        df_candidate.at[idx, '현재가'] = new_price
                        # 시가총액 = 상장주식수 * 네이버 확정 종가
                        if shrs and shrs > 0:
                            df_candidate.at[idx, '시가총액'] = round(shrs * new_price, 0)
                        elif old_price and old_price > 0 and row['시가총액'] > 0:
                            df_candidate.at[idx, '시가총액'] = round(row['시가총액'] * (new_price / old_price), 0)

                        # 배당수익률 = (배당금 / 네이버 확정 종가) * 100
                        if row['배당금'] > 0 and new_price > 0:
                            df_candidate.at[idx, '배당수익률'] = round((row['배당금'] / new_price) * 100, 2)

                # 보정된 배당수익률 기준 재정렬 후 상위 100개 확정
                df_kr_final = df_candidate.sort_values(by='배당수익률', ascending=False).head(100).copy().reset_index(drop=True)
                df_kr_final['순위'] = range(1, len(df_kr_final) + 1)
                df_kr_final['배당주기'] = df_kr_final['티커'].apply(lambda t: '분기배당' if t in QUARTERLY_KR_STOCKS else '연배당')
                df_kr_final['배당안전성'] = [
                    evaluate_dividend_safety(p, y, e, market_name)
                    for p, y, e in zip(df_kr_final['배당성향'], df_kr_final['배당수익률'], df_kr_final['EPS'])
                ]
                df_kr_final['기준일'] = target_date

                cols = ['순위', '종목명', '티커', '시장', '업종', '시가총액', '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성', '기준일']
                df_kr_final = df_kr_final[cols]
                df_parts.append(df_kr_final)
                print(f"[{market_name}] {len(df_kr_final)}개 종목 최신화 및 포털 종가/시가총액 동기화 완료 (동기화: {len(price_map_kr)}/{len(cand_tickers)}, 기준일: {target_date})")
            except Exception as e_kr:
                print(f"[{market_name}] pykrx 수집 예외: {e_kr}")

    # 2. 미국 시장 (S&P 500, NASDAQ) - FDR 및 yfinance 병렬 종가 최신 동기화
    df_existing_master = pd.DataFrame()
    if os.path.exists(MASTER_FILE):
        try:
            df_existing_master = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
        except Exception:
            pass

    for us_market in ['S&P500', 'NASDAQ']:
        df_us_sub = pd.DataFrame()
        if not df_existing_master.empty and '시장' in df_existing_master.columns:
            df_us_sub = df_existing_master[df_existing_master['시장'] == us_market].copy()

        if not df_us_sub.empty:
            tickers = df_us_sub['티커'].tolist()
            price_map = {}

            def fetch_latest_us_price(sym):
                if HAS_FDR and fdr:
                    try:
                        s_dt = (pd.to_datetime(target_date) - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
                        e_dt = (pd.to_datetime(target_date) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                        df_p = fdr.DataReader(sym, s_dt, e_dt)
                        if not df_p.empty and 'Close' in df_p.columns:
                            c_series = df_p.loc[df_p.index <= pd.to_datetime(target_date), 'Close'].dropna()
                            if not c_series.empty:
                                return sym, float(c_series.iloc[-1])
                    except Exception:
                        pass
                return sym, None

            with ThreadPoolExecutor(max_workers=30) as executor:
                results = list(executor.map(fetch_latest_us_price, tickers))

            for sym, price in results:
                if price is not None and price > 0:
                    price_map[sym] = price

            # 최신 가격 반영 및 지표 재계산
            for idx, row in df_us_sub.iterrows():
                sym = row['티커']
                if sym in price_map:
                    new_p = price_map[sym]
                    old_p = row['현재가']
                    ratio = (new_p / old_p) if (old_p and old_p > 0) else 1.0
                    df_us_sub.at[idx, '현재가'] = round(new_p, 2)
                    if row['시가총액'] > 0:
                        df_us_sub.at[idx, '시가총액'] = round(row['시가총액'] * ratio, 2)
                    if row['배당금'] > 0:
                        df_us_sub.at[idx, '배당수익률'] = round((row['배당금'] / new_p) * 100, 2)
                    df_us_sub.at[idx, '배당안전성'] = evaluate_dividend_safety(
                        row.get('배당성향', np.nan),
                        df_us_sub.at[idx, '배당수익률'],
                        1.0,
                        us_market
                    )

            # 배당수익률 기준 재정렬 후 100개
            df_us_sub = df_us_sub.sort_values(by='배당수익률', ascending=False).head(100).copy().reset_index(drop=True)
            df_us_sub['순위'] = range(1, len(df_us_sub) + 1)
            df_us_sub['기준일'] = target_date
            cols = ['순위', '종목명', '티커', '시장', '업종', '시가총액', '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성', '기준일']
            df_us_sub = df_us_sub[cols]
            df_parts.append(df_us_sub)
            print(f"[{us_market}] {len(df_us_sub)}개 종목 갱신 완료 (가격 반영: {len(price_map)}/{len(tickers)})")

    # 3. 통합 DataFrame 병합 및 저장
    if df_parts:
        df_all = pd.concat(df_parts, ignore_index=True)
        if len(df_all) >= 300:
            # 캐시 파일 저장
            df_all.to_csv(cache_path, index=False, encoding='utf-8-sig')
            # 마스터 파일 동시 저장
            df_all.to_csv(MASTER_FILE, index=False, encoding='utf-8-sig')
            print(f"[data_loader] {target_date} 데이터 저장 완료: 총 {len(df_all)}개 종목")
            return df_all

    return pd.DataFrame()


def load_market_data(force_refresh=False):
    """
    한국 및 미국 4개 시장(KOSPI, KOSDAQ, S&P500, NASDAQ)의 배당주 데이터를 로드합니다.
    - 당일 최신 기준일 캐시 파일이 있으면 0.05초 즉시 반환.
    - 캐시 파일이 없거나 force_refresh=True일 경우 최신 기준일 데이터로 수집/갱신.
    반환값: (df_all, target_date_str)
    """
    date_display = get_latest_business_date()
    today_clean = date_display.replace('-', '')
    cache_path = os.path.join(CACHE_DIR, f"dividend_summary_{today_clean}.csv")

    # 1. 당일 캐시 파일 확인 (force_refresh=False인 경우 즉시 반환)
    if not force_refresh and os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={'티커': str}, encoding='utf-8-sig')
            if not df.empty and len(df) >= 300:
                actual_date = str(df['기준일'].iloc[0]) if ('기준일' in df.columns and pd.notna(df['기준일'].iloc[0])) else date_display
                return df, actual_date
        except Exception as e:
            print(f"당일 캐시 로드 실패: {e}")

    # 2. 캐시 파일이 없거나 강제 갱신(force_refresh=True) 요청 시: 최신 데이터 수집 및 갱신
    try:
        df_updated = update_market_data_for_date(date_display)
        if not df_updated.empty and len(df_updated) >= 300:
            actual_date = str(df_updated['기준일'].iloc[0]) if ('기준일' in df_updated.columns and pd.notna(df_updated['기준일'].iloc[0])) else date_display
            return df_updated, actual_date
    except Exception as e:
        print(f"최신 데이터 수집 업데이트 실패: {e}")

    # 3. 폴백: 마스터 파일 확인 (최신 수집이 실패한 비상 상황에서만 사용)
    if os.path.exists(MASTER_FILE):
        try:
            df = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
            if not df.empty and len(df) >= 300:
                actual_date = str(df['기준일'].iloc[0]) if ('기준일' in df.columns and pd.notna(df['기준일'].iloc[0])) else date_display
                return df, actual_date
        except Exception as e:
            print(f"마스터 파일 로드 실패: {e}")

    return pd.DataFrame(), date_display


def load_stock_history_and_dividends(ticker, market, months=12, latest_date=None, latest_price=None, *args, **kwargs):
    """
    선택된 종목의 시계열 주가(일별 종가, 이동평균선) 및 역대 배당금 지급 내역(연도별 DPS) 수집.
    - 1차: 한국 주식은 pykrx 실시간 OHLCV 우선 조회 -> 2차: yfinance 글로벌 폴백
    - 3차: 타임존 완전 제거로 Plotly UTC 변환 시 하루 전으로 표시되는 버그 원천 차단
    - 4차: 테이블의 최신 검증 종가(latest_price, latest_date)와 동기화하여 시계열 데이터 누락/지연 원천 방지
    - 5차: Python 3.14 및 tz-aware/naive 비교 예외(TypeError) 원천 차단
    반환값:
      df_price: DataFrame (Index: Date, '종가', 'MA20', 'MA60')
      df_div_annual: DataFrame ('연도', 'DPS', '배당성장률(%)')
    """
    df_price = pd.DataFrame()
    df_div_annual = pd.DataFrame()

    try:
        end_date_str = get_latest_business_date()
        if latest_date:
            clean_date = str(latest_date).replace('-', '').strip()
            if len(clean_date) == 8:
                clean_end = end_date_str.replace('-', '')
                if clean_date > clean_end:
                    end_date_str = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"

        start_dt = datetime.datetime.strptime(end_date_str, "%Y-%m-%d") - datetime.timedelta(days=int(months * 30.5))
        start_date_str = start_dt.strftime("%Y-%m-%d")

        # 1. 한국 주식인 경우 pykrx OHLCV 우선 시도
        if market in ['KOSPI', 'KOSDAQ'] and HAS_PYKRX and stock:
            try:
                s_d = start_date_str.replace('-', '')
                e_d = end_date_str.replace('-', '')
                df_krx = stock.get_market_ohlcv_by_date(s_d, e_d, str(ticker).zfill(6))
                if not df_krx.empty and '종가' in df_krx.columns and len(df_krx) >= 5:
                    df_price = pd.DataFrame(index=df_krx.index)
                    df_price['종가'] = df_krx['종가'].astype(float).values
            except Exception as e:
                print(f"pykrx OHLCV 수집 실패 (yfinance 폴백 가동): {e}")

        # 2. yfinance 시도 (미국 주식 및 한국 주식 폴백)
        yf_symbol = None
        if market == 'KOSPI':
            yf_symbol = f"{str(ticker).zfill(6)}.KS"
        elif market == 'KOSDAQ':
            yf_symbol = f"{str(ticker).zfill(6)}.KQ"
        else:
            yf_symbol = str(ticker).replace('.', '-')

        if HAS_YF and yf and yf_symbol:
            try:
                t = yf.Ticker(yf_symbol)

                # 주가 데이터가 아직 없으면 yfinance에서 로드
                if df_price.empty:
                    period_str = f"{months}mo" if months <= 36 else "5y"
                    hist = t.history(period=period_str)
                    if not hist.empty and 'Close' in hist.columns:
                        df_price = pd.DataFrame(index=hist.index)
                        df_price['종가'] = hist['Close'].values

                # 배당금 이력 로드
                divs = t.dividends
                if not divs.empty:
                    if hasattr(divs.index, 'tz') and divs.index.tz is not None:
                        divs.index = divs.index.tz_localize(None)
                    divs.index = pd.to_datetime(divs.index)
                    divs_annual = divs.groupby(divs.index.year).sum()
                    current_year = datetime.datetime.now().year
                    divs_annual = divs_annual[divs_annual.index >= (current_year - 6)]
                    
                    if len(divs_annual) > 0:
                        df_div_annual = pd.DataFrame({
                            '연도': divs_annual.index.astype(str),
                            'DPS': divs_annual.values
                        })
                        growth_rates = [np.nan]
                        for i in range(1, len(df_div_annual)):
                            prev = df_div_annual.loc[i - 1, 'DPS']
                            curr = df_div_annual.loc[i, 'DPS']
                            if prev > 0:
                                rate = round(((curr - prev) / prev) * 100, 2)
                            else:
                                rate = np.nan
                            growth_rates.append(rate)
                        df_div_annual['배당성장률(%)'] = growth_rates
            except Exception as e:
                print(f"{yf_symbol} yfinance 로드 실패: {e}")

        # 2-2. 주가 데이터가 비어있으면 FinanceDataReader로 시계열 폴백 수집
        if df_price.empty and HAS_FDR and fdr:
            try:
                fdr_sym = str(ticker)
                end_fdr = (pd.to_datetime(end_date_str) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                df_fdr = fdr.DataReader(fdr_sym, start_date_str, end_fdr)
                if not df_fdr.empty and 'Close' in df_fdr.columns:
                    df_fdr = df_fdr[df_fdr.index <= pd.to_datetime(end_date_str)]
                    if not df_fdr.empty:
                        df_price = pd.DataFrame(index=df_fdr.index)
                        df_price['종가'] = df_fdr['Close'].astype(float).values
            except Exception as e_fdr:
                print(f"{ticker} FDR 히스토리 폴백 실패: {e_fdr}")

        if df_price.empty:
            return pd.DataFrame(), df_div_annual

        # 3. 타임존 제거 및 YYYY-MM-DD 날짜로 완전 정규화
        try:
            if hasattr(df_price.index, 'tz') and df_price.index.tz is not None:
                df_price.index = df_price.index.tz_localize(None)
            df_price.index = pd.to_datetime([d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10] for d in df_price.index])
        except Exception as ex_tz:
            print(f"인덱스 타임존 정규화 예외 무시: {ex_tz}")

        # 4. 테이블의 최신 검증 종가 데이터와 시계열 강제 동기화 (야후파이낸스 한국 주식 반영 지연 100% 방어)
        if latest_date and latest_price is not None and not df_price.empty:
            try:
                p_val = float(latest_price)
                if p_val > 0:
                    clean_dt_str = str(latest_date).strip()
                    if len(clean_dt_str) == 8 and clean_dt_str.isdigit():
                        clean_dt_str = f"{clean_dt_str[:4]}-{clean_dt_str[4:6]}-{clean_dt_str[6:]}"

                    target_dt = pd.to_datetime(clean_dt_str)
                    max_dt = df_price.index.max()

                    if pd.notna(max_dt):
                        if target_dt > max_dt:
                            new_row = pd.DataFrame({"종가": [p_val]}, index=[target_dt])
                            df_price = pd.concat([df_price, new_row])
                        elif target_dt in df_price.index:
                            df_price.loc[target_dt, "종가"] = p_val
                        else:
                            new_row = pd.DataFrame({"종가": [p_val]}, index=[target_dt])
                            df_price = pd.concat([df_price, new_row])
            except Exception as ex_sync:
                print(f"최신 종가 동기화 예외: {ex_sync}")

        # 중복 인덱스 제거 및 정렬
        df_price = df_price[~df_price.index.duplicated(keep='last')].sort_index()

        # 5. 이동평균선 재계산
        df_price['MA20'] = df_price['종가'].rolling(window=20, min_periods=1).mean()
        df_price['MA60'] = df_price['종가'].rolling(window=60, min_periods=1).mean()

        return df_price, df_div_annual

    except Exception as e:
        print(f"load_stock_history_and_dividends 최상위 예외 방어: {e}")
        return pd.DataFrame(), pd.DataFrame()


def create_excel_download(df_export, market_name):
    """
    선택된 시장의 TOP 100 배당주 데이터와 통화 서식을 적용한 엑셀 바이너리 생성
    """
    output = io.BytesIO()
    is_korean = market_name in ['KOSPI', 'KOSDAQ']

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = f"{market_name}_배당주_TOP100"
        df_export.to_excel(writer, sheet_name=sheet_name, index=False)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # 헤더 스타일
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="맑은 고딕", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # 데이터 셀 서식
        data_font = Font(name="맑은 고딕", size=10)
        border_thin = Side(style='thin', color="CBD5E1")
        cell_border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)

        # 헤더 서식 적용
        for col_idx in range(1, len(df_export.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = cell_border

        # 데이터 행 서식 적용
        for row_idx in range(2, len(df_export) + 2):
            for col_idx, col_name in enumerate(df_export.columns, start=1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.font = data_font
                cell.border = cell_border

                if col_name in ["순위", "코드/티커", "시장", "배당주기", "배당안전성", "배당 안정성"]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    if col_name == "순위":
                        cell.number_format = '#,##0'
                        # 순위 열은 다른 열을 정렬/필터 토글해도 항상 1부터 100까지 고정 유지되도록 동적 수식 적용
                        cell.value = f"=ROW()-1"
                    elif col_name == "코드/티커":
                        cell.number_format = '@'
                elif col_name in ["종목명", "업종"]:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_name in ["현재가", "배당금"]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if is_korean:
                        cell.number_format = '#,##0'
                    else:
                        cell.number_format = '$#,##0.00'
                elif col_name in ["시가총액"]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if is_korean:
                        cell.number_format = '#,##0'
                    else:
                        cell.number_format = '$#,##0'
                elif col_name in ["배당수익률", "배당수익률(%)", "배당성향"]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = '0.00'
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        # 자동 필터 (오름차순/내림차순 정렬 토글): 순위(A열)는 제외하고 B열부터 적용
        end_col_letter = get_column_letter(len(df_export.columns))
        worksheet.auto_filter.ref = f"B1:{end_col_letter}{len(df_export) + 1}"

        # 열 너비 자동 조정
        for col in worksheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or '')
                max_len = max(max_len, len(val.encode('euc-kr', errors='ignore')))
            worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

        worksheet.row_dimensions[1].height = 28

    return output.getvalue()
