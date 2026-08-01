import requests
import json
import time
import math
import os
from datetime import datetime, timedelta, date
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


def is_supported_sovereign_bond(ticker, family):
    t = ticker.upper()
    # USD Bonds ending with D (USD settlement version)
    if family.startswith('BONO-USD-') or family == 'BONO-USD':
        return t.endswith('D')

    # CER Bonds
    if family in ['BONO-CER', 'LETRAS-CER']:
        return True

    # Peso / BADLAR / Dual / Dollar-Linked Bonds (exclude LECAPs/BONCAPs starting with S/T followed by digit)
    if family in ['BONO-FIJA', 'BONO-BADLAR', 'LETRAS-FIJO', 'DOLAR-LINKED', 'DUAL', 'TAMAR-FIJA', 'BONO-TAMAR', 'BONO-DUAL-TAMAR', 'DUAL-CER-TAMAR', 'BOPREAL-PESOS']:
        if len(t) >= 2 and t[0] in ['S', 'T'] and t[1].isdigit():
            return False
        return True

    return False

def fetch_bond_data():
    """
    Fetches sovereign bond and corporate ON data from Bonistas.com.
    Selects the top 6 soberanos (CER, USD, Pesos) with valid historical curves,
    and the top 10 ONs (Hard Dollar).
    """
    url = "https://bonistas.com/bonos-cer-hoy"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    bonds_cer = []
    bonds_usd = []
    bonds_pesos = []
    ons_hard_dollar = []

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if script:
                raw_json = json.loads(script.string)
                bond_list = raw_json['props']['pageProps']['bondData']

                # Classify Bonds
                for b in bond_list:
                    # Sanitize name typos (like "ono " instead of "Bono ")
                    sd = b.get("short_description") or ""
                    if sd.startswith("ono "):
                        b["short_description"] = "B" + sd
                    n = b.get("name") or ""
                    if n.startswith("ono "):
                        b["name"] = "B" + n

                    fam = b.get('bond_family', '') or ''
                    ticker = b.get('ticker', '') or ''

                    if is_supported_sovereign_bond(ticker, fam):
                        if fam in ['BONO-CER', 'LETRAS-CER']:
                            bonds_cer.append(b)
                        elif fam.startswith('BONO-USD-') or fam == 'BONO-USD':
                            bonds_usd.append(b)
                        elif fam in ['BONO-FIJA', 'BONO-BADLAR', 'LETRAS-FIJO', 'DOLAR-LINKED', 'DUAL', 'TAMAR-FIJA', 'BONO-TAMAR', 'BONO-DUAL-TAMAR', 'DUAL-CER-TAMAR', 'BOPREAL-PESOS']:
                            bonds_pesos.append(b)
                    elif fam in ['ONS', 'ONS-CABLE'] and ticker.endswith('D'):
                        ons_hard_dollar.append(b)


                # Sort all candidates by volume and deduplicate
                bonds_cer = deduplicate(sorted(bonds_cer, key=lambda x: x.get('volume') or 0, reverse=True))
                bonds_usd = deduplicate(sorted(bonds_usd, key=lambda x: x.get('volume') or 0, reverse=True))
                bonds_pesos = deduplicate(sorted(bonds_pesos, key=lambda x: x.get('volume') or 0, reverse=True))
                ons_hard_dollar = deduplicate(sorted(ons_hard_dollar, key=lambda x: x.get('volume') or 0, reverse=True))[:10]

                # Fallback for ONs Hard Dollar if the list is empty
                if not ons_hard_dollar:
                    print("Warning: No ONs Hard Dollar fetched from bonistas.com. Initializing with default hardcoded ONs.")
                    default_tickers = ['YM34D', 'YMCXD', 'MGCRD', 'VSCXD', 'PLC7D', 'VSCVD', 'CS44D', 'TTCED', 'MCC3D']
                    for t in default_tickers:
                        ons_hard_dollar.append({
                            "ticker": t,
                            "short_description": f"Bono Corporativo {t}",
                            "last_price": 100.0,
                            "day_difference": 0.0,
                            "emisor": "Generico",
                            "tir": 0.07,
                            "modified_duration": 3.5
                        })

                for b in ons_hard_dollar:
                    b['price'] = b.get('last_price') or 0.0
                    day_diff = b.get('day_difference')
                    b['change'] = float(day_diff) * 100.0 if day_diff is not None else 0.0
                    b['change_1m'] = '-'
                    b['change_ytd'] = '-'
                    b['change_12m'] = '-'
                    b['company'] = b.get('emisor') or 'N/A'
                    b_tir = b.get('tir')
                    b['tir'] = f"{float(b_tir)*100:.2f}%" if b_tir is not None else 'N/A'
                    b_dur = b.get('modified_duration')
                    b['duration'] = f"{float(b_dur):.2f}" if b_dur is not None else 'N/A'

    except Exception as e:
        print(f"Error scraping bonistas.com: {e}")
        # Complete fallback in case request failed entirely
        if not ons_hard_dollar:
            default_tickers = ['YM34D', 'YMCXD', 'MGCRD', 'VSCXD', 'PLC7D', 'VSCVD', 'CS44D', 'TTCED', 'MCC3D']
            for t in default_tickers:
                ons_hard_dollar.append({
                    "ticker": t,
                    "short_description": f"Bono Corporativo {t}",
                    "last_price": 100.0,
                    "day_difference": 0.0,
                    "emisor": "Generico",
                    "tir": 0.07,
                    "modified_duration": 3.5,
                    "price": 100.0,
                    "change": 0.0,
                    "change_1m": '-',
                    "change_ytd": '-',
                    "change_12m": '-',
                    "company": "Generico",
                    "tir_val": "7.00%",
                    "duration": "3.5"
                })

    # Indicative ONs in Pesos (CER / Dolar Linked)
    ons_cer_dl = [
        {"ticker": "MRCAD", "name": "Mastellone Clase G (Dólar Linked)", "price": 1450.0, "coupon": "3.00%", "duration": 1.4, "tir": "6.5% Est."},
        {"ticker": "TLC1D", "name": "Telecom Clase 1 (Dólar Linked)", "price": 1455.0, "coupon": "4.50%", "duration": 1.2, "tir": "7.0% Est."},
        {"ticker": "YMCYD", "name": "YPF Clase Y (Dólar Linked)", "price": 1460.0, "coupon": "5.00%", "duration": 2.1, "tir": "6.2% Est."},
        {"ticker": "CS38D", "name": "Cresud Clase 38 (Dólar Linked)", "price": 1445.0, "coupon": "3.50%", "duration": 1.8, "tir": "6.8% Est."},
        {"ticker": "RUC5O", "name": "Rua S.A. Clase V (Ajuste CER)", "price": 420.5, "coupon": "2.00% + CER", "duration": 0.8, "tir": "5.5% Real Est."},
        {"ticker": "SMC3O", "name": "San Miguel Clase III (Ajuste CER)", "price": 310.2, "coupon": "1.50% + CER", "duration": 1.1, "tir": "5.8% Real Est."}
    ]

    for b in ons_cer_dl:
        b['company'] = b.get('name', '').split(' ')[0]
        b['change'] = 0.0
        b['change_1m'] = '-'
        b['change_ytd'] = '-'
        b['change_12m'] = '-'


    historical_bonds = {}

    def get_bond_residual_factor(ticker, date_str):
        t = ticker.upper()
        if t.endswith('D') or t.endswith('C'):
            base_t = t[:-1]
        else:
            base_t = t

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return 1.0

        if base_t in ["AL30", "GD30"]:
            if dt < datetime(2024, 7, 8):
                return 1.0
            elif dt < datetime(2025, 1, 8):
                return 0.96
            elif dt < datetime(2025, 7, 8):
                return 0.88
            elif dt < datetime(2026, 1, 8):
                return 0.80
            elif dt < datetime(2026, 7, 8):
                return 0.72
            elif dt < datetime(2027, 1, 8):
                return 0.64
            elif dt < datetime(2027, 7, 8):
                return 0.56
            elif dt < datetime(2028, 1, 8):
                return 0.48
            elif dt < datetime(2028, 7, 8):
                return 0.40
            elif dt < datetime(2029, 1, 8):
                return 0.32
            elif dt < datetime(2029, 7, 8):
                return 0.24
            elif dt < datetime(2030, 1, 8):
                return 0.16
            elif dt < datetime(2030, 7, 8):
                return 0.08
            else:
                return 0.00

        elif base_t in ["AL29", "GD29"]:
            if dt < datetime(2025, 1, 8):
                return 1.00
            elif dt < datetime(2025, 7, 8):
                return 0.90
            elif dt < datetime(2026, 1, 8):
                return 0.80
            elif dt < datetime(2026, 7, 8):
                return 0.70
            elif dt < datetime(2027, 1, 8):
                return 0.60
            elif dt < datetime(2027, 7, 8):
                return 0.50
            elif dt < datetime(2028, 1, 8):
                return 0.40
            elif dt < datetime(2028, 7, 8):
                return 0.30
            elif dt < datetime(2029, 1, 8):
                return 0.20
            elif dt < datetime(2029, 7, 8):
                return 0.10
            else:
                return 0.00

        elif base_t == "TX26":
            if dt < datetime(2024, 11, 8):
                return 1.0
            elif dt < datetime(2025, 5, 8):
                return 0.80
            elif dt < datetime(2025, 11, 8):
                return 0.60
            elif dt < datetime(2026, 5, 8):
                return 0.40
            elif dt < datetime(2026, 11, 8):
                return 0.20
            else:
                return 0.00

        elif base_t == "TX28":
            if dt < datetime(2024, 5, 8):
                return 1.00
            elif dt < datetime(2024, 11, 8):
                return 0.90
            elif dt < datetime(2025, 5, 8):
                return 0.80
            elif dt < datetime(2025, 11, 8):
                return 0.70
            elif dt < datetime(2026, 5, 8):
                return 0.60
            elif dt < datetime(2026, 11, 8):
                return 0.50
            elif dt < datetime(2027, 5, 8):
                return 0.40
            elif dt < datetime(2027, 11, 8):
                return 0.30
            elif dt < datetime(2028, 5, 8):
                return 0.20
            elif dt < datetime(2028, 11, 8):
                return 0.10
            else:
                return 0.00

        elif base_t == "DICP":
            if dt < datetime(2024, 6, 28):
                return 1.0
            elif dt < datetime(2024, 12, 28):
                return 0.95
            elif dt < datetime(2025, 6, 28):
                return 0.90
            elif dt < datetime(2025, 12, 28):
                return 0.85
            elif dt < datetime(2026, 6, 28):
                return 0.80
            elif dt < datetime(2026, 12, 28):
                return 0.75
            elif dt < datetime(2027, 6, 28):
                return 0.70
            elif dt < datetime(2027, 12, 28):
                return 0.65
            elif dt < datetime(2028, 6, 28):
                return 0.60
            elif dt < datetime(2028, 12, 28):
                return 0.55
            elif dt < datetime(2029, 6, 28):
                return 0.50
            elif dt < datetime(2029, 12, 28):
                return 0.45
            elif dt < datetime(2030, 6, 28):
                return 0.40
            elif dt < datetime(2030, 12, 28):
                return 0.35
            elif dt < datetime(2031, 6, 28):
                return 0.30
            elif dt < datetime(2031, 12, 28):
                return 0.25
            elif dt < datetime(2032, 6, 28):
                return 0.20
            elif dt < datetime(2032, 12, 28):
                return 0.15
            elif dt < datetime(2033, 6, 28):
                return 0.10
            elif dt < datetime(2033, 12, 28):
                return 0.05
            else:
                return 0.00
        return 1.0

    # Self-healing validation helper to select the top candidates with valid history
    def validate_and_select_top(candidates, limit_count):
        selected = []
        for b in candidates:
            ticker = b.get('ticker')
            if not ticker:
                continue

            # Filter duration and DTM
            duration = b.get('modified_duration') or b.get('duration')
            dtm = b.get('days_to_finish') or b.get('dtm')

            try:
                dur_val = float(duration) if duration is not None else 1.0
            except ValueError:
                dur_val = 1.0

            if dtm is None:
                dtm_val = dur_val * 365.0
            else:
                try:
                    dtm_val = float(dtm)
                except ValueError:
                    dtm_val = dur_val * 365.0

            if dur_val < 0.20 or dtm_val < 45:
                continue

            if len(selected) >= limit_count:
                break

            dates, prices, opens, highs, lows = [], [], [], [], []
            url = f"https://data912.com/historical/bonds/{ticker}"
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    hist_data = r.json()
                    if isinstance(hist_data, list) and len(hist_data) > 0:
                        df_bond = pd.DataFrame(hist_data)
                        df_bond['date'] = pd.to_datetime(df_bond['date'])
                        df_bond.set_index('date', inplace=True)

                        df_close = df_bond['c'].dropna().sort_index()
                        if not df_close.empty:
                            dates = [d.strftime('%Y-%m-%d') for d in df_close.index]
                            prices = [float(v) for v in df_close.values]
                            opens = [float(v) if not pd.isna(v) else float(c) for v, c in zip(df_bond['o'].reindex(df_close.index).values, prices)] if 'o' in df_bond.columns else prices
                            highs = [float(v) if not pd.isna(v) else float(c) for v, c in zip(df_bond['h'].reindex(df_close.index).values, prices)] if 'h' in df_bond.columns else prices
                            lows = [float(v) if not pd.isna(v) else float(c) for v, c in zip(df_bond['l'].reindex(df_close.index).values, prices)] if 'l' in df_bond.columns else prices
            except Exception as e:
                print(f"Warning: data912 failed for {ticker}: {e}")

            # If data912 failed or empty, check Rava!
            if not dates or not prices:
                print(f"Checking Rava fallback history for {ticker}...")
                dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker)
                if not dates and ticker.endswith('D'):
                    dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker[:-1] + 'O')
                if not dates and ticker.endswith('O'):
                    dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker[:-1] + 'D')

            if dates and prices:
                # Adjust by residual factor
                factors = pd.Series(
                    [get_bond_residual_factor(ticker, d) for d in dates],
                    index=pd.to_datetime(dates)
                )
                factors = factors.apply(lambda x: x if x > 0.0 else 1.0)

                prices = [p / f for p, f in zip(prices, factors)]
                opens = [o / f for o, f in zip(opens, factors)]
                highs = [h / f for h, f in zip(highs, factors)]
                lows = [l / f for l, f in zip(lows, factors)]

                hist_series = pd.Series(prices, index=pd.to_datetime(dates)).sort_index()
                hist_series = hist_series[~hist_series.index.duplicated(keep='last')]
                vars_dict = calculate_variations(hist_series)

                b['change'] = vars_dict['change']
                b['change_1m'] = vars_dict['change_1m']
                b['change_12m'] = vars_dict['change_12m']
                b['change_ytd'] = vars_dict['change_ytd']

                limit_daily = datetime.now() - timedelta(days=3*365)
                daily_idx = hist_series.index[hist_series.index >= limit_daily]

                df_temp = pd.DataFrame({
                    "price": prices,
                    "open": opens,
                    "high": highs,
                    "low": lows
                }, index=pd.to_datetime(dates)).sort_index()
                df_temp = df_temp[~df_temp.index.duplicated(keep='last')]

                limit_weekly = datetime.now() - timedelta(days=5*365)
                df_weekly = df_temp[df_temp.index >= limit_weekly].resample('W').agg({
                    "price": "last",
                    "open": "first",
                    "high": "max",
                    "low": "min"
                })

                historical_bonds[ticker] = {
                    "daily": {
                        "dates": [d.strftime('%Y-%m-%d') for d in daily_idx],
                        "prices": [round(float(v), 2) for v in df_temp.loc[daily_idx, "price"].values],
                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "open"].values],
                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "high"].values],
                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "low"].values],
                        "close": [round(float(v), 2) for v in df_temp.loc[daily_idx, "price"].values],
                    },
                    "weekly": {
                        "dates": [d.strftime('%Y-%m-%d') for d in df_weekly.index],
                        "prices": [round(float(v), 2) for v in df_weekly["price"].values],
                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["open"].values],
                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["high"].values],
                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["low"].values],
                        "close": [round(float(v), 2) for v in df_weekly["price"].values],
                    }
                }
                selected.append(b)
            else:
                print(f"Warning: No history found on data912 or Rava for {ticker}. Using single-point fallback.")
                price_val = float(b.get('last_price') or b.get('precio') or 0.0)
                historical_bonds[ticker] = {
                    "daily": {"dates": [datetime.now().strftime('%Y-%m-%d')], "prices": [price_val], "open": [price_val], "high": [price_val], "low": [price_val], "close": [price_val]},
                    "weekly": {"dates": [datetime.now().strftime('%Y-%m-%d')], "prices": [price_val], "open": [price_val], "high": [price_val], "low": [price_val], "close": [price_val]}
                }
                b['change'] = b.get('pct_change') or 0.0
                b['change_1m'] = 0.0
                b['change_12m'] = 0.0
                b['change_ytd'] = 0.0
                selected.append(b)

        return selected

    print("Fetching and validating CER bonds...")
    final_cer = validate_and_select_top(bonds_cer, 25)

    print("Fetching and validating USD bonds...")
    final_usd = validate_and_select_top(bonds_usd, 25)

    print("Fetching and validating Pesos bonds...")
    final_pesos = validate_and_select_top(bonds_pesos, 25)

    print("Fetching and validating ONs (corporate bonds) from Rava...")
    valid_ons_hard = []
    valid_ons_cer_dl = []

    for list_on, target_list in [(ons_hard_dollar, valid_ons_hard), (ons_cer_dl, valid_ons_cer_dl)]:
        for b in list_on:
            ticker = b.get('ticker')
            if not ticker:
                continue

            # Filter duration and DTM
            duration = b.get('modified_duration') or b.get('duration')
            dtm = b.get('days_to_finish') or b.get('dtm')

            try:
                if isinstance(duration, str):
                    duration = duration.replace('%', '').strip()
                dur_val = float(duration) if duration is not None else 1.0
            except ValueError:
                dur_val = 1.0

            if dtm is None:
                dtm_val = dur_val * 365.0
            else:
                try:
                    dtm_val = float(dtm)
                except ValueError:
                    dtm_val = dur_val * 365.0

            if dur_val < 0.20 or dtm_val < 45:
                continue

            # Try to fetch history from Rava
            dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker)
            if not dates and ticker.endswith('D'):
                dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker[:-1] + 'O')
            if not dates and ticker.endswith('O'):
                dates, prices, opens, highs, lows = fetch_rava_ohlc_history(ticker[:-1] + 'D')

            if dates and prices:
                # Adjust by residual factor
                factors = pd.Series(
                    [get_bond_residual_factor(ticker, d) for d in dates],
                    index=pd.to_datetime(dates)
                )
                factors = factors.apply(lambda x: x if x > 0.0 else 1.0)

                prices = [p / f for p, f in zip(prices, factors)]
                opens = [o / f for o, f in zip(opens, factors)]
                highs = [h / f for h, f in zip(highs, factors)]
                lows = [l / f for l, f in zip(lows, factors)]

                hist_series = pd.Series(prices, index=pd.to_datetime(dates)).sort_index()
                hist_series = hist_series[~hist_series.index.duplicated(keep='last')]
                vars_dict = calculate_variations(hist_series)

                # Update current price and variations
                b['price'] = prices[-1]
                b['change'] = vars_dict['change']
                b['change_1m'] = vars_dict['change_1m']
                b['change_ytd'] = vars_dict['change_ytd']
                b['change_12m'] = vars_dict['change_12m']

                # Store in historical_bonds for the chart modals
                limit_daily = datetime.now() - timedelta(days=3*365)
                daily_idx = hist_series.index[hist_series.index >= limit_daily]

                df_temp = pd.DataFrame({
                    "price": prices,
                    "open": opens,
                    "high": highs,
                    "low": lows
                }, index=pd.to_datetime(dates)).sort_index()
                df_temp = df_temp[~df_temp.index.duplicated(keep='last')]

                limit_weekly = datetime.now() - timedelta(days=5*365)
                df_weekly = df_temp[df_temp.index >= limit_weekly].resample('W').agg({
                    "price": "last",
                    "open": "first",
                    "high": "max",
                    "low": "min"
                })

                historical_bonds[ticker] = {
                    "daily": {
                        "dates": [d.strftime('%Y-%m-%d') for d in daily_idx],
                        "prices": [round(float(v), 2) for v in df_temp.loc[daily_idx, "price"].values],
                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "open"].values],
                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "high"].values],
                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in df_temp.loc[daily_idx, "low"].values],
                        "close": [round(float(v), 2) for v in df_temp.loc[daily_idx, "price"].values],
                    },
                    "weekly": {
                        "dates": [d.strftime('%Y-%m-%d') for d in df_weekly.index],
                        "prices": [round(float(v), 2) for v in df_weekly["price"].values],
                        "open": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["open"].values],
                        "high": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["high"].values],
                        "low": [round(float(v), 2) if not pd.isna(v) else None for v in df_weekly["low"].values],
                        "close": [round(float(v), 2) for v in df_weekly["price"].values],
                    }
                }
                target_list.append(b)

    return {
        "cer": final_cer,
        "usd": final_usd,
        "pesos": final_pesos,
        "ons_hard": valid_ons_hard,
        "ons_cer_dl": valid_ons_cer_dl,
        "history": historical_bonds
    }

