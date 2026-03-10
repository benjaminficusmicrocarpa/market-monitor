"""
Market Monitor Dashboard
Reads from Google Sheets, displays EOD / Evening / PreMarket scans + Watchlist.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, timedelta
import json

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stDataFrame { font-size: 13px; }
    div[data-testid="metric-container"] { background: #1a1a2e; border-radius: 8px; padding: 8px; }
    .up-badge   { color: #00d26a; font-weight: bold; }
    .down-badge { color: #ff4b4b; font-weight: bold; }
    h1 { font-size: 1.6rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Auth ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)


def get_spreadsheet_id():
    return st.secrets["spreadsheet_id"]


# ── Data Loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_tab(tab_name: str) -> pd.DataFrame:
    try:
        client = get_client()
        sh     = client.open_by_key(get_spreadsheet_id())
        ws     = sh.worksheet(tab_name)
        data   = ws.get_all_records()
        return pd.DataFrame(data)
    except gspread.WorksheetNotFound:
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading {tab_name}: {e}")
        return pd.DataFrame()


def add_to_watchlist(rows: pd.DataFrame, source: str):
    """Append selected rows to the Watchlist tab."""
    client         = get_client()
    spreadsheet_id = get_spreadsheet_id()
    sh             = client.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet("Watchlist")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Watchlist", rows=2000, cols=12)
        ws.append_row(
            ["Date Added", "Ticker", "Company", "Sector",
             "Close / Price", "Change %", "Volume", "Direction", "Catalyst", "Scan Source"],
            value_input_option="USER_ENTERED"
        )

    existing_tickers = ws.col_values(2)[1:]  # skip header

    new_rows = []
    skipped  = []
    for _, row in rows.iterrows():
        ticker = str(row.get("Ticker", ""))
        if ticker in existing_tickers:
            skipped.append(ticker)
            continue
        new_rows.append([
            str(date.today()),
            ticker,
            str(row.get("Company", "")),
            str(row.get("Sector", "")),
            str(row.get("Close", row.get("Pre-Mkt Price", ""))),
            str(row.get("Change %", "")),
            str(row.get("Volume", "")),
            str(row.get("Direction", "")),
            str(row.get("Catalyst", "")),
            source,
        ])

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")

    st.cache_data.clear()
    return len(new_rows), skipped


# ── Scan Tab Renderer ─────────────────────────────────────────────────────────
def render_scan_tab(tab_name: str, source_label: str, selected_date: str):
    df = load_tab(tab_name)

    if df.empty:
        st.info("📭 No data yet — scans will populate this tab automatically after the scheduled run.")
        return

    # Date filter
    df_day = df[df["Date"] == selected_date].copy() if "Date" in df.columns else df.copy()

    # ── Date navigation ──
    available_dates = sorted(df["Date"].unique(), reverse=True) if "Date" in df.columns else []

    if not df_day.empty:
        # Summary metrics
        n_up   = len(df_day[df_day["Direction"] == "UP"]) if "Direction" in df_day.columns else 0
        n_down = len(df_day[df_day["Direction"] == "DOWN"]) if "Direction" in df_day.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Movers", len(df_day))
        c2.metric("🟢 Up", n_up)
        c3.metric("🔴 Down", n_down)
        if "Vol Ratio" in df_day.columns:
            avg_vr = pd.to_numeric(df_day["Vol Ratio"], errors="coerce").mean()
            c4.metric("Avg Vol Ratio", f"{avg_vr:.1f}x" if pd.notna(avg_vr) else "—")

        st.markdown("---")

        # Direction filter
        direction_filter = st.radio(
            "Show", ["All", "🟢 Up only", "🔴 Down only"],
            horizontal=True,
            key=f"dir_{tab_name}"
        )
        if "Direction" in df_day.columns:
            if direction_filter == "🟢 Up only":
                df_day = df_day[df_day["Direction"] == "UP"]
            elif direction_filter == "🔴 Down only":
                df_day = df_day[df_day["Direction"] == "DOWN"]

        # Checkbox column for watchlist
        df_display = df_day.copy()
        df_display.insert(0, "➕", False)

        # Drop Date column from display (already filtered)
        display_cols = [c for c in df_display.columns if c != "Date"]
        df_display = df_display[display_cols]

        col_config = {
            "➕": st.column_config.CheckboxColumn("➕", default=False, width="small"),
            "Change %": st.column_config.NumberColumn("Change %", format="%.2f%%"),
            "Vol Ratio": st.column_config.NumberColumn("Vol Ratio", format="%.1fx"),
            "Catalyst": st.column_config.TextColumn("Catalyst", width="large"),
        }

        edited = st.data_editor(
            df_display,
            column_config=col_config,
            hide_index=True,
            use_container_width=True,
            key=f"grid_{tab_name}_{selected_date}",
        )

        selected_rows = edited[edited["➕"] == True].drop(columns=["➕"])

        if st.button(
            f"⭐ Add Selected to Watchlist ({len(selected_rows)})",
            key=f"add_{tab_name}",
            type="primary",
            disabled=len(selected_rows) == 0,
        ):
            added, skipped = add_to_watchlist(selected_rows, source_label)
            if added:
                st.success(f"✅ Added {added} stock(s) to Watchlist!")
            if skipped:
                st.warning(f"Already in Watchlist: {', '.join(skipped)}")

    else:
        st.info(f"No data for {selected_date}.")
        if available_dates:
            st.caption(f"Data available for: {', '.join(available_dates[:5])}{'...' if len(available_dates) > 5 else ''}")


# ── Watchlist Tab ─────────────────────────────────────────────────────────────
def render_watchlist_tab():
    st.subheader("⭐ Watchlist")
    df = load_tab("Watchlist")

    if df.empty:
        st.info("Your watchlist is empty. Add stocks from the scan tabs above.")
        return

    # Sort newest first
    if "Date Added" in df.columns:
        df = df.sort_values("Date Added", ascending=False)

    c1, c2 = st.columns([3, 7])
    with c1:
        show_all = st.checkbox("Show all dates", value=True, key="wl_all")
    if not show_all:
        with c2:
            wl_date = st.date_input("Filter by date added", value=date.today(), key="wl_date")
        df = df[df["Date Added"] == wl_date.strftime("%Y-%m-%d")]

    # Source filter
    if "Scan Source" in df.columns:
        sources = ["All"] + sorted(df["Scan Source"].unique().tolist())
        src_filter = st.selectbox("Scan Source", sources, key="wl_src")
        if src_filter != "All":
            df = df[df["Scan Source"] == src_filter]

    col_config = {
        "Change %": st.column_config.NumberColumn("Change %", format="%.2f%%"),
        "Catalyst": st.column_config.TextColumn("Catalyst", width="large"),
    }

    st.dataframe(df, use_container_width=True, hide_index=True, column_config=col_config)
    st.caption(f"{len(df)} stock(s) in view")

    if st.button("🔄 Refresh Watchlist"):
        st.cache_data.clear()
        st.rerun()


# ── Historical Browser ────────────────────────────────────────────────────────
def get_available_dates(tab_name: str):
    df = load_tab(tab_name)
    if df.empty or "Date" not in df.columns:
        return []
    return sorted(df["Date"].unique().tolist(), reverse=True)


# ── Main Layout ───────────────────────────────────────────────────────────────
st.title("📈 Market Monitor")

# Date picker row
col_date, col_refresh, col_spacer = st.columns([2, 1, 7])
with col_date:
    selected_date = st.date_input(
        "📅 Date",
        value=date.today(),
        max_value=date.today(),
        min_value=date.today() - timedelta(days=365),
    )
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

date_str = selected_date.strftime("%Y-%m-%d")

st.markdown("---")

# Main tabs
tab_eod, tab_eve, tab_pre, tab_wl = st.tabs([
    "🔔 EOD Scan  (4:30 PM)",
    "🌙 Evening Scan  (8:15 PM)",
    "🌅 Pre-Market  (8:00 AM)",
    "⭐ Watchlist",
])

with tab_eod:
    render_scan_tab("EOD", "EOD", date_str)

with tab_eve:
    render_scan_tab("Evening", "Evening", date_str)

with tab_pre:
    render_scan_tab("PreMarket", "PreMarket", date_str)

with tab_wl:
    render_watchlist_tab()
