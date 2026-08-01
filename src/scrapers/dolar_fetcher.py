import requests
import json
import time
import math
import os
from datetime import datetime, timedelta, date
import calendar
from src.utils.formatters import *
from src.utils.math_utils import *
from src.utils.dates import *
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import unicodedata
import re


def calculate_exchange_rate_band_series(start_date, end_date, inflation_data):
    """
    Generates a daily series of Piso and Techo values for the BCRA exchange rate band.
    - Base on 11-Apr-2025: Piso=$1000, Techo=$1400
    - Up to 31-Dec-2025: Piso decreases 1% monthly, Techo increases 1% monthly
    - From 01-Jan-2026: Limits adjust monthly by the IPC of T-2.
    """
    base_date = date(2025, 4, 11)
    piso = 1000.0
    techo = 1400.0

    # 2025 compound daily adjustment
    factor_piso_2025_daily = 0.99 ** (1/30)
    factor_techo_2025_daily = 1.01 ** (1/30)

    fallbacks = {
        (2025, 11): 0.025,
        (2025, 12): 0.028,
        (2026, 1): 0.029,
        (2026, 2): 0.029,
        (2026, 3): 0.034,
        (2026, 4): 0.026,
        (2026, 5): 0.021,
    }


    series = {}
    current = base_date

    # Run the simulation day by day from base_date to end_date
    while current <= end_date:
        if current.year == 2025:
            piso *= factor_piso_2025_daily
            techo *= factor_techo_2025_daily
        else: # 2026
            inf_rate = get_t2_inflation(current.year, current.month, inflation_data)
            days_in_month = calendar.monthrange(current.year, current.month)[1]
            factor_daily = (1.0 + inf_rate) ** (1 / days_in_month)
            piso *= factor_daily
            techo *= factor_daily

        if current >= start_date:
            series[current.strftime('%Y-%m-%d')] = {
                "piso": round(piso, 2),
                "techo": round(techo, 2)
            }
        current += timedelta(days=1)

    return series

def fetch_dolar_api():
    """Fetches current exchange rates in Argentina from Dolar API."""
    data = {}
    try:
        r = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                casa = item['casa'].lower()
                data[casa] = {
                    "compra": item.get('compra', 0.0),
                    "venta": item.get('venta', 0.0),
                    "nombre": item.get('nombre', '')
                }

        # Euro & Real
        r_cot = requests.get("https://dolarapi.com/v1/cotizaciones", timeout=10)
        if r_cot.status_code == 200:
            for item in r_cot.json():
                moneda = item['moneda'].lower()
                data[moneda] = {
                    "compra": item.get('compra', 0.0),
                    "venta": item.get('venta', 0.0),
                    "nombre": item.get('nombre', '')
                }

        # Map mep and ccl keys for the HTML template
        if 'bolsa' in data:
            data['mep'] = data['bolsa']
        if 'contadoconliqui' in data:
            data['ccl'] = data['contadoconliqui']
        if 'eur' in data:
            data['euro'] = data['eur']
        if 'brl' in data:
            data['real'] = data['brl']
    except Exception as e:
        print(f"Error fetching Dolar API: {e}")
    return data

def fetch_dolar_history_and_bands(inflation_data):
    """
    Fetches historical exchange rates from ArgentinaDatos and computes exchange bands history.
    """
    history_db = {}
    df_oficial = None
    try:
        url = "https://api.argentinadatos.com/v1/cotizaciones/dolares"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            df_raw = pd.DataFrame(r.json())
            df_raw['fecha'] = pd.to_datetime(df_raw['fecha'])
            df_raw.set_index('fecha', inplace=True)

            # Map the houses
            casa_mapping = {
                "oficial": "Oficial Billete",
                "mayorista": "Oficial Divisa",
                "blue": "Blue",
                "bolsa": "MEP",
                "contadoconliqui": "CCL"
            }

            # Keep df_oficial for foreign currencies multiplication in ARS
            df_oficial = df_raw[df_raw['casa'] == 'oficial']['venta'].dropna().sort_index()

            start_date_5y = datetime.now() - timedelta(days=5*365)

            # For each target house, build daily and weekly series
            for api_casa, label in casa_mapping.items():
                df_house = df_raw[df_raw['casa'] == api_casa]['venta'].dropna().sort_index()

                # Daily (full history to support historical charts)
                daily = df_house
                # Weekly (full history)
                weekly = df_house.resample('W').last()

                history_db[label] = {
                    "daily": {
                        "dates": [d.strftime('%Y-%m-%d') for d in daily.index],
                        "prices": [round(float(v), 2) for v in daily.values]
                    },
                    "weekly": {
                        "dates": [d.strftime('%Y-%m-%d') for d in weekly.index],
                        "prices": [round(float(v), 2) for v in weekly.values]
                    }
                }

            # Now compute bands history
            print("Calculating exchange rate bands historical series...")
            start_simulate = date(2025, 4, 11)
            end_simulate = datetime.now().date()
            bands_series = calculate_exchange_rate_band_series(start_simulate, end_simulate, inflation_data)

            # Convert bands_series to daily and weekly formats
            band_dates = sorted(bands_series.keys())
            band_piso_vals = [bands_series[d]['piso'] for d in band_dates]
            band_techo_vals = [bands_series[d]['techo'] for d in band_dates]

            df_bands = pd.DataFrame({
                "piso": band_piso_vals,
                "techo": band_techo_vals
            }, index=pd.to_datetime(band_dates))

            # Daily last 3 years to support 2A period view
            daily_bands = df_bands[df_bands.index >= (datetime.now() - timedelta(days=3*365))]
            # Weekly
            weekly_bands = df_bands.resample('W').last()

            history_db["PISO_BANDA"] = {
                "daily": {
                    "dates": [d.strftime('%Y-%m-%d') for d in daily_bands.index],
                    "prices": [round(float(v), 2) for v in daily_bands['piso'].values]
                },
                "weekly": {
                    "dates": [d.strftime('%Y-%m-%d') for d in weekly_bands.index],
                    "prices": [round(float(v), 2) for v in weekly_bands['piso'].values]
                }
            }
            history_db["TECHO_BANDA"] = {
                "daily": {
                    "dates": [d.strftime('%Y-%m-%d') for d in daily_bands.index],
                    "prices": [round(float(v), 2) for v in daily_bands['techo'].values]
                },
                "weekly": {
                    "dates": [d.strftime('%Y-%m-%d') for d in weekly_bands.index],
                    "prices": [round(float(v), 2) for v in weekly_bands['techo'].values]
                }
            }
    except Exception as e:
        print(f"Error fetching historical dollar data: {e}")
    return history_db, df_oficial

