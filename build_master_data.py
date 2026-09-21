"""
build_master_data.py
KOSPI, KOSDAQ, S&P 500, NASDAQ 4개 시장의 배당수익률 기준 TOP 100 마스터 데이터를 수집하고
dividend_stocks_master.csv 파일로 생성하는 스크립트.
"""

import os
import sys
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np

# UTF-8 출력 인코딩 설정
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_FILE = os.path.join(CURRENT_DIR, "dividend_stocks_master.csv")
CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 1. KRX 인증 설정
def init_krx_credentials():
    if not os.getenv('KRX_ID') or not os.getenv('KRX_PW'):
        parent_dir = os.path.dirname(CURRENT_DIR)
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
                print(f"KRX 인증 파일 로드 실패: {e}")

init_krx_credentials()

# 2. 라이브러리 로드
try:
    from pykrx import stock
    HAS_PYKRX = True
except Exception as e:
    stock = None
    HAS_PYKRX = False
    print(f"pykrx 로드 실패: {e}")

import yfinance as yf
try:
    import FinanceDataReader as fdr
except Exception:
    fdr = None

# 분기배당 실시하는 대표 국내 기업 목록
QUARTERLY_KR_STOCKS = {
    '005930', '005935', '000660', '005380', '000270', '055550', '105560', '086790',
    '316140', '017670', '030200', '032640', '034730', '005490', '036570', '035420',
    '051910', '012330', '003670'
}