def fetch_single_bond_details(ticker):
    """Scrapes details and 252-day history for a specific bond from bonistas.com."""
    import time
    ticker_to_url_map = {
        "T2X8": "TX28",
    }
    fetch_ticker = ticker_to_url_map.get(ticker, ticker)
    url = f"https://bonistas.com/bono-cotizacion-rendimiento-precio-hoy/{fetch_ticker}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, 'html.parser')
                script = soup.find('script', id='__NEXT_DATA__')
                if script:
                    raw_json = json.loads(script.string)
                    bond_data = raw_json['props']['pageProps']['bondData']
                    bond = bond_data.get('bond') or {}
                    history = bond_data.get('history') or {}

                    # cC is accrued interest (cupón corrido)
                    accrued_interest = 0.0
                    if 'cC' in history and history['cC']:
                        accrued_interest = history['cC'][-1]

                    # Technical value
                    technical_value = bond.get('fair_value') or 0.0
                    if 'fair_value' in history and history['fair_value']:
                        technical_value = history['fair_value'][-1]

                    # Get last price
                    price_val = bond.get('last_price') or 0.0
                    if 'close' in history and history['close']:
                        price_val = history['close'][-1]

                    # Calculate TIR stats for last 365 days
                    dates_history = history.get('fecha') or []
                    tirs_history = history.get('tir') or []
                    recent_tirs = []
                    limit_date = datetime.now() - timedelta(days=365)
                    for d_str, t_val in zip(dates_history, tirs_history):
                        try:
                            d_obj = datetime.strptime(d_str, "%Y-%m-%d")
                            if d_obj >= limit_date and t_val is not None:
                                recent_tirs.append(float(t_val))
                        except Exception:
                            pass

                    if recent_tirs:
                        tir_avg_365 = sum(recent_tirs) / len(recent_tirs)
                        tir_min_365 = min(recent_tirs)
                        tir_max_365 = max(recent_tirs)
                    else:
                        tir_avg_365 = bond.get('tir') or 0.0
                        tir_min_365 = bond.get('tir') or 0.0
                        tir_max_365 = bond.get('tir') or 0.0

                    # Form sensitivity list
                    sensitivity = {
                        "tir_down_3": bond.get("tir_down_3"),
                        "tir_down_2": bond.get("tir_down_2"),
                        "tir_down_1": bond.get("tir_down_1"),
                        "tir_up_1": bond.get("tir_up_1"),
                        "tir_up_2": bond.get("tir_up_2"),
                        "tir_up_3": bond.get("tir_up_3"),
                        "tir_up_5": bond.get("tir_up_5"),
                        "tir_up_10": bond.get("tir_up_10"),
                    }

                    # Clean price
                    clean_prices = []
                    if 'clean_t3' in history and history['clean_t3'] and any(v != 0 for v in history['clean_t3']):
                        clean_prices = history['clean_t3']
                    else:
                        close_prices = history.get('close') or []
                        cc_prices = history.get('cC') or []
                        clean_prices = [max(0.0, c - cc) for c, cc in zip(close_prices, cc_prices)]

                    return ticker, {
                        "ticker": ticker,
                        "name": bond.get("short_description") or bond.get("description", "").split("\n")[0].replace("**", ""),
                        "price": price_val,
                        "tir": bond.get("tir") or 0.0,
                        "fair_value": technical_value,
                        "modified_duration": bond.get("modified_duration") or 0.0,
                        "parity": bond.get("parity") or 0.0,
                        "change": bond.get("day_difference") or 0.0,
                        "open": bond.get("last_open") or 0.0,
                        "min": bond.get("last_min") or 0.0,
                        "max": bond.get("last_max") or 0.0,
                        "close": bond.get("last_close") or 0.0,
                        "start_date": bond.get("start_date") or "",
                        "end_date": bond.get("end_date") or "",
                        "coupon": bond.get("coupon") or 0.0,
                        "tir_avg_365": tir_avg_365,
                        "tir_min_365": tir_min_365,
                        "tir_max_365": tir_max_365,
                        "sensitivity": sensitivity,
                        "history": {
                            "fecha": history.get("fecha") or [],
                            "tir": [float(v) * 100.0 if v is not None else 0.0 for v in (history.get("tir") or [])],
                            "paridad": [float(v) * 100.0 if v is not None else 0.0 for v in (history.get("paridad") or [])],
                            "close": history.get("close") or [],
                            "clean": clean_prices,
                            "cC": history.get("cC") or [],
                            "fair_value": history.get("fair_value") or []
                        }
                    }
            print(f"Warning: Attempt {attempt+1} for {ticker} returned status {r.status_code}")
            time.sleep(1.5 + attempt * 2)
        except Exception as e:
            print(f"Warning: Attempt {attempt+1} for {ticker} failed: {e}")
            time.sleep(1.5 + attempt * 2)

    print(f"Error: Failed to fetch detail for {ticker} after {max_retries} attempts.")
    return ticker, None

