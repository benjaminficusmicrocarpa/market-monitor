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
    """S&P 500 + Nasdaq 100 combined, deduplicated. Hardcoded for reliability."""
    print("Building ticker universe...")

    sp500 = [
        "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB","AKAM",
        "ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN","AMCR","AEE",
        "AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH","ADI","ANSS","AON",
        "APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG","AIZ","T","ATO","ADSK","ADP",
        "AZO","AVB","AVY","AXON","BKR","BALL","BAC","BK","BBWI","BAX","BDX","BRK-B","BBY",
        "BIO","TECH","BIIB","BLK","BX","BA","BCH","BWA","BXP","BSX","BMY","AVGO","BR",
        "BRO","BF-B","BLDR","BG","CDNS","CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR",
        "CTLT","CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNX","CDAY","CF","CRL","SCHW",
        "CHTR","CVX","CMG","CB","CHD","CI","CINF","CTAS","CSCO","C","CFG","CLX","CME",
        "CMS","KO","CTSH","CL","CMCSA","CMA","CAG","COP","ED","STZ","CEG","COO","CPRT",
        "GLW","CTVA","CSGP","COST","CTRA","CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY",
        "DE","DAL","XRAY","DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV",
        "DOW","DHI","DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV","LLY",
        "EMR","ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG",
        "EVRG","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX",
        "FIS","FITB","FSLR","FE","FI","FMC","F","FTNT","FTV","FOXA","FOX","BEN","FCX",
        "GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD","GPN",
        "GL","GDDY","GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT",
        "HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX",
        "IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG","IVZ",
        "INVH","IQV","IRM","JBHT","JBL","JKHY","J","JNJ","JCI","JPM","JNPR","K","KVUE",
        "KDP","KEY","KEYS","KMB","KIM","KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW",
        "LVS","LDOS","LEN","LNC","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB",
        "MRO","MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT",
        "MRK","META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP",
        "MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NOV","NWSA",
        "NWS","NEE","NKE","NEM","NFLX","NWL","NRG","NUE","NVDA","NVR","NXPI","ORLY","OXY",
        "ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PLTR","PH","PAYX","PAYC","PYPL",
        "PNR","PEP","PFE","PCG","PM","PSX","PNW","PXD","PNC","POOL","PPG","PPL","PFG",
        "PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","QRVO","PWR","QCOM","DGX","RL",
        "RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST",
        "RCL","SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM","SNA",
        "SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK","SMCI","SYF","SNPS","SYY",
        "TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL","TDY","TFX","TER","TSLA","TXN",
        "TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB","TFC","TYL","TSN","USB","UBER",
        "UDR","ULTA","UNP","UAL","UPS","URI","UNH","UHS","VLO","VTR","VLTO","VRSN","VRSK",
        "VZ","VRTX","VTRS","VICI","V","VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS",
        "WBD","WM","WAT","WEC","WFC","WELL","WST","WDC","WY","WMB","WTW","WYNN","XEL",
        "XYL","YUM","ZBRA","ZBH","ZTS",
    ]

    nasdaq100 = [
        "ADBE","AMD","ABNB","GOOGL","GOOG","AMZN","AMGN","AEP","AAPL","AMAT",
        "ASML","TEAM","ADSK","AZN","ATVI","BIDU","BIIB","BKNG","AVGO","CDNS",
        "CHTR","CTAS","CSCO","CTSH","CMCSA","CEG","CPRT","CSGP","COST","CRWD",
        "CSX","DDOG","DXCM","FANG","DLTR","EBAY","EA","EXC","FAST","META","FI",
        "FTNT","GILD","HON","IDXX","ILMN","INTC","INTU","ISRG","MRVL","KLAC",
        "KDP","KHC","LRCX","LULU","MELI","MDLZ","MRNA","MSFT","MU","NFLX","NVDA",
        "NXPI","ORLY","ODFL","ON","PCAR","PANW","PAYX","PYPL","PDD","QCOM","REGN",
        "ROST","CRM","SBUX","SNPS","TMUS","TSLA","TXN","TTD","VRSK","VRTX","WBA",
        "WDAY","WBD","ZS","ZM","OKTA","COIN","HOOD","RBLX","DKNG","RIVN","LCID",
        "UBER","LYFT","DASH","ABNB","SHOP","SQ","ROKU","SPOT","PINS","SNAP",
    ]

    unique = list(set(sp500 + nasdaq100))
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
