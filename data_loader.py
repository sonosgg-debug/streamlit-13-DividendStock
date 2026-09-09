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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
MASTER_FILE = os.path.join(CURRENT_DIR, "dividend_stocks_master.csv")


def get_latest_business_date():
    """최근 영업일 문자열 YYYY-MM-DD 반환"""
    now = datetime.datetime.now()
    for i in range(10):
        d = now - datetime.timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def load_market_data(force_refresh=False):
    """
    한국 및 미국 4개 시장(KOSPI, KOSDAQ, S&P500, NASDAQ)의 배당주 데이터를 로드합니다.
    - 캐시 파일 또는 마스터 데이터셋을 통해 0.1초 즉시 반환.
    - force_refresh=True일 경우 build_master_data를 호출하여 캐시 갱신.
    반환값: (df_all, target_date_str)
    """
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    cache_path = os.path.join(CACHE_DIR, f"dividend_summary_{today_str}.csv")
    date_display = get_latest_business_date()

    # 1. 강제 갱신 요청 시
    if force_refresh:
        try:
            import build_master_data
            build_master_data.main()
        except Exception as e:
            print(f"데이터 강제 갱신 실패: {e}")

    # 2. 당일 캐시 파일 확인
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={'티커': str}, encoding='utf-8-sig')
            if not df.empty and len(df) >= 300:
                return df, date_display
        except Exception as e:
            print(f"당일 캐시 로드 실패: {e}")

    # 3. 마스터 파일 확인
    if os.path.exists(MASTER_FILE):
        try:
            df = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
            if not df.empty and len(df) >= 300:
                return df, date_display
        except Exception as e:
            print(f"마스터 파일 로드 실패: {e}")

    # 4. 파일이 없을 경우 즉석 빌드
    try:
        import build_master_data
        build_master_data.main()
        if os.path.exists(MASTER_FILE):
            df = pd.read_csv(MASTER_FILE, dtype={'티커': str}, encoding='utf-8-sig')
            return df, date_display
    except Exception as e:
        print(f"즉석 마스터 빌드 실패: {e}")

    return pd.DataFrame(), date_display


def load_stock_history_and_dividends(ticker, market, months=12):
    """
    선택된 종목의 시계열 주가(일별 종가, 이동평균선) 및 역대 배당금 지급 내역(연도별 DPS) 수집.
    반환값:
      df_price: DataFrame (Index: Date, '종가', 'MA20', 'MA60')
      df_div_annual: DataFrame ('연도', 'DPS', '배당성장률(%)')
    """
    if not HAS_YF or not yf:
        return pd.DataFrame(), pd.DataFrame()

    # 티커 형식 변환
    if market == 'KOSPI':
        yf_symbol = f"{str(ticker).zfill(6)}.KS"
    elif market == 'KOSDAQ':
        yf_symbol = f"{str(ticker).zfill(6)}.KQ"
    else:
        yf_symbol = str(ticker).replace('.', '-')

    try:
        t = yf.Ticker(yf_symbol)
        
        # 1. 시계열 주가 로드
        period_str = f"{months}mo" if months <= 36 else "5y"
        hist = t.history(period=period_str)
        
        if hist.empty or 'Close' not in hist.columns:
            df_price = pd.DataFrame()
        else:
            df_price = pd.DataFrame(index=hist.index)
            df_price['종가'] = hist['Close'].values
            df_price['MA20'] = df_price['종가'].rolling(window=20, min_periods=1).mean()
            df_price['MA60'] = df_price['종가'].rolling(window=60, min_periods=1).mean()
            df_price.index = pd.to_datetime(df_price.index)

        # 2. 배당 이력 로드 및 연도별 집계
        divs = t.dividends
        if divs.empty:
            df_div_annual = pd.DataFrame()
        else:
            divs.index = pd.to_datetime(divs.index)
            # 최근 7개년 집계
            divs_annual = divs.groupby(divs.index.year).sum()
            current_year = datetime.datetime.now().year
            # 최근 연도 필터링
            divs_annual = divs_annual[divs_annual.index >= (current_year - 6)]
            
            df_div_annual = pd.DataFrame({
                '연도': divs_annual.index.astype(str),
                'DPS': divs_annual.values
            })
            
            # 배당 성장률 계산
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

        return df_price, df_div_annual

    except Exception as e:
        print(f"{yf_symbol} 시계열/배당 데이터 로드 실패: {e}")
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
                    if col_name == "코드/티커":
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

        # 자동 필터 (헤더 오름차순 / 내림차순 정렬 토글) 활성화
        end_col_letter = get_column_letter(len(df_export.columns))
        worksheet.auto_filter.ref = f"A1:{end_col_letter}{len(df_export) + 1}"

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