def fetch_rava_caucion_history(symbol):
    """Scrapes historical daily closing rates for a Caucion from Rava Bursátil."""
    url = f"https://www.rava.com/perfil/{symbol.replace(' ', '%20')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.rava.com/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        dates = []
        prices = []
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    date_str = tds[0].text.strip()
                    cierre_str = tds[4].text.strip().replace(',', '.')
                    try:
                        dt = datetime.strptime(date_str, '%d/%m/%Y')
                        val = float(cierre_str)
                        dates.append(dt.strftime('%Y-%m-%d'))
                        prices.append(val)
                    except ValueError:
                        pass
            return dates[::-1], prices[::-1]
    except Exception as e:
        print(f"Warning: Failed to fetch Rava history for {symbol}: {e}")
    return [], []

def fetch_rava_ohlc_history(symbol):
    """Scrapes historical daily OHLC rates for a symbol from Rava Bursátil."""
    url = f"https://www.rava.com/perfil/{symbol.replace(' ', '%20')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.rava.com/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        dates, prices, opens, highs, lows = [], [], [], [], []
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    date_str = tds[0].text.strip()
                    open_str = tds[1].text.strip().replace(',', '.')
                    max_str = tds[2].text.strip().replace(',', '.')
                    min_str = tds[3].text.strip().replace(',', '.')
                    cierre_str = tds[4].text.strip().replace(',', '.')
                    try:
                        dt = datetime.strptime(date_str, '%d/%m/%Y')
                        val_c = float(cierre_str)
                        val_o = float(open_str) if open_str else val_c
                        val_h = float(max_str) if max_str else val_c
                        val_l = float(min_str) if min_str else val_c
                        dates.append(dt.strftime('%Y-%m-%d'))
                        prices.append(val_c)
                        opens.append(val_o)
                        highs.append(val_h)
                        lows.append(val_l)
                    except ValueError:
                        pass
            return dates[::-1], prices[::-1], opens[::-1], highs[::-1], lows[::-1]
    except Exception as e:
        print(f"Warning: Failed to fetch Rava OHLC for {symbol}: {e}")
    return [], [], [], [], []

