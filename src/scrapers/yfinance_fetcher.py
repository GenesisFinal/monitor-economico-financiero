import requests
import json
import time
import math
import os
from datetime import datetime, timedelta
from src.utils.formatters import *
from src.utils.math_utils import *
from src.utils.dates import *
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import traceback
import unicodedata
import re

def scrape_cnbc_current(symbol):

    """Scrapes current yield and nominal change from CNBC."""

    url = f"https://www.cnbc.com/quotes/{symbol}"

    headers = {

        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    }

    try:

        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code == 200:

            soup = BeautifulSoup(r.text, 'html.parser')

            price_element = soup.find(class_="QuoteStrip-lastPrice")

            change_element = (soup.find(class_="QuoteStrip-changeUp") or 

                              soup.find(class_="QuoteStrip-changeDown") or

                              soup.find(class_="QuoteStrip-changeUnchanged"))

            

            if price_element:

                price_str = price_element.text.replace('%', '').strip()

                price = float(price_str)

                

                change_val = 0.0

                if change_element:

                    change_str = change_element.text.replace('%', '').replace('+', '').strip()

                    try:

                        change_val = float(change_str)

                        if "changeDown" in str(change_element.get('class')):

                            change_val = -abs(change_val)

                    except ValueError:

                        pass

                return price, change_val

    except Exception as e:

        print(f"Error scraping CNBC {symbol}: {e}")

    return None, None







def fetch_yfinance_and_histories(tickers_map, dolar_api_data, oficial_series=None):

    """

    Downloads current prices and 5-year histories (daily & weekly)

    for all Yahoo Finance tickers one by one to avoid pandas concat hangs.

    """

    from datetime import datetime, timedelta

    import yfinance as yf

    import pandas as pd

    import time

    

    dolar_oficial_venta = 1450.0

    if 'oficial' in dolar_api_data:

        dolar_oficial_venta = dolar_api_data['oficial']['venta']

        

    tickers_list = list(tickers_map.keys())

    print(f"Downloading {len(tickers_list)} tickers from Yahoo Finance sequentially...")

    

    current_prices = {}

    historical_db = {}

    limit_daily = datetime.now() - timedelta(days=3*365)

    

    for i, (t_symbol, label) in enumerate(tickers_map.items()):

        try:

            if i % 10 == 0:

                print(f"  Progress: {i}/{len(tickers_list)} downloaded...")

                

            single_df = yf.download(t_symbol, period="5y", interval="1d", progress=False)

            

            if single_df.empty or 'Close' not in single_df.columns:

                print(f"  Warning: Empty data for {t_symbol}")

                continue

                

            # Flatten multi-index columns if yfinance returns them

            if isinstance(single_df.columns, pd.MultiIndex):

                single_df.columns = single_df.columns.get_level_values(0)

                

            factor = 1.0

            if t_symbol == "ZS=F":

                factor = 36.7437 / 100.0

            elif t_symbol == "ZC=F":

                factor = 39.368 / 100.0

            elif t_symbol == "ZW=F":

                factor = 36.7437 / 100.0

            elif t_symbol in ["CT=F", "KC=F", "SB=F", "OJ=F"]:

                factor = 1.0 / 100.0

                

            close_series = single_df['Close'].dropna()

            if not close_series.empty:

                close_series = close_series * factor

                open_series = single_df['Open'].reindex(close_series.index) * factor

                high_series = single_df['High'].reindex(close_series.index) * factor

                low_series = single_df['Low'].reindex(close_series.index) * factor

                

                # Extract current price and calculate variations

                last_price = close_series.iloc[-1]

                vars_dict = calculate_variations(close_series)

                

                current_prices[t_symbol] = {

                    "name": label,

                    "ticker": t_symbol,

                    "price": round(float(last_price), 4) if t_symbol in ["EURUSD=X", "GBPUSD=X", "AUDUSD=X"] else round(float(last_price), 2),

                    "change": vars_dict["change"],

                    "change_1m": vars_dict["change_1m"],

                    "change_12m": vars_dict["change_12m"],

                    "change_ytd": vars_dict["change_ytd"]

                }

                

                daily_idx = close_series.index[close_series.index >= limit_daily]

                

                weekly_close = close_series.resample('W').last()

                weekly_open = open_series.resample('W').first()

                weekly_high = high_series.resample('W').max()

                weekly_low = low_series.resample('W').min()

                

                historical_db[t_symbol] = {

                    "daily": {

                        "dates": [d.strftime('%Y-%m-%d') for d in daily_idx],

                        "prices": [round(float(v), 2) for v in close_series.reindex(daily_idx).values],

                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in open_series.reindex(daily_idx).values],

                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in high_series.reindex(daily_idx).values],

                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in low_series.reindex(daily_idx).values],

                        "close": [round(float(v), 2) if not pd.isna(v) else None for v in close_series.reindex(daily_idx).values],

                    },

                    "weekly": {

                        "dates": [d.strftime('%Y-%m-%d') for d in weekly_close.index],

                        "prices": [round(float(v), 2) for v in weekly_close.values],

                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in weekly_open.values],

                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in weekly_high.values],

                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in weekly_low.values],

                        "close": [round(float(v), 2) if not pd.isna(v) else None for v in weekly_close.values],

                    }

                }

        except Exception as ex:

            print(f"Warning: Failed processing history for {t_symbol}: {ex}")

            

    print(f"Successfully processed {len(current_prices)} tickers from Yahoo Finance.")

    return current_prices, historical_db



