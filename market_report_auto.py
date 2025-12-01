#!/usr/bin/env python3
"""Market report: yfinance for futures + TradingEconomics public scraping.
Generates CSV and PDF and optionally emails via SMTP.
"""
import os, time, random, logging, re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

try:
    import yfinance as yf
except Exception:
    yf = None

from email.message import EmailMessage
import smtplib, ssl

OUT = Path('reports')
OUT.mkdir(exist_ok=True)
LOG = logging.getLogger('market_report')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

def cents_per_lb_to_usd_per_kg(cents):
    return (cents / 100.0) / 0.45359237

def usd_per_tonne_to_usd_per_kg(v):
    return v / 1000.0

def usd_per_bushel_corn_to_usd_per_kg(v):
    return v / 25.4

def usd_per_bushel_soy_to_usd_per_kg(v):
    return v / 27.2155

HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_te_public(slug):
    url = f'https://tradingeconomics.com/commodity/{slug}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        selectors = ['.tradingeconomics-widget .value', '.indicator .value', '.last', '.quote-value', '.value']
        text = None
        for sel in selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                text = el.get_text(strip=True)
                break
        if not text:
            meta = soup.find('meta', {'name':'twitter:data1'}) or soup.find('meta', {'property':'og:description'})
            if meta and meta.get('content'):
                text = meta.get('content')
        if not text:
            return None, None
        txt = text.replace('\xa0',' ').replace(',','').strip()
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)', txt)
        if m:
            price = float(m.group(1))
            unit = txt[m.end():].strip() or None
            return price, unit
    except Exception as e:
        LOG.exception('TE fetch error: %s', e)
    finally:
        time.sleep(0.6 + random.random()*0.6)
    return None, None

def fetch_yf_price(ticker):
    if yf is None:
        LOG.warning('yfinance not available')
        return None
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period='400d', auto_adjust=False)
        if hist is None or hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception as e:
        LOG.exception('yfinance error: %s', e)
        return None

def collect_all():
    data = {}
    mapping = {'Arabica':'KC=F','Cocoa':'CC=F','Corn':'ZC=F','Soybeans':'ZS=F'}
    for name,t in mapping.items():
        p = fetch_yf_price(t)
        if p is not None:
            # Correct units for futures:
# KC=F (Arabica) is quoted in cents per pound (¢/lb)
if t == 'KC=F':
    unit = '¢/lb'
elif t in ('ZC=F', 'ZS=F'):
    unit = 'USD/bushel'
else:
    unit = 'USD/tonne'
            data[name] = {'instrument':t,'price':p,'unit':unit,'source':'yfinance'}
    te_map = {'Robusta':'robusta','Vanilla Natural':'vanilla','Dry Beans':'dry-beans','Onions':'onions','Pineapples':'pineapples','Bananas':'bananas'}
    for name,slug in te_map.items():
        p,u = fetch_te_public(slug)
        if p is not None:
            data[name] = {'instrument':f'TE:{slug}','price':p,'unit':u or 'USD/tonne','source':'tradingeconomics'}
    demo = {'Arabica':{'price':403.14,'unit':'¢/lb'},'Robusta':{'price':4506,'unit':'USD/tonne'},'Cocoa':{'price':2700,'unit':'USD/tonne'},'Corn':{'price':520,'unit':'USD/bushel'},'Soybeans':{'price':1200,'unit':'USD/bushel'},'Vanilla Natural':{'price':160,'unit':'USD/kg'},'Dry Beans':{'price':900,'unit':'USD/tonne'},'Onions':{'price':0.8,'unit':'USD/kg'},'Pineapples':{'price':400,'unit':'USD/tonne'},'Bananas':{'price':600,'unit':'USD/tonne'}}
    for k,v in demo.items():
        if k not in data:
            data[k] = {'instrument':'demo','price':v['price'],'unit':v['unit'],'source':'demo'}
    return data

def convert_to_usdkg(price,unit,name=''):
    if unit is None:
        if price>1000:
            return price/1000.0
        return price
    u = unit.lower()
    if '¢/lb' in u or 'cent' in u:
        return cents_per_lb_to_usd_per_kg(price)
    if 'lb' in u:
        return price/0.45359237
    if 'bushel' in u:
        if 'corn' in name.lower():
            return usd_per_bushel_corn_to_usd_per_kg(price)
        if 'soy' in name.lower():
            return usd_per_bushel_soy_to_usd_per_kg(price)
    if 'tonne' in u or 'ton' in u:
        return usd_per_tonne_to_usd_per_kg(price)
    if 'kg' in u:
        return float(price)
    return price

def generate_report(data):
    rows=[]
    for name,info in data.items():
        usdkg = convert_to_usdkg(info['price'], info.get('unit'), name)
        rows.append({'culture':name,'instrument':info.get('instrument'),'raw_price':info.get('price'),'raw_unit':info.get('unit'),'USD_per_kg':round(usdkg,4),'source':info.get('source')})
    df = pd.DataFrame(rows)
    snapshot = datetime.utcnow().date().isoformat()
    csvp = OUT / f'market_report_{snapshot}.csv'
    pdfp = OUT / f'market_report_{snapshot}.pdf'
    df.to_csv(csvp,index=False)
    with plt.rc_context({'figure.max_open_warning': 0}):
        from matplotlib.backends.backend_pdf import PdfPages
        with PdfPages(pdfp) as pdf:
            fig,ax = plt.subplots(figsize=(8.27,11.69))
            ax.axis('off')
            ax.text(0.02,0.9,f'Market Report — {snapshot}', fontsize=14)
            pdf.savefig(); plt.close()
            fig,ax = plt.subplots(figsize=(11,6))
            ax.axis('off')
            tbl = ax.table(cellText=df[['culture','raw_price','raw_unit','USD_per_kg','source']].values, colLabels=['culture','raw_price','raw_unit','USD_per_kg','source'], loc='center')
            tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1,1.2)
            pdf.savefig(); plt.close()
    return csvp, pdfp

def send_email(to, files):
    SMTP_HOST = os.getenv('SMTP_HOST')
    SMTP_PORT = int(os.getenv('SMTP_PORT') or 587)
    SMTP_USER = os.getenv('SMTP_USER')
    SMTP_PASS = os.getenv('SMTP_PASS')
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        LOG.warning('SMTP not configured, skipping send')
        return
    msg = EmailMessage()
    msg['Subject'] = 'Market report'
    msg['From'] = SMTP_USER
    msg['To'] = to
    msg.set_content('Attached')
    for f in files:
        with open(f,'rb') as fh:
            data = fh.read()
        msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=Path(f).name)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls(context=ctx)
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    LOG.info('Email sent to %s', to)

def main():
    LOG.info('Collecting data...')
    data = collect_all()
    csvp,pdfp = generate_report(data)
    LOG.info('Wrote %s and %s', csvp, pdfp)
    report_to = os.getenv('REPORT_TO') or 'ldutos@gmail.com'
    send_email(report_to, [str(csvp), str(pdfp)])

if __name__ == '__main__':
    main()