def fetch_cauciones():
    """Fetches latest rates and history for Cauciones 1D, 7D, 30D from Rava."""
    cauciones_res = []
    cauciones_histories = {}
    for sym, ticker, name in [("CAUCION 1D", "CAUCION_1D", "Caución Bursátil a 1 día"),
                              ("CAUCION 7D", "CAUCION_7D", "Caución Bursátil a 7 días"),
                              ("CAUCION 30D", "CAUCION_30D", "Caución Bursátil a 30 días")]:
        dates, prices = fetch_rava_caucion_history(sym)
        if len(dates) > 0:
            last_price = prices[-1]
            prev_price = prices[-2] if len(prices) > 1 else last_price
            change = ((last_price - prev_price) / prev_price) * 100 if prev_price else 0.0

            cauciones_res.append({
                "ticker": ticker,
                "name": name,
                "price": round(last_price, 2),
                "change": round(change, 2)
            })

            cauciones_histories[ticker] = {
                "daily": {
                    "dates": dates,
                    "prices": prices
                },
                "weekly": {
                    "dates": dates,
                    "prices": prices
                }
            }
        else:
            fallbacks = {
                "CAUCION_1D": 20.60,
                "CAUCION_7D": 21.10,
                "CAUCION_30D": 21.00
            }
            cauciones_res.append({
                "ticker": ticker,
                "name": name,
                "price": fallbacks[ticker],
                "change": 0.0
            })
            cauciones_histories[ticker] = {
                "daily": {"dates": [], "prices": []},
                "weekly": {"dates": [], "prices": []}
            }
    return cauciones_res, cauciones_histories

