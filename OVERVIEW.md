# Market Monitor — Project Overview

Automated stock scanner that flags unusual price moves and volume spikes across regular trading hours, after-hours, and pre-market sessions — runs on a schedule via GitHub Actions and logs results to Google Sheets, with a Streamlit dashboard for review.

## Why

Significant stock moves often happen outside regular trading hours — on earnings releases, news, or guidance updates — and can be easy to miss. This project automatically scans a broad universe of liquid stocks at key points in the trading day (end of day, evening, and pre-market) and surfaces names with abnormal volume and price action, along with the likely news catalyst.

## How it works

The scanner pulls daily and intraday price/volume data via `yfinance` for a combined universe of S&P 500 and Nasdaq 100 tickers (~550 unique symbols), then applies different filters depending on the scan mode:

- **EOD scan** — flags stocks with average daily volume above 3M shares and a same-day price move of at least 4%.
- **Evening scan** — same move threshold, but with a lower volume bar (100k shares) to catch smaller-cap movers.
- **Pre-market scan** — uses extended-hours data (`prepost=True`) to catch pre-market movers with at least 50k volume and a 2% move.

For each qualifying ticker, the script computes:
- Price change %
- Volume vs. 20-day average volume ("volume ratio")
- Company name and sector
- A news headline (top Yahoo Finance story) as a likely catalyst

Results are sorted by % change and appended to a dedicated tab in a Google Sheet (`EOD`, `Evening`, or `PreMarket`), so historical scans accumulate over time and can be reviewed or charted later.

## Architecture

- **`scan.py`** — core scanning logic, run via CLI with `--mode eod|evening|premarket`
- **`dashboard.py`** — Streamlit app for browsing scan results
- **`.github/workflows/`** — GitHub Actions workflows that run the scans on a schedule (pre-market, end-of-day, evening)
- **Google Sheets** — acts as the data store / log for all scan results, using a service account for authentication

### Dashboard

The dashboard is a Streamlit app with three scan tabs (EOD, Evening, Pre-Market) plus a Watchlist tab:

- **Date picker** to browse historical scan results for any day in the last year
- **Summary metrics** per scan — total movers, count of gainers vs. decliners, and average volume ratio
- **Up/down filter** to quickly narrow to gainers or decliners
- **Color-coded table** (green/red) for price moves and direction, with the news catalyst shown alongside each ticker
- **Watchlist**: select rows with a checkbox and add them to a persistent Watchlist tab in the spreadsheet, with duplicate-ticker detection so the same stock isn't added twice
- **Watchlist view** supports filtering by date added and by which scan it came from (EOD / Evening / PreMarket)

Data is cached for 5 minutes to avoid hitting the Google Sheets API on every interaction, with a manual refresh button to force a reload.

## Setup

**For the scanner (`scan.py`):**

1. Install dependencies:
```bash
   pip install -r requirements.txt
```

2. Create a Google Cloud service account with access to the Sheets and Drive APIs, and share your target spreadsheet with the service account email.

3. Set environment variables:
```bash
   export GOOGLE_CREDENTIALS='<service account JSON>'
   export SPREADSHEET_ID='<your spreadsheet id>'
```

**For the dashboard (`dashboard.py`):**

Add the service account credentials and spreadsheet ID to Streamlit secrets (`.streamlit/secrets.toml`):

```toml
spreadsheet_id = "<your spreadsheet id>"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key = "..."
client_email = "..."
# ...remaining service account fields
```

## Usage

Run a specific scan manually:

```bash
python scan.py --mode eod
python scan.py --mode evening
python scan.py --mode premarket
```

In production, these are triggered automatically by the GitHub Actions workflows on a schedule (pre-market open, market close, and evening).

Launch the dashboard:

```bash
streamlit run dashboard.py
```

## Notes / Roadmap

- Ticker universe is currently hardcoded (S&P 500 + Nasdaq 100); could be made dynamic via an index constituents API.
- Catalyst detection relies on the top Yahoo Finance headline; could be expanded to pull from multiple news sources.
- Possible next steps: alerting (email/SMS/Telegram) when new movers are found, backtesting scan criteria against historical performance, and watchlist performance tracking (e.g. how watchlist picks perform after being added).
