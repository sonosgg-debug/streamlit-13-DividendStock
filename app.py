"""
app.py
한국 및 미국 증시(KOSPI, KOSDAQ, S&P 500, NASDAQ) 배당주 TOP 100 선별 및
투자 지표 비교 분석, 인터랙티브 시각화 차트 대시보드 웹 애플리케이션.
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

import io
import os
import datetime
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data_loader

# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="한국 및 미국 증시 배당주 TOP 100",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. 커스텀 CSS (38 PreferredStock 딥 다크 테마 일관 적용)
# ==========================================
st.markdown("""
<style>
    /* Main Background */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", sans-serif;
    }
    
    /* Main Content Area */
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 2.0rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 98% !important;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-right: 1px solid #334155;
    }
    
    /* Headers (00 Bookmarks / 38 PreferredStock 테마 일치) */
    h1, .main h1, [data-testid="stHeadingWithActionElements"] h1 {
        color: #8AB4F8 !important;
        font-weight: 800 !important;
        font-size: 2.0rem !important;
    }

    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3 {
        color: #f8fafc !important;
    }

    /* Input & Select Box styling */
    .stTextInput input, .stSelectbox select, .stMultiSelect {
        background-color: #334155 !important;
        color: #f8fafc !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
    }

    /* Metric Value & Label font size adjustments */
    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: 1.35rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
        color: #94a3b8 !important;
        font-weight: 500 !important;
    }

    /* 6열 상세 요약 메트릭 영역 폰트 크기 최적화 */
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="column"]:nth-child(6)) [data-testid="stMetricValue"],
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="column"]:nth-child(6)) [data-testid="stMetricValue"] > div,
    .detail-metrics [data-testid="stMetricValue"],
    .detail-metrics [data-testid="stMetricValue"] > div {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="column"]:nth-child(6)) [data-testid="stMetricLabel"],
    .detail-metrics [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
    }

    /* Section Subheaders */
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #e2e8f0;
        margin-top: 10px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Button Styling */
    .stButton button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.2s ease !important;
    }
    .stButton button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.4) !important;
    }

    /* 다운로드 버튼 공통 통일 스타일 */
    div[data-testid="stDownloadButton"] > button,
    .stDownloadButton > button {
        background-color: #334155 !important;
        color: #f8fafc !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        line-height: 36px !important;
        padding: 0 16px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease-in-out !important;
        box-sizing: border-box !important;
    }
    div[data-testid="stDownloadButton"] > button:hover,
    .stDownloadButton > button:hover {
        background-color: #475569 !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.25) !important;
    }
    div[data-testid="stDownloadButton"] > button:active,
    .stDownloadButton > button:active {
        background-color: #1e293b !important;
        border-color: #0284c7 !important;
    }
    div[data-testid="stDownloadButton"] > button p,
    div[data-testid="stDownloadButton"] > button span,
    .stDownloadButton > button p,
    .stDownloadButton > button span {
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: inherit !important;
        line-height: inherit !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Badge styles */
    .badge-safe {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .badge-danger {
        background-color: rgba(239, 68, 68, 0.2);
        color: #f87171;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* =========================================================
       사이드바 접기(<<) 및 펼치기(>>) 버튼 항상 표시 및 시인성/대비 강화
       ========================================================= */
    /* 1. 사이드바가 열려 있을 때 접기 버튼 (<<) 상시 표시 */
    [data-testid="stSidebarCollapseButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        display: inline-flex !important;
    }
    
    [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
        background-color: #1e293b !important;       /* 진한 네이비 배경 */
        border: 1.5px solid #38bdf8 !important;     /* 선명한 스카이블루 테두리로 상자 명확화 */
        border-radius: 8px !important;
        width: 38px !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
        transition: all 0.2s ease !important;
    }
    
    /* 상자 내부의 << 아이콘(Material Icon span/svg/문자)을 순백색으로 강제하여 상자와 극명한 대비 구현 */
    [data-testid="stSidebarCollapseButton"] button *,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapseButton"] svg {
        color: #ffffff !important;
        fill: #ffffff !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }
    
    /* 호버(PC) 및 터치 시 반전 효과 */
    [data-testid="stSidebarCollapseButton"] button:hover {
        background-color: #38bdf8 !important;
        border-color: #38bdf8 !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover * {
        color: #0f172a !important;
        fill: #0f172a !important;
    }

    /* 2. 사이드바 헤더 영역 패딩 및 정렬 보정 */
    [data-testid="stSidebarHeader"] {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }

    /* 3. 사이드바가 닫혔을 때 다시 여는 버튼 (>>) 시인성 강화 */
    [data-testid="stSidebarCollapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button {
        background-color: #1e293b !important;
        border: 1.5px solid #38bdf8 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button *,
    [data-testid="stSidebarCollapsedControl"] span,
    [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapsedControl"] svg {
        color: #38bdf8 !important;
        fill: #38bdf8 !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 3. 데이터 로딩 캐시 함수
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_market_data(target_date_key: str, force_refresh: bool = False):
    return data_loader.load_market_data(force_refresh=force_refresh)


@st.cache_data(ttl=600, show_spinner=False)
def get_cached_stock_history_and_dividends(ticker, market, months=12, latest_date=None, latest_price=None, force_refresh=False, *args, **kwargs):
    try:
        return data_loader.load_stock_history_and_dividends(
            ticker,
            market,
            months=months,
            latest_date=latest_date,
            latest_price=latest_price
        )
    except Exception as e:
        print(f"get_cached_stock_history_and_dividends 캐시 로드 예외: {e}")
        return pd.DataFrame(), pd.DataFrame()


# ==========================================
# 4. 세션 상태 초기화
# ==========================================
if 'market_selection' not in st.session_state:
    st.session_state.market_selection = "KOSPI"
if 'selected_stock_key' not in st.session_state:
    st.session_state.selected_stock_key = None
if 'force_reload' not in st.session_state:
    st.session_state.force_reload = False
if 'show_refresh_toast' not in st.session_state:
    st.session_state.show_refresh_toast = False


# ==========================================
# 5. 왼쪽 사이드 패널 (사이드바)
# ==========================================
with st.sidebar:
    st.markdown("<h2 style='color: #8AB4F8; font-size: 1.3rem; margin-top: 0;'>⚙️ 시장 선택 및 필터</h2>", unsafe_allow_html=True)

    # 1) 시장 선택 (사용자 요청: KOSPI, KOSDAQ, S&P 500, NASDAQ)
    market_options = ["KOSPI", "KOSDAQ", "S&P 500", "NASDAQ"]
    if st.session_state.market_selection == "S&P500":
        st.session_state.market_selection = "S&P 500"
    current_market_idx = market_options.index(st.session_state.market_selection) if st.session_state.market_selection in market_options else 0
    
    market_choice = st.selectbox(
        "🏛️ 시장 선택",
        options=market_options,
        index=current_market_idx,
        help="조회할 주식 시장을 선택합니다. (한국 2개 시장, 미국 2개 시장)"
    )

    st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 16px 0;'>", unsafe_allow_html=True)

    # 2) 스마트 필터
    st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #cbd5e1; margin-bottom: 8px;'>🎯 스마트 필터</div>", unsafe_allow_html=True)

    search_keyword = st.text_input(
        "종목명 / 티커 검색",
        placeholder="예: 삼성, 현대, Apple, 리츠...",
        help="종목명 또는 티커 코드로 검색합니다."
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_div_yield = st.number_input(
            "최소 배당률(%)",
            min_value=0.0,
            max_value=30.0,
            value=0.0,
            step=0.5,
            help="0.0%는 전체 순위 종목 표시"
        )
    with col_f2:
        safety_filter = st.selectbox(
            "배당 안전성",
            options=["전체", "안전/보통만", "안전만"],
            index=0,
            help="배당성향 과다 및 적자 배당(주의) 종목을 제외합니다."
        )

    # 배당주기 필터
    freq_filter = st.selectbox(
        "배당주기 선택",
        options=["전체 주기", "연배당", "분기배당", "월배당"],
        index=0,
        help="현금흐름 계획에 맞는 배당주기를 필터링합니다."
    )

    # 정렬 기준 선택 (순위는 1부터 100까지 항상 고정 유지)
    sort_option = st.selectbox(
        "정렬 기준 (정렬 항목)",
        options=[
            "배당수익률 높은순 (기본)",
            "시가총액 높은순",
            "현재가 높은순",
            "배당금 높은순",
            "배당성향 낮은순",
            "배당성향 높은순"
        ],
        index=0,
        help="선택한 항목으로 재정렬하더라도 순위는 늘 1부터 100까지 고정 표시됩니다."
    )

    st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 16px 0;'>", unsafe_allow_html=True)

    # 3) Update & 조회 버튼 (다른 앱과의 레이아웃 통일: 왼쪽 Update, 오른쪽 조회)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_update = st.button("🔄 Update", use_container_width=True, help="최신 데이터를 다시 수집하고 캐시를 갱신합니다.")
    with col_btn2:
        btn_search = st.button("🔍 조회", type="primary", use_container_width=True, help="선택한 조건으로 대시보드를 조회합니다.")

    if btn_update:
        st.cache_data.clear()
        st.session_state.force_reload = True
        st.session_state.show_refresh_toast = True
        st.rerun()

    if btn_search or (market_choice != st.session_state.market_selection):
        st.session_state.market_selection = market_choice
        st.session_state.selected_stock_key = None
        st.rerun()


# ==========================================
# 6. 데이터 로드 및 시장별 필터링
# ==========================================
force_refresh = st.session_state.force_reload
st.session_state.force_reload = False
latest_biz_date = data_loader.get_latest_business_date()

with st.spinner("증시 배당주 펀더멘털 데이터를 불러오는 중입니다..."):
    df_raw, target_date = get_cached_market_data(latest_biz_date, force_refresh=force_refresh)

if st.session_state.get('show_refresh_toast', False):
    st.toast(f"✅ {target_date} 최신 주가 및 배당 데이터가 성공적으로 갱신되었습니다!", icon="🚀")
    st.session_state.show_refresh_toast = False

if df_raw.empty:
    st.error("데이터를 불러올 수 없습니다. 인터넷 연결 및 데이터 소스 설정을 확인하세요.")
    st.stop()

# 1) 선택된 시장 데이터 필터링 (기본 100개)
active_market = st.session_state.market_selection
is_korean = active_market in ["KOSPI", "KOSDAQ"]
currency_symbol = "₩" if is_korean else "$"
currency_unit = "원" if is_korean else "$"

# S&P 500 / S&P500 양방향 호환 필터링
mkt_targets = [active_market, active_market.replace(" ", "")]
df_market = df_raw[df_raw["시장"].isin(mkt_targets)].copy().reset_index(drop=True)

# 2) 스마트 필터 적용
df_filtered = df_market.copy()

if search_keyword.strip():
    kw = search_keyword.strip().lower()
    df_filtered = df_filtered[
        df_filtered["종목명"].astype(str).str.lower().str.contains(kw) |
        df_filtered["티커"].astype(str).str.lower().str.contains(kw)
    ]

if min_div_yield > 0:
    df_filtered = df_filtered[df_filtered["배당수익률"] >= min_div_yield]

if safety_filter == "안전/보통만":
    df_filtered = df_filtered[~df_filtered["배당안전성"].str.contains("주의", na=False)]
elif safety_filter == "안전만":
    df_filtered = df_filtered[df_filtered["배당안전성"].str.contains("안전", na=False)]

if freq_filter != "전체 주기":
    df_filtered = df_filtered[df_filtered["배당주기"] == freq_filter]

# 3) 정렬 기준 적용 (다른 항목으로 재정렬하더라도 순위는 늘 1부터 100까지 고정 유지)
if sort_option == "시가총액 높은순":
    df_filtered = df_filtered.sort_values(by="시가총액", ascending=False).reset_index(drop=True)
elif sort_option == "현재가 높은순":
    df_filtered = df_filtered.sort_values(by="현재가", ascending=False).reset_index(drop=True)
elif sort_option == "배당금 높은순":
    df_filtered = df_filtered.sort_values(by="배당금", ascending=False).reset_index(drop=True)
elif sort_option == "배당성향 낮은순":
    df_filtered = df_filtered.sort_values(by="배당성향", ascending=True).reset_index(drop=True)
elif sort_option == "배당성향 높은순":
    df_filtered = df_filtered.sort_values(by="배당성향", ascending=False).reset_index(drop=True)
else:
    df_filtered = df_filtered.sort_values(by="배당수익률", ascending=False).reset_index(drop=True)

# 순위는 어떤 항목으로 정렬하더라도 항상 1부터 100까지 고정
df_filtered["순위"] = list(range(1, len(df_filtered) + 1))


# ==========================================
# 7. 메인 타이틀 영역
# ==========================================
st.markdown(
    "<h1 style='text-align: center; color: #8AB4F8 !important; font-weight: 800; font-size: 2.0rem; margin-top: 0; margin-bottom: 0.3rem; letter-spacing: -0.5px;'>"
    "<span style='color: #8AB4F8 !important;'>한국 및 미국 증시 배당주 TOP 100</span>"
    "</h1>",
    unsafe_allow_html=True
)

# 메타 정보 표시
latest_biz_date = data_loader.get_latest_business_date()
is_outdated = (target_date < latest_biz_date)
outdated_badge = f" &nbsp;|&nbsp; <span style='color: #fbbf24; font-weight: 600;'>⚠️ 이전 마스터 기준 (🔄 Update 권장)</span>" if is_outdated else ""

st.markdown(
    f"<div style='text-align: center; font-size: 0.85rem; color: #94a3b8; margin-bottom: 12px;'>"
    f"기준일: <span style='color: #38bdf8; font-weight: 600;'>{target_date}</span> (종가 기준) &nbsp;|&nbsp; "
    f"선택 시장: <span style='color: #f8fafc; font-weight: 700;'>{active_market}</span> &nbsp;|&nbsp; "
    f"표시 통화: <span style='color: #34d399; font-weight: 600;'>{'원화(KRW, ₩)' if is_korean else '달러(USD, $)'}</span> &nbsp;|&nbsp; "
    f"데이터 출처: <span style='color: #cbd5e1;'>{'KRX & 네이버 증권' if is_korean else 'S&P Dow Jones / Yahoo Finance'}</span>"
    f"{outdated_badge}"
    f"</div>",
    unsafe_allow_html=True
)

# [가로 선 1]: 타이틀 영역과 KPI 영역 사이
st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 8px 0 18px 0;'>", unsafe_allow_html=True)


# ==========================================
# 8. 핵심 요약 KPI 지표 카드 (4열)
# ==========================================
col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

total_count = len(df_filtered)
avg_yield = df_filtered["배당수익률"].mean() if total_count > 0 else 0.0
valid_payout = df_filtered["배당성향"].dropna()
avg_payout = valid_payout.mean() if len(valid_payout) > 0 else 0.0

if total_count > 0:
    top_div_row = df_filtered.loc[df_filtered["배당수익률"].idxmax()]
    top_div_info = f"{top_div_row['종목명']} ({top_div_row['배당수익률']:.2f}%)"
else:
    top_div_info = "-"

with col_kpi1:
    with st.container(border=True):
        st.metric("📊 조회된 종목 수", f"{total_count:,} 개", help=f"{active_market} 시장 배당 상위 종목")

with col_kpi2:
    with st.container(border=True):
        st.metric("💰 평균 배당수익률", f"{avg_yield:.2f} %", help="조회된 종목들의 단순 평균 배당률")

with col_kpi3:
    with st.container(border=True):
        st.metric("⚖️ 평균 배당성향", f"{avg_payout:.1f} %", help="순이익 중 배당금 지급 비율")

with col_kpi4:
    with st.container(border=True):
        st.metric("🏆 최고 배당수익률 종목", top_div_info, help="현재 필터 조건 내 1위 배당 종목")


# ==========================================
# 9. 메인 영역: 조회 결과 데이터 테이블
# ==========================================
col_tbl_title, col_dl = st.columns([8, 2], vertical_alignment="bottom")
with col_tbl_title:
    st.markdown(
        f"<div class='section-header'>📋 {active_market} 배당주 TOP {min(100, len(df_filtered))} 데이터 테이블</div>",
        unsafe_allow_html=True
    )
with col_dl:
    # 엑셀 다운로드 파일 생성
    df_excel = df_filtered.copy()
    df_excel["코드/티커"] = df_excel["티커"].astype(str)
    excel_cols = [
        "순위", "코드/티커", "종목명", "시장", "업종", "시가총액",
        "현재가", "배당금", "배당수익률", "배당성향", "배당주기", "배당안전성"
    ]
    df_excel = df_excel[excel_cols].copy()
    excel_bytes = data_loader.create_excel_download(df_excel, active_market)
    file_name = f"배당주_TOP100_{active_market}_{target_date.replace('-', '')}.xlsx"
    
    st.download_button(
        label="📥 엑셀 파일 다운로드",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 표시용 데이터프레임 가공
df_display = df_filtered.copy()
df_display["코드/티커"] = df_display["티커"].astype(str)

if is_korean:
    # 한국 주식: 시가총액을 억원 단위로 변환
    df_display["시가총액_표시"] = (df_display["시가총액"] / 1e8).round(0)
    cap_format = "%,.0f 억"
    price_format = "%,.0f 원"
    dps_format = "%,.0f 원"
else:
    # 미국 주식: 시가총액을 백만달러(M) 단위로 변환
    df_display["시가총액_표시"] = (df_display["시가총액"] / 1e6).round(1)
    cap_format = "$%,.1f M"
    price_format = "$%,.2f"
    dps_format = "$%,.2f"

# 필수 헤더 9개 + 코드/티커 + 전문가 지표 구성
display_cols = [
    "순위",
    "코드/티커",
    "종목명",
    "시장",
    "업종",
    "시가총액_표시",
    "현재가",
    "배당금",
    "배당수익률",
    "배당성향",
    "배당주기",
    "배당안전성"
]

column_config = {
    "순위": st.column_config.NumberColumn("순위", width=50, format="%d", pinned=True),
    "코드/티커": st.column_config.TextColumn("코드/티커", width=75),
    "종목명": st.column_config.TextColumn("종목명", width="medium"),
    "시장": st.column_config.TextColumn("시장", width="small"),
    "업종": st.column_config.TextColumn("업종", width="medium"),
    "시가총액_표시": st.column_config.NumberColumn("시가총액", format=cap_format, width="small"),
    "현재가": st.column_config.NumberColumn("현재가", format=price_format, width="small"),
    "배당금": st.column_config.NumberColumn("배당금(DPS)", format=dps_format, width="small"),
    "배당수익률": st.column_config.NumberColumn("배당수익률(%)", format="%.2f%%", width="small"),
    "배당성향": st.column_config.NumberColumn("배당성향", format="%.1f%%", width="small"),
    "배당주기": st.column_config.TextColumn("배당주기", width="small"),
    "배당안전성": st.column_config.TextColumn("배당 안정성", width=140),
}

# st.dataframe 인터랙티브 테이블 렌더링
selection = st.dataframe(
    df_display[display_cols],
    use_container_width=True,
    height=420,
    hide_index=True,
    column_config=column_config,
    on_select="rerun",
    selection_mode="single-row"
)

# 테이블에서 선택된 행이 있으면 상세 분석 종목으로 동기화
selected_from_table = None
if selection and selection.get("rows"):
    sel_idx = selection["rows"][0]
    if sel_idx < len(df_filtered):
        selected_from_table = df_filtered.iloc[sel_idx]["종목명"]
        st.session_state.selected_stock_key = selected_from_table


# ==========================================
# 10. [가로 선 2]: 데이터 영역과 상세 영역 사이
# ==========================================
st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 25px 0 22px 0;'>", unsafe_allow_html=True)


# ==========================================
# 11. 메인 영역: 종목별 상세 비교 및 시각화 차트
# ==========================================
st.markdown("<div class='section-header'>📈 종목별 상세 비교 및 시각화 차트</div>", unsafe_allow_html=True)

stock_name_options = df_filtered["종목명"].tolist()

if not stock_name_options:
    st.info("조건에 맞는 종목이 없습니다. 필터를 조정해 보세요.")
    st.stop()

# 디폴트 인덱스 계산 (테이블 선택 우선, 없으면 1위 종목)
if st.session_state.selected_stock_key in stock_name_options:
    default_stock_idx = stock_name_options.index(st.session_state.selected_stock_key)
elif selected_from_table and selected_from_table in stock_name_options:
    default_stock_idx = stock_name_options.index(selected_from_table)
else:
    default_stock_idx = 0

col_sel1, col_sel2, col_sel3 = st.columns([5, 4, 3])
with col_sel1:
    chosen_stock_name = st.selectbox(
        "분석할 배당주 종목 선택",
        options=stock_name_options,
        index=default_stock_idx,
        help="상단 테이블에서 행을 클릭하거나 목록에서 종목을 직접 선택할 수 있습니다."
    )

target_stock_row = df_filtered[df_filtered["종목명"] == chosen_stock_name].iloc[0]
chosen_ticker = str(target_stock_row["티커"])
chosen_market = target_stock_row["시장"]

with col_sel2:
    period_label = st.radio(
        "주가 조회 기간",
        options=["3개월", "6개월", "1년", "3년"],
        index=2,
        horizontal=True
    )
    period_map = {"3개월": 3, "6개월": 6, "1년": 12, "3년": 36}
    chosen_months = period_map[period_label]

with col_sel3:
    if is_korean:
        default_invest = 1000  # 1000만원
        invest_amount = st.slider("DRIP 시뮬레이션 투자금", min_value=100, max_value=5000, value=default_invest, step=100, format="%d만원")
        invest_val_num = invest_amount * 10000
    else:
        default_invest = 10000 # $10,000
        invest_amount = st.slider("DRIP 시뮬레이션 투자금", min_value=1000, max_value=100000, value=default_invest, step=1000, format="$%d")
        invest_val_num = invest_amount

# 6열 상세 지표 요약 카드
with st.container(border=True):
    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    with col_m1:
        st.metric("종목명 (티커)", f"{chosen_stock_name}", help=f"티커: {chosen_ticker} | 시장: {chosen_market}")
    with col_m2:
        price_val_str = f"{target_stock_row['현재가']:,.0f}원" if is_korean else f"${target_stock_row['현재가']:,.2f}"
        st.metric("현재 주가", price_val_str)
    with col_m3:
        st.metric("배당수익률", f"{target_stock_row['배당수익률']:.2f}%")
    with col_m4:
        dps_val_str = f"{target_stock_row['배당금']:,.0f}원" if is_korean else f"${target_stock_row['배당금']:,.2f}"
        st.metric("연간 배당금(DPS)", dps_val_str)
    with col_m5:
        payout_val = target_stock_row['배당성향']
        payout_str = f"{payout_val:.1f}%" if pd.notna(payout_val) else "N/A"
        st.metric("배당성향", payout_str)
    with col_m6:
        st.metric("배당주기 / 안전성", f"{target_stock_row['배당주기']}", help=f"안전성 등급: {target_stock_row['배당안전성']}")


# 시계열 주가 및 배당 이력 로드
with st.spinner(f"{chosen_stock_name} 시계열 주가 및 배당 이력을 불러오는 중..."):
    df_price_hist, df_div_annual = get_cached_stock_history_and_dividends(
        chosen_ticker,
        chosen_market,
        months=chosen_months,
        latest_date=target_date,
        latest_price=target_stock_row["현재가"],
        force_refresh=force_refresh
    )

# 2x2 차트 레이아웃
col_ch1, col_ch2 = st.columns([6, 6])

# ----------------------------------------------------
# [차트 1]: 주가 추이 및 이동평균선
# ----------------------------------------------------
with col_ch1:
    fig1 = go.Figure()
    if not df_price_hist.empty:
        # 날짜 문자열 변환 (Plotly D3의 UTC 시차 계산으로 전일(Sep 8)로 밀려 표시되는 현상 원천 방지)
        date_strs = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10] for d in df_price_hist.index]

        fig1.add_trace(go.Scatter(
            x=date_strs,
            y=df_price_hist['종가'],
            mode='lines',
            name="주가 (종가)",
            line=dict(color='#38bdf8', width=2),
            hovertemplate=f"종가: %{{y:,.0f}}{currency_unit}<extra></extra>" if is_korean else f"종가: $%{{y:,.2f}}<extra></extra>"
        ))
        fig1.add_trace(go.Scatter(
            x=date_strs,
            y=df_price_hist['MA20'],
            mode='lines',
            name="20일 이동평균",
            line=dict(color='#f59e0b', width=1.5, dash='dot'),
            hovertemplate=f"20일 이평: %{{y:,.0f}}{currency_unit}<extra></extra>" if is_korean else f"20일 이평: $%{{y:,.2f}}<extra></extra>"
        ))
        fig1.add_trace(go.Scatter(
            x=date_strs,
            y=df_price_hist['MA60'],
            mode='lines',
            name="60일 이동평균",
            line=dict(color='#a855f7', width=1.5, dash='dash'),
            hovertemplate=f"60일 이평: %{{y:,.0f}}{currency_unit}<extra></extra>" if is_korean else f"60일 이평: $%{{y:,.2f}}<extra></extra>"
        ))
        y_label = f"주가 ({currency_unit})"
    else:
        # 데이터 부재 시 기본 텍스트 표시
        fig1.add_annotation(
            text="시계열 주가 데이터를 조회할 수 없습니다.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color="#94a3b8", size=14)
        )
        y_label = "주가"

    fig1.update_layout(
        title=dict(
            text=f"<b>{chosen_stock_name} 주가 및 이동평균선 추이 ({period_label})</b>",
            font=dict(color="#f8fafc", size=14)
        ),
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=50, b=40),
        yaxis=dict(title=y_label, gridcolor="#334155"),
        xaxis=dict(
            gridcolor="#334155",
            type="date",
            tickformat="%Y-%m-%d",
            hoverformat="%Y-%m-%d"
        )
    )
    st.plotly_chart(fig1, use_container_width=True)

# ----------------------------------------------------
# [차트 2]: 연도별 배당금(DPS) 및 배당 성장률
# ----------------------------------------------------
with col_ch2:
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])

    if not df_div_annual.empty and len(df_div_annual) > 0:
        fig2.add_trace(
            go.Bar(
                x=df_div_annual['연도'],
                y=df_div_annual['DPS'],
                name=f"연간 배당금 ({currency_unit})",
                marker_color='#34d399',
                text=[f"{v:,.0f}{currency_unit}" if is_korean else f"${v:.2f}" for v in df_div_annual['DPS']],
                textposition='auto'
            ),
            secondary_y=False
        )

        valid_growth = df_div_annual.dropna(subset=['배당성장률(%)'])
        if not valid_growth.empty:
            fig2.add_trace(
                go.Scatter(
                    x=valid_growth['연도'],
                    y=valid_growth['배당성장률(%)'],
                    name="배당성장률 (%)",
                    mode='lines+markers+text',
                    marker=dict(size=8, color='#fbbf24'),
                    line=dict(color='#fbbf24', width=2),
                    text=[f"{g:+.1f}%" for g in valid_growth['배당성장률(%)']],
                    textposition='top center'
                ),
                secondary_y=True
            )
    else:
        fig2.add_annotation(
            text="과거 연도별 배당 이력 데이터가 없습니다.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color="#94a3b8", size=14)
        )

    fig2.update_layout(
        title=dict(
            text=f"<b>{chosen_stock_name} 연도별 배당금 및 배당성장률</b>",
            font=dict(color="#f8fafc", size=14)
        ),
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=50, b=40)
    )
    fig2.update_yaxes(title_text=f"주당 배당금 ({currency_unit})", secondary_y=False, gridcolor="#334155")
    fig2.update_yaxes(title_text="성장률 (%)", secondary_y=True, gridcolor="#334155")
    st.plotly_chart(fig2, use_container_width=True)


# 하단 2단 레이아웃 (4분면 매트릭스 & DRIP 복리 시뮬레이터)
col_ch3, col_ch4 = st.columns([6, 6])

# ----------------------------------------------------
# [차트 3]: 배당수익률 vs 배당성향 4분면 매트릭스
# ----------------------------------------------------
with col_ch3:
    fig3 = go.Figure()

    # 시장 전체 종목 산점도
    df_matrix = df_market.dropna(subset=['배당성향', '배당수익률']).copy()
    # 이상치 완화 (배당성향 200% 이하로 클리핑하여 보기 쉽게 표현)
    df_matrix['표시_배당성향'] = df_matrix['배당성향'].clip(upper=180)

    # 1) 전체 종목 스캐터
    fig3.add_trace(go.Scatter(
        x=df_matrix['표시_배당성향'],
        y=df_matrix['배당수익률'],
        mode='markers',
        name=f"{active_market} 종목들",
        marker=dict(
            size=8,
            color='#64748b',
            opacity=0.6,
            line=dict(width=1, color='#334155')
        ),
        text=df_matrix['종목명'],
        hovertemplate="<b>%{text}</b><br>배당수익률: %{y:.2f}%<br>배당성향: %{x:.1f}%<extra></extra>"
    ))

    # 2) 선택된 종목 하이라이트
    chosen_payout = target_stock_row['배당성향']
    chosen_yield = target_stock_row['배당수익률']
    if pd.notna(chosen_payout):
        disp_payout = min(chosen_payout, 180)
        fig3.add_trace(go.Scatter(
            x=[disp_payout],
            y=[chosen_yield],
            mode='markers+text',
            name=f"선택: {chosen_stock_name}",
            marker=dict(size=16, color='#fbbf24', symbol='star', line=dict(width=2, color='#ffffff')),
            text=[f"★ {chosen_stock_name}"],
            textposition="top center",
            hovertemplate=f"<b>{chosen_stock_name}</b><br>배당수익률: {chosen_yield:.2f}%<br>배당성향: {chosen_payout:.1f}%<extra></extra>"
        ))

    # 4분면 가이드라인 (배당성향 70%, 배당수익률 6%)
    fig3.add_vline(x=70, line_dash="dash", line_color="#475569", opacity=0.7)
    fig3.add_hline(y=6.0, line_dash="dash", line_color="#475569", opacity=0.7)

    # 4분면 텍스트 주석
    fig3.add_annotation(x=35, y=14, text="🌟 이상적 고배당 (저성향·고배당)", showarrow=False, font=dict(color="#34d399", size=10))
    fig3.add_annotation(x=125, y=14, text="⚠️ 배당 함정 주의 (고성향·고배당)", showarrow=False, font=dict(color="#f87171", size=10))
    fig3.add_annotation(x=35, y=2.5, text="🌱 배당성장형 (안정 배당)", showarrow=False, font=dict(color="#38bdf8", size=10))

    fig3.update_layout(
        title=dict(
            text=f"<b>{active_market} 배당수익률 vs 배당성향 4분면 매트릭스</b>",
            font=dict(color="#f8fafc", size=14)
        ),
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(title="배당성향 (%)", gridcolor="#334155"),
        yaxis=dict(title="배당수익률 (%)", gridcolor="#334155"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig3, use_container_width=True)

# ----------------------------------------------------
# [차트 4]: 배당 재투자(DRIP) 복리 시뮬레이터
# ----------------------------------------------------
with col_ch4:
    fig4 = go.Figure()

    stock_yield = target_stock_row['배당수익률'] / 100.0
    assumed_price_growth = 0.03  # 연 3% 주가 상승 가정
    years = list(range(0, 11))

    # 1) 단순 보유 (배당금 현금 수령 및 소비)
    val_simple = [invest_val_num * ((1 + assumed_price_growth) ** y) for y in years]
    # 2) 배당 재투자(DRIP: Dividend Reinvestment Plan) 복리 효과
    val_drip = [invest_val_num * ((1 + assumed_price_growth + stock_yield) ** y) for y in years]

    fig4.add_trace(go.Scatter(
        x=years,
        y=val_drip,
        mode='lines+markers',
        name="배당 재투자(DRIP) 복리 자산",
        line=dict(color='#10b981', width=2.5),
        fill='tonexty',
        fillcolor='rgba(16, 185, 129, 0.1)'
    ))

    fig4.add_trace(go.Scatter(
        x=years,
        y=val_simple,
        mode='lines+markers',
        name="단순 주가 보유 (배당 미재투자)",
        line=dict(color='#64748b', width=2, dash='dot')
    ))

    # 10년 후 복리 격차 계산
    gap_val = val_drip[-1] - val_simple[-1]
    gap_str = f"+{gap_val / 10000:,.0f}만원" if is_korean else f"+${gap_val:,.0f}"

    fig4.update_layout(
        title=dict(
            text=f"<b>배당 재투자(DRIP) 10년 복리 시뮬레이터 (격차: {gap_str})</b>",
            font=dict(color="#f8fafc", size=14)
        ),
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(title="투자 경과 연수 (년)", tickmode='linear', dtick=1, gridcolor="#334155"),
        yaxis=dict(title=f"예상 평가액 ({currency_unit})", gridcolor="#334155"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig4, use_container_width=True)


# ==========================================
# 12. 전문가 배당 진단 카드 & 핵심 체크포인트
# ==========================================
with st.container(border=True):
    st.markdown("<div style='font-size: 1.15rem; font-weight: 700; color: #8AB4F8; margin-bottom: 12px;'>💡 전문가 배당 진단 & 투자 체크포인트</div>", unsafe_allow_html=True)

    col_diag1, col_diag2, col_diag3 = st.columns(3)

    with col_diag1:
        st.markdown("**1. 배당수익률 매력도 진단:**")
        mkt_avg = df_market["배당수익률"].mean()
        stock_y = target_stock_row["배당수익률"]
        diff_y = stock_y - mkt_avg

        if diff_y > 2.0:
            st.markdown(f":green[**시장 평균 대비 초고배당 (+{diff_y:.2f}%p)**]")
            st.caption(f"{active_market} 시장 평균({mkt_avg:.2f}%)보다 현저히 높은 배당을 지급하며, 높은 인컴 수익 창출이 가능합니다.")
        elif diff_y > 0.0:
            st.markdown(f":blue[**시장 평균 상회 우량 배당 (+{diff_y:.2f}%p)**]")
            st.caption(f"시장 평균({mkt_avg:.2f}%)을 웃돌며 안정적인 현금흐름과 주가 방어력을 기대할 수 있습니다.")
        else:
            st.markdown(f":orange[**시장 평균 수준 또는 성장 배당 ({diff_y:.2f}%p)**]")
            st.caption("배당수익률 자체보다는 미래 배당 성장 가능성 및 자본 차익을 함께 고려해야 합니다.")

    with col_diag2:
        st.markdown("**2. 배당 지속 가능성 (배당 함정 진단):**")
        payout = target_stock_row["배당성향"]
        safety_status = target_stock_row["배당안전성"]

        if pd.isna(payout) or "주의" in safety_status:
            st.markdown(f":red[**{safety_status}**]")
            st.caption("배당성향이 100%를 초과하거나 적자 상태에서 배당이 지급되어, 향후 배당 삭감(Dividend Cut) 위험에 유의해야 합니다.")
        elif payout > 75:
            st.markdown(f":orange[**{safety_status} (보통 구간)**]")
            st.caption("배당성향이 75% 이상으로 높은 편입니다. 리츠나 공익 유틸리티가 아닌 일반 기업이라면 이익 변동성을 체크하세요.")
        else:
            st.markdown(f":green[**{safety_status} (최적 안전 구간)**]")
            st.caption(f"배당성향이 {payout:.1f}%로 매우 건전하여 이익 감소 시에도 배당을 유지하거나 늘릴 여력이 충분합니다.")

    with col_diag3:
        st.markdown("**3. 투자 전략 및 현금흐름 제언:**")
        freq = target_stock_row["배당주기"]
        if freq == "월배당":
            st.caption("매월 배당금이 지급되는 **월배당 종목**으로, 은퇴 생활비 마련이나 빠른 복리 재투자에 최적화된 포트폴리오 자산입니다.")
        elif freq == "분기배당":
            st.caption("3개월마다 현금이 유입되는 **분기배당 종목**으로, 계절적 배당 쏠림 없이 연중 안정적인 재투자 사이클을 운영할 수 있습니다.")
        else:
            st.caption("연 1회 결산배당 중심의 종목으로, 연말 배당락일 전후의 주가 변동성을 활용한 전략적 매수 진입이 유효합니다.")

# 하단 투자 유의사항 공통 푸터
st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 30px 0 10px 0;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 8px; margin-bottom: 24px; line-height: 1.6;'>"
    "⚠️ 본 서비스에서 제공하는 모든 정보는 투자 참고용이며, 투자의 최종 결정과 책임은 투자자 본인에게 있습니다."
    "</div>",
    unsafe_allow_html=True
)
