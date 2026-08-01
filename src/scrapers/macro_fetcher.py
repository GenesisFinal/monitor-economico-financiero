import requests
import json
import time
import math
import os
from datetime import datetime, timedelta
from src.utils.formatters import *
from src.utils.math_utils import *
from src.utils.dates import *
import io
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import unicodedata
import re


def fetch_fred_monthly_with_retry(symbol, retries=4, delay=2, timeout=15):
    """Downloads monthly sovereign yield data from FRED with retries and timeout."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={symbol}"
    for i in range(retries):
        print(f"  Attempt {i+1} downloading {symbol} from FRED...")
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                df.columns = ['date', 'value']
                df = df[df['value'] != '.']
                df['value'] = pd.to_numeric(df['value'])
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df['value'].sort_index()
            else:
                print(f"    Status code: {r.status_code}")
        except Exception as e:
            print(f"    Error on attempt {i+1} for {symbol}: {e}")
        time.sleep(delay)
    print(f"  Warning: Failed to fetch FRED symbol {symbol} after {retries} attempts.")
    return pd.Series(dtype=float)

def fetch_country_risk_history():
    """Fetches 5-year country risk history from ArgentinaDatos."""
    try:
        url = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df['fecha'] = pd.to_datetime(df['fecha'])
            df.set_index('fecha', inplace=True)
            df_risk = df['valor'].dropna().sort_index()

            # Daily (last 3 years to support 2A period view)
            daily = df_risk[df_risk.index >= (datetime.now() - timedelta(days=3*365))]
            # Weekly (5 years)
            weekly = df_risk[df_risk.index >= (datetime.now() - timedelta(days=5*365))].resample('W').last()

            return {
                "latest": int(df_risk.iloc[-1]) if not df_risk.empty else None,
                "date": df_risk.index[-1].strftime('%Y-%m-%d') if not df_risk.empty else None,
                "history": {
                    "daily": {
                        "dates": [d.strftime('%Y-%m-%d') for d in daily.index],
                        "prices": [int(v) for v in daily.values]
                    },
                    "weekly": {
                        "dates": [d.strftime('%Y-%m-%d') for d in weekly.index],
                        "prices": [int(v) for v in weekly.values]
                    }
                }
            }
    except Exception as e:
        print(f"Error fetching country risk: {e}")
    return {"latest": None, "date": None, "history": {"daily": {"dates": [], "prices": []}, "weekly": {"dates": [], "prices": []}}}

def fetch_bcra_rate(var_id):
    """Fetches historical and current rate from the BCRA API."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    url = f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{var_id}"
    try:
        r = requests.get(url, verify=False, timeout=12)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if len(results) > 0:
                detalle = results[0].get("detalle", [])
                if len(detalle) > 0:
                    sorted_det = sorted(detalle, key=lambda x: x.get('fecha', ''))

                    dates = [item['fecha'] for item in sorted_det]
                    prices = [float(item['valor']) for item in sorted_det]

                    # Forward-fill if the last date is older than today and the gap is within 15 days (active series)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    if dates and dates[-1] < today_str:
                        last_dt = datetime.strptime(dates[-1], '%Y-%m-%d').date()
                        today_dt = datetime.now().date()
                        if (today_dt - last_dt).days <= 15:
                            curr_dt = last_dt + timedelta(days=1)
                            while curr_dt <= today_dt:
                                dates.append(curr_dt.strftime('%Y-%m-%d'))
                                prices.append(prices[-1])
                                curr_dt += timedelta(days=1)

                    current_val = prices[-1]
                    orig_prices = [float(item['valor']) for item in sorted_det]
                    prev_val = orig_prices[-2] if len(orig_prices) > 1 else current_val
                    change = ((orig_prices[-1] - prev_val) / prev_val) * 100 if prev_val else 0.0

                    return current_val, change, {"dates": dates, "prices": prices}
    except Exception as e:
        print(f"Warning: Failed to fetch BCRA rate for ID {var_id}: {e}")
    return 0.0, 0.0, {"dates": [], "prices": []}

