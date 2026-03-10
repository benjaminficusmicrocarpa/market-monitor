"""
Market Monitor — Scan Script
Modes: eod | evening | premarket
Run by GitHub Actions on schedule, writes results to Google Sheets.
"""

import argparse
import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import json
import os
import time

# ── Config ────────────────────────────────────────────────────────────────────
EOD_MIN_AVG_VOL     = 3_000_000   # 3M avg daily volume for EOD scan
EVENING_MIN_VOL     = 100_000     # 100k volume for evening scan
PREMARKET_MIN_VOL   = 50_000      # 50k for pre-market scan
DAILY_MOVE_PCT      = 4.0         # minimum % move to qualify
PREMARKET_MOVE_PCT  = 2.0         # lower bar for pre-market
HEADLINE_MAX_CHARS  = 130         # truncate catalyst headline

# ── Universe ──────────────────────────────────────────────────────────────────
def get_universe():
    """S&P 500 + Nasdaq 100 combined, deduplicated."""
    print("Building ticker universe...")
    tickers = []

    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        tickers += sp500["Symbol"].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"  Warning: Could not fetch S&P 500 list: {e}")

    try:
        nq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        tickers += nq100["Ticker"].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"  Warning: Could not fetch Nasdaq 100 list: {e}")

    unique = list(set(tickers))
    print(f"  Universe size: {len(unique)} tickers")
    return unique


# ── Google Sheets ─────────────────────────────────────────────────────────────
def get_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    return gspread.authorize(creds)


def write_to_sheet(client, spreadsheet_id, tab_name, df):
    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=5000, cols=15)

    existing = ws.get_all_values()
    if not existing:
        ws.append_row(list(df.columns), value_input_option="USER_ENTERED")

    rows = [[str(v) for v in row] for row in df.values.tolist()]
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"  ✓ Wrote {len(rows)} rows → '{tab_name}'")


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_catalyst(ticker):
    """Fetch top news headline for a ticker from Yahoo Finance."""
    try:
        news = yf.Ticker(ticker).news
        if news:
            item = news[0]
            # Handle both old and new yfinance response formats
            title = (
                item.get("content", {}).get("title")
                or item.get("title")
                or ""
            )
            return title[:HEADLINE_MAX_CHARS] if title else "—"
    except Exception:
        pass
    return "—"


def get_company_info(ticker):
    """Return (short_name, sector) for a ticker."""
    try:
        info = yf.Ticker(ticker).fast_info
        # fast_info is lightweight; fall back to full info for sector
        full = yf.Ticker(ticker).info
        name   = full.get("shortName") or full.get("longName") or ticker
        sector = full.get("sector") or "—"
        return name, sector
    except Exception:
        return ticker, "—"


# ── EOD & Evening Scan ────────────────────────────────────────────────────────
def run_regular_scan(mode, tickers, run_date, client, spreadsheet_id):
    min_avg_vol = EOD_MIN_AVG_VOL if mode == "eod" else EOD_MIN_AVG_VOL
    min_today_vol = EOD_MIN_AVG_VOL if mode == "eod" else EVENING_MIN_VOL

    print(f"Downloading 30-day price data for {len(tickers)} tickers...")
    raw = yf.download(
        tickers,
        period="30d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    rows = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw
            else:
                if ticker not in raw.columns.get_level_values(0):
                    continue
                df = raw[ticker]

            df = df.dropna(subset=["Close", "Volume"])
            if len(df) < 5:
                continue

            avg_vol     = df["Volume"].tail(20).mean()
            close       = float(df["Close"].iloc[-1])
            prev_close  = float(df["Close"].iloc[-2])
            today_vol   = float(df["Volume"].iloc[-1])
            chg_pct     = (close - prev_close) / prev_close * 100

            # Volume filters
            if avg_vol < min_avg_vol:
                continue
            if today_vol < min_today_vol:
                continue

            # Move filter
            if abs(chg_pct) < DAILY_MOVE_PCT:
                continue

            vol_ratio   = round(today_vol / avg_vol, 1) if avg_vol > 0 else 0
            company, sector = get_company_info(ticker)
            catalyst    = get_catalyst(ticker)
            time.sleep(0.05)

            rows.append({
                "Date":       run_date,
                "Ticker":     ticker,
                "Company":    company,
                "Sector":     sector,
                "Close":      round(close, 2),
                "Change %":   round(chg_pct, 2),
                "Volume":     int(today_vol),
                "Avg Volume": int(avg_vol),
                "Vol Ratio":  vol_ratio,
                "Direction":  "UP" if chg_pct > 0 else "DOWN",
                "Catalyst":   catalyst,
            })

        except Exception as e:
            continue

    tab = "EOD" if mode == "eod" else "Evening"
    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("Change %", ascending=False)
    print(f"  Found {len(rows)} qualifying movers")
    write_to_sheet(client, spreadsheet_id, tab, df_out)


# ── Pre-Market Scan ───────────────────────────────────────────────────────────
def run_premarket_scan(tickers, run_date, client, spreadsheet_id):
    print(f"Downloading pre/after-hours data for {len(tickers)} tickers...")
    raw = yf.download(
        tickers,
        period="5d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
        prepost=True,
    )

    rows = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw
            else:
                if ticker not in raw.columns.get_level_values(0):
                    continue
                df = raw[ticker]

            df = df.dropna(subset=["Close", "Volume"])
            if len(df) < 2:
                continue

            close       = float(df["Close"].iloc[-1])
            prev_close  = float(df["Close"].iloc[-2])
            vol         = float(df["Volume"].iloc[-1])
            chg_pct     = (close - prev_close) / prev_close * 100

            if vol < PREMARKET_MIN_VOL:
                continue
            if abs(chg_pct) < PREMARKET_MOVE_PCT:
                continue

            company, sector = get_company_info(ticker)
            catalyst    = get_catalyst(ticker)
            time.sleep(0.05)

            rows.append({
                "Date":           run_date,
                "Ticker":         ticker,
                "Company":        company,
                "Sector":         sector,
                "Pre-Mkt Price":  round(close, 2),
                "Change %":       round(chg_pct, 2),
                "Volume":         int(vol),
                "Direction":      "UP" if chg_pct > 0 else "DOWN",
                "Catalyst":       catalyst,
            })

        except Exception:
            continue

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("Change %", ascending=False)
    print(f"  Found {len(rows)} pre-market movers")
    write_to_sheet(client, spreadsheet_id, "PreMarket", df_out)


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["eod", "evening", "premarket"], required=True,
                        help="Which scan to run")
    args = parser.parse_args()

    run_date = date.today().strftime("%Y-%m-%d")
    print(f"\n=== Market Monitor [{args.mode.upper()}] | {run_date} ===\n")

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ValueError("SPREADSHEET_ID environment variable is not set.")

    tickers = get_universe()
    client  = get_gsheet_client()

    if args.mode in ("eod", "evening"):
        run_regular_scan(args.mode, tickers, run_date, client, spreadsheet_id)
    else:
        run_premarket_scan(tickers, run_date, client, spreadsheet_id)

    print(f"\n✅ {args.mode.upper()} scan complete.\n")


if __name__ == "__main__":
    main()