def fetch_lecaps_bonistas():
    """Fetches top 3 active LECAPs by volume from Bonistas.com."""
    url = "https://bonistas.com/bonos-cer-hoy"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if script:
                raw_json = json.loads(script.string)
                bond_list = raw_json['props']['pageProps']['bondData']

                lecaps = []
                for b in bond_list:
                    fam = b.get('bond_family', '') or ''
                    ticker = b.get('ticker', '') or ''
                    if fam == 'LETRAS-FIJO':
                        # Filter duration and DTM
                        duration = b.get('modified_duration') or b.get('duration')
                        dtm = b.get('days_to_finish') or b.get('dtm')

                        try:
                            dur_val = float(duration) if duration is not None else 1.0
                        except ValueError:
                            dur_val = 1.0

                        if dtm is None:
                            dtm_val = dur_val * 365.0
                        else:
                            try:
                                dtm_val = float(dtm)
                            except ValueError:
                                dtm_val = dur_val * 365.0

                        if dur_val < 0.20 or dtm_val < 45:
                            continue

                        tir = (b.get('tir') or 0.0) * 100
                        vol = b.get('volume') or 0.0
                        desc = b.get('short_description', '')
                        lecaps.append({
                            "ticker": f"LECAP_{ticker}",
                            "name": desc or f"LECAP {ticker}",
                            "price": round(tir, 2),
                            "change": 0.0,
                            "volume": vol
                        })
                # Sort by volume and pick top 3
                lecaps_sorted = sorted(lecaps, key=lambda x: x['volume'], reverse=True)
                return lecaps_sorted[:3]
    except Exception as e:
        print(f"Warning: Failed to fetch LECAPs from Bonistas: {e}")

    return [
        {"ticker": "LECAP_S30S6", "name": "Bono Tasa Fija ARS - vto. 09/2026", "price": 24.51, "change": 0.0},
        {"ticker": "LECAP_S30N6", "name": "Bono Tasa Fija ARS - vto. 11/2026", "price": 22.88, "change": 0.0},
        {"ticker": "LECAP_S18D6", "name": "Bono Tasa Fija ARS - vto. 12/2026", "price": 21.40, "change": 0.0}
    ]