def get_latest_business_date() -> str:
    """
    가장 최근 거래 완료된 영업일 YYYY-MM-DD 반환.
    한국 장 마감 시간(15:30) 및 일별 정산(16:00)을 고려:
    - 평일 16:00 KST 이전에는 아직 당일 종가가 확정되지 않았으므로 '직전 평일'을 기준일로 설정
    - 평일 16:00 KST 이후에는 '당일'을 최신 영업일로 설정
    - 주말(토, 일)에는 '직전 금요일'을 최신 영업일로 설정
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)
    start_offset = 0 if (now_kst.weekday() < 5 and now_kst.hour >= 16) else 1

    for i in range(start_offset, start_offset + 10):
        d = now_kst - datetime.timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime('%Y-%m-%d')
    return (now_kst - datetime.timedelta(days=1)).strftime('%Y-%m-%d')


def get_latest_krx_date(target_date: str = None) -> str:
    """YYYYMMDD 포맷의 가장 최근 마감 영업일 반환 (pykrx 검증 지원)"""
    if not target_date:
        target_date = get_latest_business_date()
    clean_date = target_date.replace('-', '').strip()

    if HAS_PYKRX and stock:
        try:
            krx_day = stock.get_nearest_business_day_in_a_week(date=clean_date)
            if krx_day and len(krx_day) == 8 and krx_day <= clean_date:
                return krx_day
        except Exception:
            pass
    return clean_date


def evaluate_dividend_safety(payout_ratio, div_yield, eps, market):
    """
    배당 안전성 평가 로직 (정상, 보통, 주의)
    """
    if pd.isna(payout_ratio) or payout_ratio is None:
        if eps <= 0:
            return "🔴 주의 (적자 배당)"
        return "🟡 보통"
    
    if payout_ratio > 100:
        return "🔴 주의 (과다 배당)"
    elif payout_ratio > 75 or div_yield > 12:
        return "🟡 보통 (고배당 주의)"
    elif 10 <= payout_ratio <= 75:
        return "🟢 안전 (안정적)"
    elif payout_ratio < 10:
        return "🟢 안전 (저성향)"
    return "🟡 보통"


def build_kr_market(market_name="KOSPI", target_date: str = None):
    """
    KOSPI 또는 KOSDAQ 배당 상위 100개 종목 수집.
    target_date: 영업일 기준일 (예: '2026-09-21'). 미지정 시 get_latest_business_date() 사용.
    """
    if not target_date:
        target_date = get_latest_business_date()

    print(f"[{market_name}] 데이터 수집 시작 (기준일: {target_date})...")
    date = get_latest_krx_date(target_date)
    print(f"[{market_name}] KRX 공식 영업일: {date}")

    if not HAS_PYKRX or not stock:
        print(f"pykrx를 사용할 수 없습니다.")
        return pd.DataFrame()

    fund = stock.get_market_fundamental_by_ticker(date, market=market_name)
    cap = stock.get_market_cap_by_ticker(date, market=market_name)
    sec = stock.get_market_sector_classifications(date, market=market_name)

    df = pd.DataFrame(index=fund.index)
    df['티커'] = fund.index
    df['종목명'] = sec['종목명'] if '종목명' in sec.columns else [stock.get_market_ticker_name(t) for t in fund.index]
    df['시장'] = market_name
    df['업종'] = sec['업종명'] if '업종명' in sec.columns else '기타'
    df['현재가'] = cap['종가'].astype(float)
    df['시가총액'] = cap['시가총액'].astype(float)
    df['상장주식수'] = cap['상장주식수'].astype(float) if '상장주식수' in cap.columns else 0.0
    df['배당금'] = fund['DPS'].astype(float)
    df['배당수익률'] = fund['DIV'].astype(float)
    df['EPS'] = fund['EPS'].astype(float)

    # 스팩 및 배당금 0 종목 제외
    df = df[~df['종목명'].str.contains('스팩', na=False)]
    df = df[df['배당수익률'] > 0]
    df = df[df['배당금'] > 0]
    df = df[df['시가총액'] >= 100_000_000] # 최소 1억원 이상

    # 배당성향 1차 계산
    df['배당성향'] = np.where(
        (df['EPS'] > 0) & (df['배당금'] > 0),
        np.round((df['배당금'] / df['EPS']) * 100, 2),
        np.nan
    )

    # 배당수익률 기준 정렬 후 상위 120개 후보군 선별 (확정 종가 보정 후 최종 100개 확정)
    df_candidate = df.sort_values(by='배당수익률', ascending=False).head(120).copy().reset_index(drop=True)
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
    df_final = df_candidate.sort_values(by='배당수익률', ascending=False).head(100).copy().reset_index(drop=True)
    df_final['순위'] = range(1, len(df_final) + 1)
    df_final['배당주기'] = df_final['티커'].apply(lambda t: '분기배당' if t in QUARTERLY_KR_STOCKS else '연배당')
    df_final['배당안전성'] = [
        evaluate_dividend_safety(p, y, e, market_name)
        for p, y, e in zip(df_final['배당성향'], df_final['배당수익률'], df_final['EPS'])
    ]
    date_hyphen = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    df_final['기준일'] = date_hyphen

    # 불필요 컬럼 정리
    df_final = df_final[[
        '순위', '종목명', '티커', '시장', '업종', '시가총액',
        '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성', '기준일'
    ]]
    print(f"[{market_name}] 수집 완료: {len(df_final)}개 종목 (포털 종가 동기화: {len(price_map_kr)}/{len(cand_tickers)})")
    return df_final


def build_us_market_sp500(target_date: str = None):
    """
    S&P 500 종목 중 배당수익률 기준 상위 100개 종목 수집.
    target_date: 영업일 기준일 (예: '2026-09-21'). 미지정 시 get_latest_business_date() 사용.
    """
    if not target_date:
        target_date = get_latest_business_date()

    print(f"[S&P500] 종목 리스트 수집 중 (기준일: {target_date})...")
    symbols_data = []
    if fdr is not None:
        try:
            sp500_listing = fdr.StockListing('S&P500')
            for _, row in sp500_listing.iterrows():
                sym = str(row['Symbol']).replace('.', '-')
                name = str(row.get('Name', sym))
                sector = str(row.get('Sector', '기타'))
                symbols_data.append((sym, name, sector))
        except Exception:
            pass

    if not symbols_data:
        try:
            import requests, io
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=10)
            df_wiki = pd.read_html(io.StringIO(resp.text))[0]
            for _, row in df_wiki.iterrows():
                sym = str(row['Symbol']).replace('.', '-')
                name = str(row.get('Security', sym))
                sector = str(row.get('GICS Sector', '기타'))
                symbols_data.append((sym, name, sector))
        except Exception as e:
            print(f"Wikipedia S&P500 로드 실패: {e}")

    print(f"[S&P500] 총 {len(symbols_data)}개 종목 yfinance 병렬 데이터 수집 시작...")
    records = []

    def fetch_one(item):
        sym, name, sector = item
        try:
            t = yf.Ticker(sym)
            inf = t.info
            price = inf.get('currentPrice') or inf.get('regularMarketPrice') or inf.get('previousClose')
            d_rate = inf.get('dividendRate') or inf.get('trailingAnnualDividendRate')
            d_yield = inf.get('dividendYield') or inf.get('trailingAnnualDividendYield')
            mcap = inf.get('marketCap')
            payout = inf.get('payoutRatio')
            sec = inf.get('sector') or sector
            s_name = inf.get('shortName') or name

            if not price or price <= 0:
                return None
            if not d_rate or d_rate <= 0:
                # 배당률이 없으면 배당 미지급주
                if not d_yield or d_yield <= 0:
                    return None
                d_rate = (d_yield if d_yield < 1 else d_yield / 100.0) * price

            # 배당수익률 백분율(%) 계산 통일
            if d_yield is not None and d_yield > 0:
                calc_yield = d_yield * 100 if d_yield < 1.0 else d_yield
            else:
                calc_yield = (d_rate / price) * 100

            calc_yield = round(float(calc_yield), 2)
            if calc_yield <= 0.2: # 0.2% 이하는 제외
                return None

            # 배당성향 백분율(%) 계산 통일
            if payout is not None and payout > 0:
                calc_payout = round(payout * 100 if payout < 2.0 else payout, 2)
            else:
                calc_payout = np.nan

            # 월배당 대표 리츠 식별
            monthly_us = {'O', 'STAG', 'MAIN', 'AGNC', 'EPR', 'LAND', 'ADC'}
            freq = '월배당' if sym in monthly_us else '분기배당'
            safety = evaluate_dividend_safety(calc_payout, calc_yield, 1.0, "S&P500")

            return {
                '종목명': s_name,
                '티커': sym,
                '시장': 'S&P500',
                '업종': sec,
                '시가총액': float(mcap) if mcap else 0.0,
                '현재가': round(float(price), 2),
                '배당금': round(float(d_rate), 2),
                '배당수익률': calc_yield,
                '배당성향': calc_payout,
                '배당주기': freq,
                '배당안전성': safety
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_one, symbols_data))

    records = [r for r in results if r is not None]
    df = pd.DataFrame(records)
    print(f"[S&P500] 배당 지급 종목 수: {len(df)}개")

    if df.empty or '배당수익률' not in df.columns or len(df) == 0:
        print("[S&P500] yfinance 수집 실패 또는 호출 한도 초과. 기존 마스터 데이터에서 폴백 로드합니다.")
        if os.path.exists(MASTER_FILE):
            df_m = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
            df_sp = df_m[df_m['시장'] == 'S&P500'].copy().reset_index(drop=True)
            if not df_sp.empty:
                return df_sp
        return pd.DataFrame(columns=['순위', '종목명', '티커', '시장', '업종', '시가총액', '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성'])

    # 배당수익률 기준 내림차순 정렬 후 100개
    df = df.sort_values(by='배당수익률', ascending=False).head(100).copy().reset_index(drop=True)
    df['순위'] = range(1, len(df) + 1)
    df['기준일'] = target_date
    df = df[[
        '순위', '종목명', '티커', '시장', '업종', '시가총액',
        '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성', '기준일'
    ]]
    return df


def build_us_market_nasdaq(target_date: str = None):
    """
    NASDAQ 상장 종목 중 배당수익률 기준 상위 100개 종목 수집.
    target_date: 영업일 기준일 (예: '2026-09-21'). 미지정 시 get_latest_business_date() 사용.
    """
    if not target_date:
        target_date = get_latest_business_date()

    print(f"[NASDAQ] 대표 고배당 및 우량 종목 리스트 선별 (기준일: {target_date})...")
    # 대표적인 NASDAQ 배당 지급 종목 풀 (NASDAQ 100 + 주요 NASDAQ 배당주)
    nasdaq_top_tickers = [
        ('CSCO', 'Cisco Systems', 'Technology'),
        ('PEP', 'PepsiCo', 'Consumer Defensive'),
        ('TXN', 'Texas Instruments', 'Technology'),
        ('QCOM', 'Qualcomm', 'Technology'),
        ('GILD', 'Gilead Sciences', 'Healthcare'),
        ('AMGN', 'Amgen', 'Healthcare'),
        ('INTC', 'Intel Corporation', 'Technology'),
        ('CMCSA', 'Comcast Corporation', 'Communication Services'),
        ('KDP', 'Keurig Dr Pepper', 'Consumer Defensive'),
        ('PAYX', 'Paychex', 'Industrials'),
        ('FAST', 'Fastenal', 'Industrials'),
        ('ADP', 'Automatic Data Processing', 'Industrials'),
        ('CTAS', 'Cintas Corporation', 'Industrials'),
        ('EXPE', 'Expedia Group', 'Consumer Cyclical'),
        ('BKNG', 'Booking Holdings', 'Consumer Cyclical'),
        ('AVGO', 'Broadcom', 'Technology'),
        ('ADI', 'Analog Devices', 'Technology'),
        ('NXPI', 'NXP Semiconductors', 'Technology'),
        ('MCHP', 'Microchip Technology', 'Technology'),
        ('KLAC', 'KLA Corporation', 'Technology'),
        ('LRCX', 'Lam Research', 'Technology'),
        ('BIIB', 'Biogen', 'Healthcare'),
        ('VRSK', 'Verisk Analytics', 'Industrials'),
        ('PCAR', 'PACCAR', 'Industrials'),
        ('DLTR', 'Dollar Tree', 'Consumer Defensive'),
        ('ROST', 'Ross Stores', 'Consumer Cyclical'),
        ('ORLY', 'O\'Reilly Automotive', 'Consumer Cyclical'),
        ('EBAY', 'eBay', 'Consumer Cyclical'),
        ('CHTR', 'Charter Communications', 'Communication Services'),
        ('EA', 'Electronic Arts', 'Communication Services'),
        ('NTES', 'NetEase', 'Communication Services'),
        ('REGN', 'Regeneron Pharmaceuticals', 'Healthcare'),
        ('VRTX', 'Vertex Pharmaceuticals', 'Healthcare'),
        ('WBD', 'Warner Bros. Discovery', 'Communication Services'),
        ('SBUX', 'Starbucks', 'Consumer Cyclical'),
        ('MDLZ', 'Mondelez International', 'Consumer Defensive'),
        ('KHC', 'Kraft Heinz', 'Consumer Defensive'),
        ('CSX', 'CSX Corporation', 'Industrials'),
        ('HON', 'Honeywell', 'Industrials'),
        ('MAR', 'Marriott International', 'Consumer Cyclical'),
        ('ABNB', 'Airbnb', 'Consumer Cyclical'),
        ('PANW', 'Palo Alto Networks', 'Technology'),
        ('FTNT', 'Fortinet', 'Technology'),
        ('CRWD', 'CrowdStrike', 'Technology'),
        ('SNPS', 'Synopsys', 'Technology'),
        ('CDNS', 'Cadence Design Systems', 'Technology'),
        ('ANSS', 'ANSYS', 'Technology'),
        ('WDAY', 'Workday', 'Technology'),
        ('TEAM', 'Atlassian', 'Technology'),
        ('DDOG', 'Datadog', 'Technology'),
        ('ZS', 'Zscaler', 'Technology'),
        # NASDAQ 고배당 금융/리츠/인프라/통신
        ('AGNC', 'AGNC Investment Corp.', 'Real Estate'),
        ('NLY', 'Annaly Capital Management', 'Real Estate'),
        ('FSK', 'FS KKR Capital Corp.', 'Financial Services'),
        ('ARCC', 'Ares Capital Corporation', 'Financial Services'),
        ('MAIN', 'Main Street Capital', 'Financial Services'),
        ('ORC', 'Orchid Island Capital', 'Real Estate'),
        ('TWO', 'Two Harbors Investment', 'Real Estate'),
        ('DX', 'Dynex Capital', 'Real Estate'),
        ('CIM', 'Chimera Investment', 'Real Estate'),
        ('MFA', 'MFA Financial', 'Real Estate'),
        ('RITM', 'Rithm Capital', 'Real Estate'),
        ('STWD', 'Starwood Property Trust', 'Real Estate'),
        ('HASI', 'Hannon Armstrong', 'Real Estate'),
        ('OPI', 'Office Properties Income Trust', 'Real Estate'),
        ('GOOD', 'Gladstone Commercial', 'Real Estate'),
        ('LAND', 'Gladstone Land', 'Real Estate'),
        ('GAIN', 'Gladstone Investment', 'Financial Services'),
        ('GLAD', 'Gladstone Capital', 'Financial Services'),
        ('PSEC', 'Prospect Capital', 'Financial Services'),
        ('HTGC', 'Hercules Capital', 'Financial Services'),
        ('GBDC', 'Golub Capital BDC', 'Financial Services'),
        ('OCSL', 'Oaktree Specialty Lending', 'Financial Services'),
        ('TCPC', 'BlackRock TCP Capital', 'Financial Services'),
        ('NMFC', 'New Mountain Finance', 'Financial Services'),
        ('SLRC', 'SLR Investment Corp.', 'Financial Services'),
        ('BXSL', 'Blackstone Secured Lending', 'Financial Services'),
        ('OBDC', 'Blue Owl Capital Corp.', 'Financial Services'),
        ('CGBD', 'Carlyle Secured Lending', 'Financial Services'),
        ('TRIN', 'Trinity Capital', 'Financial Services'),
        ('HRZN', 'Horizon Technology Finance', 'Financial Services'),
        ('CSWC', 'Capital Southwest', 'Financial Services'),
        ('FDUS', 'Fidus Investment', 'Financial Services'),
        ('OXLC', 'Oxford Lane Capital', 'Financial Services'),
        ('ECC', 'Eagle Point Credit Company', 'Financial Services'),
        ('CCIF', 'Carlyle Credit Income Fund', 'Financial Services'),
        ('FCRD', 'First Eagle Alternative Capital', 'Financial Services'),
        ('RC', 'Ready Capital', 'Real Estate'),
        ('ACRE', 'Ares Commercial Real Estate', 'Real Estate'),
        ('BRSP', 'BrightSpire Capital', 'Real Estate'),
        ('KREF', 'KKR Real Estate Finance', 'Real Estate'),
        ('LADR', 'Ladder Capital', 'Real Estate'),
        ('ABR', 'Arbor Realty Trust', 'Real Estate'),
        ('HAS', 'Hasbro', 'Consumer Cyclical'),
        ('WBA', 'Walgreens Boots Alliance', 'Healthcare'),
        ('FANG', 'Diamondback Energy', 'Energy'),
        ('APA', 'APA Corporation', 'Energy'),
        ('CHRD', 'Chord Energy', 'Energy'),
        ('EQT', 'EQT Corporation', 'Energy'),
        ('TRGP', 'Targa Resources', 'Energy'),
        ('ONEOK', 'ONEOK', 'Energy'),
        ('WMB', 'Williams Companies', 'Energy'),
        ('EXC', 'Exelon Corporation', 'Utilities'),
        ('XEL', 'Xcel Energy', 'Utilities'),
        ('AEP', 'American Electric Power', 'Utilities'),
        ('SRE', 'Sempra Energy', 'Utilities'),
        ('FE', 'FirstEnergy Corp.', 'Utilities'),
        ('PPL', 'PPL Corporation', 'Utilities'),
        ('ES', 'Eversource Energy', 'Utilities'),
        ('PEG', 'Public Service Enterprise Group', 'Utilities'),
        ('D', 'Dominion Energy', 'Utilities'),
        ('ED', 'Consolidated Edison', 'Utilities'),
        ('ETR', 'Entergy Corporation', 'Utilities'),
        ('CMS', 'CMS Energy', 'Utilities'),
        ('LNT', 'Alliant Energy', 'Utilities'),
        ('EVRG', 'Evergy', 'Utilities'),
        ('PNW', 'Pinnacle West Capital', 'Utilities'),
        ('NI', 'NiSource', 'Utilities'),
        ('OGE', 'OGE Energy', 'Utilities'),
        ('CNP', 'CenterPoint Energy', 'Utilities'),
        ('AES', 'The AES Corporation', 'Utilities'),
        ('NRG', 'NRG Energy', 'Utilities'),
        ('SO', 'The Southern Company', 'Utilities'),
        ('DUK', 'Duke Energy', 'Utilities'),
        ('NEE', 'NextEra Energy', 'Utilities'),
        ('VZ', 'Verizon Communications', 'Communication Services'),
        ('T', 'AT&T Inc.', 'Communication Services'),
        ('LUMN', 'Lumen Technologies', 'Communication Services'),
        ('USM', 'United States Cellular', 'Communication Services')
    ]

    print(f"[NASDAQ] 총 {len(nasdaq_top_tickers)}개 후보군 yfinance 병렬 데이터 수집 시작...")

    def fetch_one(item):
        sym, name, sector = item
        try:
            t = yf.Ticker(sym)
            inf = t.info
            price = inf.get('currentPrice') or inf.get('regularMarketPrice') or inf.get('previousClose')
            d_rate = inf.get('dividendRate') or inf.get('trailingAnnualDividendRate')
            d_yield = inf.get('dividendYield') or inf.get('trailingAnnualDividendYield')
            mcap = inf.get('marketCap')
            payout = inf.get('payoutRatio')
            sec = inf.get('sector') or sector
            s_name = inf.get('shortName') or name

            if not price or price <= 0:
                return None
            if not d_rate or d_rate <= 0:
                if not d_yield or d_yield <= 0:
                    return None
                d_rate = (d_yield if d_yield < 1 else d_yield / 100.0) * price

            if d_yield is not None and d_yield > 0:
                calc_yield = d_yield * 100 if d_yield < 1.0 else d_yield
            else:
                calc_yield = (d_rate / price) * 100

            calc_yield = round(float(calc_yield), 2)
            if calc_yield <= 0.2:
                return None

            if payout is not None and payout > 0:
                calc_payout = round(payout * 100 if payout < 2.0 else payout, 2)
            else:
                calc_payout = np.nan

            monthly_nasdaq = {'AGNC', 'MAIN', 'ORC', 'DX', 'PSEC', 'HRZN', 'OXLC', 'ECC', 'CCIF', 'GOOD', 'LAND'}
            freq = '월배당' if sym in monthly_nasdaq else '분기배당'
            safety = evaluate_dividend_safety(calc_payout, calc_yield, 1.0, "NASDAQ")

            return {
                '종목명': s_name,
                '티커': sym,
                '시장': 'NASDAQ',
                '업종': sec,
                '시가총액': float(mcap) if mcap else 0.0,
                '현재가': round(float(price), 2),
                '배당금': round(float(d_rate), 2),
                '배당수익률': calc_yield,
                '배당성향': calc_payout,
                '배당주기': freq,
                '배당안전성': safety
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_one, nasdaq_top_tickers))

    records = [r for r in results if r is not None]
    df = pd.DataFrame(records)
    print(f"[NASDAQ] 배당 지급 종목 수: {len(df)}개")

    if df.empty or '배당수익률' not in df.columns or len(df) == 0:
        print("[NASDAQ] yfinance 수집 실패 또는 호출 한도 초과. 기존 마스터 데이터에서 폴백 로드합니다.")
        if os.path.exists(MASTER_FILE):
            df_m = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
            df_nas = df_m[df_m['시장'] == 'NASDAQ'].copy().reset_index(drop=True)
            if not df_nas.empty:
                return df_nas
        return pd.DataFrame(columns=['순위', '종목명', '티커', '시장', '업종', '시가총액', '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성'])

    df = df.sort_values(by='배당수익률', ascending=False).head(100).copy().reset_index(drop=True)
    df['순위'] = range(1, len(df) + 1)
    df['기준일'] = target_date
    df = df[[
        '순위', '종목명', '티커', '시장', '업종', '시가총액',
        '현재가', '배당금', '배당수익률', '배당성향', '배당주기', '배당안전성', '기준일'
    ]]
    return df


def main():
    print("=== 한국 및 미국 증시 배당주 TOP 100 마스터 데이터 구축 시작 ===")
    t0 = time.time()

    target_date = get_latest_business_date()
    print(f"[*] 영업일 기준일: {target_date}")

    # 1. KOSPI
    df_kospi = build_kr_market("KOSPI", target_date=target_date)

    # 2. KOSDAQ
    df_kosdaq = build_kr_market("KOSDAQ", target_date=target_date)

    # 3. S&P 500
    df_sp500 = build_us_market_sp500(target_date=target_date)

    # 4. NASDAQ
    df_nasdaq = build_us_market_nasdaq(target_date=target_date)

    # 통합 마스터 데이터프레임
    df_all = pd.concat([df_kospi, df_kosdaq, df_sp500, df_nasdaq], ignore_index=True)
    print(f"\n[통합 완료] 총 종목 수: {len(df_all)}개")
    for mkt in ['KOSPI', 'KOSDAQ', 'S&P500', 'NASDAQ']:
        cnt = len(df_all[df_all['시장'] == mkt])
        print(f"  - {mkt}: {cnt}개 종목")

    # 마스터 파일 및 당일 캐시 파일로 저장
    df_all.to_csv(MASTER_FILE, index=False, encoding='utf-8-sig')
    print(f"[저장 완료] 마스터 파일: {MASTER_FILE}")

    today_clean = target_date.replace('-', '')
    cache_file = os.path.join(CACHE_DIR, f"dividend_summary_{today_clean}.csv")
    df_all.to_csv(cache_file, index=False, encoding='utf-8-sig')
    print(f"[저장 완료] 당일 캐시 파일: {cache_file}")

    print(f"전체 소요 시간: {time.time() - t0:.1f}초")


if __name__ == '__main__':
    main()
