Market Report Automation — full project (Variant 1)

This archive contains a ready-to-run weekly market report:
- market_report_auto.py — full script using yfinance + public TradingEconomics scraping
- requirements.txt
- .github/workflows/send_report.yml (weekly schedule + manual run)
- assets/logo.png
- .env.example

Quickstart:
1. Copy .env.example -> .env and fill SMTP + REPORT_TO.
2. python3 -m venv venv && source venv/bin/activate
3. pip install -r requirements.txt
4. python market_report_auto.py

To run in GitHub Actions: upload this repo to your GitHub, add Secrets (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, REPORT_TO), then trigger workflow manually or wait for scheduled run.