def get_argentina_settlement_date(from_date):
    """Calculates next business day for Argentina, skipping weekends and fixed holidays."""
    holidays = {
        '2026-03-23', '2026-03-24', '2026-04-02', '2026-04-03',
        '2026-05-01', '2026-05-25', '2026-06-15', '2026-06-20',
        '2026-07-09', '2026-08-17', '2026-10-12', '2026-11-23',
        '2026-12-07', '2026-12-08', '2026-12-25', '2027-01-01',
    }
    d = from_date
    steps = 0
    while steps < 1:
        d += timedelta(days=1)
        if d.weekday() >= 5: # Saturday or Sunday
            continue
        iso = d.strftime('%Y-%m-%d')
        if iso in holidays:
            continue
        steps += 1
    return d

def fetch_lecaps_rendimientos_co():
    """Fetches active LECAPs/BONCAPs from rendimientos.co API and calculates metrics."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r_config = requests.get("https://rendimientos.co/api/config", headers=headers, timeout=15)
        r_live = requests.get("https://rendimientos.co/api/lecaps", headers=headers, timeout=15)

        if r_config.status_code == 200 and r_live.status_code == 200:
            config_data = r_config.json()
            live_data = r_live.json()

            live_prices = {}
            for item in live_data.get("data", []):
                sym = item.get("symbol")
                if sym:
                    live_prices[sym] = {
                        "price": item.get("price"),
                        "bid": item.get("bid"),
                        "ask": item.get("ask"),
                        "type": item.get("type")
                    }

            letras_config = config_data.get("lecaps", {}).get("letras", [])
            processed_lecaps = []

            today = date.today()
            settlement = get_argentina_settlement_date(today)

            for letra in letras_config:
                if not letra.get("activo"):
                    continue
                ticker = letra.get("ticker")
                live = live_prices.get(ticker, {})

                # Fallback matching tty.js: ask > 0 else (price > 0 else config price)
                price = live.get("ask") or live.get("price") or letra.get("precio")
                if not price or price <= 0:
                    continue

                pago_final = letra.get("pago_final")
                vto_str = letra.get("fecha_vencimiento")
                vto = datetime.strptime(vto_str, "%Y-%m-%d").date()

                dtm = max(1, (vto - settlement).days)
                duration = dtm / 365.0
                if duration < 0.20 or dtm < 45:
                    continue

                ganancia = pago_final / price

                tem = (pow(ganancia, 30.0 / dtm) - 1.0) * 100.0
                tna = (ganancia - 1.0) * (365.0 / dtm) * 100.0
                tea = (pow(ganancia, 365.0 / dtm) - 1.0) * 100.0

                processed_lecaps.append({
                    "ticker": ticker,
                    "name": letra.get("nombre") or f"LECAP {ticker}",
                    "pago_final": pago_final,
                    "fecha_vencimiento": vto_str,
                    "price": price,
                    "type": live.get("type") or (letra.get("nombre", "").split()[0] if letra.get("nombre") else "LECAP"),
                    "dtm": dtm,
                    "tem": round(tem, 2),
                    "tna": round(tna, 2),
                    "tea": round(tea, 2)
                })

            processed_lecaps.sort(key=lambda x: x["dtm"])
            return processed_lecaps
    except Exception as e:
        print(f"Error fetching/processing lecaps from rendimientos.co: {e}")
    return []


