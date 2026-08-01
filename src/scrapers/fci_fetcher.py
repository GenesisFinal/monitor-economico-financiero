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
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import unicodedata
import re


def fetch_plazo_fijo():
    """Fetches and maps all plazo fijo rates from ArgentinaDatos with short names sorted by TNA descending."""
    url = "https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo"
    name_map = {
        "BANCO DE LA NACION ARGENTINA": "Nación",
        "BANCO DE GALICIA Y BUENOS AIRES S.A.": "Galicia",
        "BANCO BBVA ARGENTINA S.A.": "BBVA",
        "BANCO SANTANDER ARGENTINA S.A.": "Banco Santander",
        "BANCO DE LA PROVINCIA DE BUENOS AIRES": "Provincia BA",
        "BANCO MACRO S.A.": "Macro",
        "INDUSTRIAL AND COMMERCIAL BANK OF CHINA (ARGENTINA) S.A.U.": "ICBC",
        "BANCO DE LA CIUDAD DE BUENOS AIRES": "Ciudad",
        "BANCO PATAGONIA S.A.": "Banco Patagonia",
        "BANCO CREDICOOP COOPERATIVO LIMITADO": "Credicoop",
        "BANCO BICA S.A.": "Bica",
        "BANCO CMF S.A.": "CMF",
        "BANCO COMAFI SOCIEDAD ANONIMA": "Comafi",
        "BANCO DE COMERCIO S.A.": "Banco de Comercio",
        "BANCO DE FORMOSA S.A.": "Banco de Formosa",
        "BANCO DE LA PROVINCIA DE CORDOBA S.A.": "Provincia de Córdoba",
        "BANCO DEL CHUBUT S.A.": "Banco del Chubut",
        "BANCO DEL SOL S.A.": "Del Sol",
        "BANCO DINO S.A.": "Dino",
        "BANCO HIPOTECARIO S.A.": "Banco Hipotecario",
        "BANCO JULIO SOCIEDAD ANONIMA": "Julio",
        "BANCO MARIVA S.A.": "Mariva",
        "BANCO MASVENTAS S.A.": "Banco Masventas",
        "BANCO MERIDIAN S.A.": "Banco Meridian S.a.",
        "BANCO PROVINCIA DE TIERRA DEL FUEGO": "Provincia de TDF",
        "BANCO VOII S.A.": "Voii",
        "BIBANK S.A.": "Bibank",
        "CRÉDITO REGIONAL COMPAÑIA FINANCIERA S.A.U.": "Crédito Regional",
        "CRÉDITO REGIONAL COMPAÑÍA FINANCIERA S.A.U.": "Crédito Regional",
        "REBA COMPAÑIA FINANCIERA S.A.": "Reba",
        "Banco Piano": "Piano",
        "Piano": "Piano",
        "Brubank": "Brubank",
        "UALA": "Ualá",
        "Ualá": "Ualá"
    }

    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            res = []
            max_tna = 0.0

            # First pass to find max TNA
            for item in data:
                rate = float(item.get('tnaClientes', 0.0)) * 100
                if rate > max_tna:
                    max_tna = rate

            for item in data:
                ent_raw = item.get('entidad', '')
                ent_upper = ent_raw.upper().strip()
                rate = round(float(item.get('tnaClientes', 0.0)) * 100, 2)

                # Check mapping
                mapped_name = ent_raw
                for k, v in name_map.items():
                    if k.upper() in ent_upper or ent_upper in k.upper():
                        mapped_name = v
                        break

                res.append({
                    "ticker": f"PF_{mapped_name.upper().replace(' ', '_')}",
                    "name": mapped_name,
                    "price": rate,
                    "change": 0.0,
                    "destacado": (rate >= 22.0)
                })

            # Sort by rate descending, then by name
            res_sorted = sorted(res, key=lambda x: (-x['price'], x['name']))
            return res_sorted

    except Exception as e:
        print(f"Warning: Failed to fetch Plazo Fijo: {e}")

    # Return offline fallbacks if API fails
    return [
        {"ticker": "PF_MERIDIAN", "name": "Banco Meridian S.a.", "price": 22.25, "change": 0.0, "destacado": True},
        {"ticker": "PF_REBA", "name": "Reba", "price": 23.0, "change": 0.0, "destacado": True},
        {"ticker": "PF_NACION", "name": "Nación", "price": 19.0, "change": 0.0, "destacado": False},
        {"ticker": "PF_GALICIA", "name": "Galicia", "price": 17.5, "change": 0.0, "destacado": False}
    ]

def fetch_money_market_rates():
    """Fetches latest and penultimo VCP for 4 money market funds, annualizing the daily return."""
    url_u = "https://api.argentinadatos.com/v1/finanzas/fci/mercadoDinero/ultimo"
    url_p = "https://api.argentinadatos.com/v1/finanzas/fci/mercadoDinero/penultimo"
    try:
        r_u = requests.get(url_u, timeout=10)
        r_p = requests.get(url_p, timeout=10)
        if r_u.status_code == 200 and r_p.status_code == 200:
            dict_u = {x['fondo']: x for x in r_u.json()}
            dict_p = {x['fondo']: x for x in r_p.json()}

            target_funds = [
                {"ticker": "FCI_MERCADOFONDO", "names": ["Mercado Fondo - Clase A", "Mercado Fondo - Clase C"], "display": "Mercado Fondo (Mercado Pago)"},
                {"ticker": "FCI_UALA", "names": ["Ualintec Ahorro Pesos - Clase A", "Ualintec Ahorro Pesos - Clase B"], "display": "Ualintec Ahorro Pesos (Ualá)"},
                {"ticker": "FCI_FIMA", "names": ["Fima Premium - Clase A", "Fima Premium - Clase B", "Fima Premium - Clase C"], "display": "Fima Premium (Banco Galicia)"},
                {"ticker": "FCI_PELLEGRINI", "names": ["Pellegrini Liquidez Pesos Clase A", "Pellegrini Liquidez Pesos Clase C"], "display": "Pellegrini Liquidez (Banco Nación)"}
            ]

            res = []
            for target in target_funds:
                matched = False
                for fname in target["names"]:
                    u_item = dict_u.get(fname)
                    p_item = dict_p.get(fname)
                    if u_item and p_item:
                        dt_u = datetime.strptime(u_item['fecha'], '%Y-%m-%d')
                        dt_p = datetime.strptime(p_item['fecha'], '%Y-%m-%d')
                        delta = (dt_u - dt_p).days
                        if delta > 0:
                            vcp_u = u_item['vcp']
                            vcp_p = p_item['vcp']
                            daily_ret = (vcp_u - vcp_p) / vcp_p
                            tna = (daily_ret / delta) * 365 * 100
                            res.append({"ticker": target["ticker"], "name": target["display"], "price": round(tna, 2), "change": 0.0})
                            matched = True
                            break
                if not matched:
                    fallbacks = {
                        "FCI_MERCADOFONDO": 17.24,
                        "FCI_UALA": 17.94,
                        "FCI_FIMA": 15.70,
                        "FCI_PELLEGRINI": 19.83
                    }
                    res.append({"ticker": target["ticker"], "name": target["display"], "price": fallbacks[target["ticker"]], "change": 0.0})
            return res
    except Exception as e:
        print(f"Warning: Failed to fetch MM rates: {e}")
    return [
        {"ticker": "FCI_MERCADOFONDO", "name": "Mercado Fondo (Mercado Pago)", "price": 17.24, "change": 0.0},
        {"ticker": "FCI_UALA", "name": "Ualintec Ahorro Pesos (Ualá)", "price": 17.94, "change": 0.0},
        {"ticker": "FCI_FIMA", "name": "Fima Premium (Banco Galicia)", "price": 15.70, "change": 0.0},
        {"ticker": "FCI_PELLEGRINI", "name": "Pellegrini Liquidez (Banco Nación)", "price": 19.83, "change": 0.0}
    ]

def get_fallback_fci_data():
    """Returns static, realistic top 3 funds of each category and currency as fallback."""
    raw = {
        "Mercado de Dinero": {
            "Pesos": [
                {"name": "Mercado Fondo - Clase A", "manager": "Mercado Pago Asset Management S.A.", "patrimonio": 6826533983922.24, "vcp": 24263.828, "daily": 0.3779, "monthly": 18.15, "ytd": 23.37, "m12": 30.14},
                {"name": "Pellegrini Liquidez - Clase A", "manager": "Pellegrini Sociedad Gerente S.A.", "patrimonio": 4533548070991.28, "vcp": 96946.982, "daily": 0.0941, "monthly": 17.98, "ytd": 23.33, "m12": 30.74},
                {"name": "Fima Premium - Clase A", "manager": "Galicia Asset Management S.A.U.", "patrimonio": 3384719950543.64, "vcp": 80651.265, "daily": 0.086, "monthly": 16.49, "ytd": 21.73, "m12": 28.83}
            ],
            "Dólares": [
                {"name": "Fima Premium Dólares - Clase A", "manager": "Galicia Asset Management S.A.U.", "patrimonio": 1819866327.0, "vcp": 1013.743, "daily": 0.012, "monthly": 0.12, "ytd": 1.05, "m12": 2.50},
                {"name": "Superfondo Ahorro en Dólares - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 1100117563.0, "vcp": 1016.121, "daily": 0.011, "monthly": 0.15, "ytd": 1.10, "m12": 2.70},
                {"name": "IAM Retorno Dólares - Clase A", "manager": "Supervielle Asset Management S.A.", "patrimonio": 869988170.0, "vcp": 1032.735, "daily": 0.018, "monthly": 0.18, "ytd": 1.25, "m12": 3.00}
            ]
        },
        "Renta Fija": {
            "Pesos": [
                {"name": "Supergestion Mix VI - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 856570049583.0, "vcp": 157204.35, "daily": 0.221, "monthly": 3.40, "ytd": 22.30, "m12": 48.50},
                {"name": "Superfondo Renta Fija - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 446858915663.0, "vcp": 168012.505, "daily": 0.182, "monthly": 3.10, "ytd": 21.10, "m12": 45.30},
                {"name": "Balanz Capital Ahorro - Clase A", "manager": "Balanz Sociedad Gerente de FCI S.A.", "patrimonio": 438933858745.0, "vcp": 235195.122, "daily": 0.245, "monthly": 3.80, "ytd": 23.50, "m12": 51.20}
            ],
            "Dólares": [
                {"name": "Schroder Renta Global Cinco - Clase A", "manager": "Schroder Investment Management S.A.", "patrimonio": 74247378865.0, "vcp": 15911.862, "daily": 0.031, "monthly": 0.25, "ytd": 2.30, "m12": 6.50},
                {"name": "Consultatio Renta Dolares - Clase A", "manager": "Consultatio Asset Management S.A.", "patrimonio": 73682481904.0, "vcp": 162168.013, "daily": 0.042, "monthly": 0.28, "ytd": 2.50, "m12": 7.10},
                {"name": "Schroder Renta Global Cuatro - Clase A", "manager": "Schroder Investment Management S.A.", "patrimonio": 29477218514.0, "vcp": 13687.543, "daily": 0.022, "monthly": 0.21, "ytd": 1.95, "m12": 5.80}
            ]
        },
        "Renta Variable": {
            "Pesos": [
                {"name": "Superfondo Acciones - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 189113750966.4, "vcp": 515548.383, "daily": 0.3263, "monthly": 7.03, "ytd": 6.79, "m12": 31.10},
                {"name": "Superfondo Renta Variable - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 127999123814.18, "vcp": 5243538.988, "daily": 0.1811, "monthly": 7.53, "ytd": 0.91, "m12": 27.58},
                {"name": "Galileo Acciones - Clase A", "manager": "Galileo Argentina S.G.F.C.I. S.A.", "patrimonio": 87376326573.7, "vcp": 421173.687, "daily": -0.2947, "monthly": 6.36, "ytd": 11.28, "m12": 41.36}
            ],
            "Dólares": [
                {"name": "Superfondo Latinoamerica - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 2038579869.31, "vcp": 8288755.253, "daily": 1.0518, "monthly": -5.31, "ytd": 14.70, "m12": 73.12},
                {"name": "Superfondo Acciones Brasil - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 423180237.57, "vcp": 2369247.286, "daily": 0.9323, "monthly": -10.24, "ytd": 6.86, "m12": 59.39},
                {"name": "Galileo Acciones Clase A - Dolares", "manager": "Galileo Argentina S.G.F.C.I. S.A.", "patrimonio": 238699336.37, "vcp": 12482765.101, "daily": 1.0567, "monthly": -5.18, "ytd": 15.52, "m12": 76.19}
            ]
        },
        "Renta Mixta": {
            "Pesos": [
                {"name": "Cocos Rendimiento - Clase A", "manager": "Cocos Asset Management S.A.", "patrimonio": 259720758806.31, "vcp": 11074.479, "daily": 0.0565, "monthly": 1.61, "ytd": 10.44, "m12": 35.07},
                {"name": "Consultatio Renta Mixta - Clase A", "manager": "Consultatio Asset Management S.A.", "patrimonio": 208178833543.97, "vcp": 304365.288, "daily": 0.0686, "monthly": 3.00, "ytd": 16.05, "m12": 48.33},
                {"name": "Superfondo Renta Mixta - Clase A", "manager": "Santander Asset Management S.A.", "patrimonio": 155043502571.06, "vcp": 4878.008, "daily": 0.213, "monthly": 1.74, "ytd": 5.92, "m12": 38.90}
            ],
            "Dólares": [
                {"name": "Allaria Dólar Ahorro Plus - Clase A", "manager": "Allaria Ledesma Fondos Administrados S.A.", "patrimonio": 121861685.65, "vcp": 1083.549, "daily": 0.0336, "monthly": 0.22, "ytd": 2.03, "m12": 6.08},
                {"name": "Delta Renta Dolar - Clase A", "manager": "Delta Asset Management S.A.", "patrimonio": 111124540.45, "vcp": 1086.34, "daily": 0.0344, "monthly": 0.24, "ytd": 2.14, "m12": 6.30},
                {"name": "Fima Mix Dólares - Clase A", "manager": "Galicia Asset Management S.A.U.", "patrimonio": 95639762.96, "vcp": 1469.624, "daily": 3.2421, "monthly": 2.43, "ytd": 4.42, "m12": 12.08}
            ]
        },
        "Retorno Total": {
            "Pesos": [
                {"name": "Cocos Pesos Plus - Clase A", "manager": "Cocos Asset Management S.A.", "patrimonio": 441990558028.6, "vcp": 1370.132, "daily": 0.2972, "monthly": 2.06, "ytd": 12.43, "m12": 37.01},
                {"name": "Consultatio Balance Fund - Clase A", "manager": "Consultatio Asset Management S.A.", "patrimonio": 174904621414.6, "vcp": 4216174.123, "daily": 0.4207, "monthly": 3.04, "ytd": 15.51, "m12": 45.93},
                {"name": "Schroder Patrimonio Dos - Clase A", "manager": "Schroder Investment Management S.A.", "patrimonio": 111735042547.93, "vcp": 995.597, "daily": -0.258, "monthly": 1.02, "ytd": 4.61, "m12": 37.37}
            ],
            "Dólares": [
                {"name": "Galileo Event Driven - Clase A", "manager": "Galileo Argentina S.G.F.C.I. S.A.", "patrimonio": 133423915.91, "vcp": 3924.366, "daily": 0.4565, "monthly": 0.39, "ytd": 1.60, "m12": 7.07},
                {"name": "Compass Renta Fija Dolar - Clase A", "manager": "Compass Group S.A. S.G.F.C.I.", "patrimonio": 128806456.72, "vcp": 1895553.132, "daily": 2.4027, "monthly": 2.39, "ytd": 2.51, "m12": 50.02},
                {"name": "IAM Renta Dolar - Clase A", "manager": "Supervielle Asset Management S.A.", "patrimonio": 119622933.28, "vcp": 3272.478, "daily": 0.454, "monthly": 0.34, "ytd": 1.32, "m12": 6.35}
            ]
        }
    }
    for tr, curr_dict in raw.items():
        for curr, f_list in curr_dict.items():
            for idx, fund in enumerate(f_list):
                fund["selection_type"] = "AUM" if idx < 2 else "Performance 12M"
                fund["category_spanish"] = f"Fondos de {tr}" if tr != "Mercado de Dinero" else "Fondos de Money Market"
    return raw

def fetch_all_fci_details(mep_rate=1200.0, prev_histories=None):
    """
    if prev_histories is None: prev_histories = {}Fetches all mutual funds, separates them by category and currency, sorts by AUM (patrimonio) desc, and retrieves top 3 (2 AUM + 1 Perf). Also downloads histories."""
    import re
    import unicodedata
    import time

    def slugify(value):
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf-8')
        value = value.lower()
        value = re.sub(r'[^a-z0-9]+', '-', value)
        value = re.sub(r'-+', '-', value).strip('-')
        return value

    print("Fetching full FCI database from ArgentinaDatos...")
    url_fondos = "https://api.argentinadatos.com/v1/finanzas/fci/fondos"

    categories_map = {
        "Mercado de Dinero": "mercadoDinero",
        "Renta Fija": "rentaFija",
        "Renta Variable": "rentaVariable",
        "Renta Mixta": "rentaMixta",
        "Retorno Total": "retornoTotal"
    }

    # Initialize result structure
    results = {}
    for cat_name in categories_map.keys():
        results[cat_name] = {"Pesos": [], "Dólares": []}

    try:
        r_f = requests.get(url_fondos, timeout=25)
        if r_f.status_code != 200:
            print("Warning: Failed to fetch fondos list. Using fallback.")
            return get_fallback_fci_data(), {}

        fondos_list = r_f.json().get("fondos", [])

        # Fetch ultimo and penultimo for daily change calculations
        ultimo_dict = {}
        penultimo_dict = {}
        for cat_name, cat_slug in categories_map.items():
            try:
                r_u = requests.get(f"https://api.argentinadatos.com/v1/finanzas/fci/{cat_slug}/ultimo", timeout=12)
                r_p = requests.get(f"https://api.argentinadatos.com/v1/finanzas/fci/{cat_slug}/penultimo", timeout=12)
                if r_u.status_code == 200:
                    for x in r_u.json():
                        ultimo_dict[x['fondo']] = x
                if r_p.status_code == 200:
                    for x in r_p.json():
                        penultimo_dict[x['fondo']] = x
            except Exception as e:
                print(f"Warning: Failed to fetch {cat_slug} details: {e}")

        # Group and process
        for f in fondos_list:
            tr = f.get("tipoRenta")
            if tr not in categories_map:
                continue

            moneda = f.get("moneda")
            if not moneda:
                continue

            currency_key = None
            if "peso" in moneda.lower():
                currency_key = "Pesos"
            elif "dolar" in moneda.lower() or "dólar" in moneda.lower():
                currency_key = "Dólares"

            if not currency_key:
                continue

            name = f.get("nombre")
            if not name or ("clase a" not in name.lower() and "class a" not in name.lower()):
                continue

            # Skip funds with known broken history endpoints
            blacklist = [
                "axis s&c renta fija dólar low volatility - clase a",
                "axis s&c renta fija dlar low volatility - clase a",
                "axis s&c renta fija dolar low volatility - clase a",
                "cocos renta dólar - clase a - ley nº 27.743",
                "cocos renta dolar - clase a - ley n 27.743",
                "quiron latam en u$s - clase a"
            ]
            if name.lower() in blacklist:
                continue

            manager = f.get("administradora") or "N/A"
            patrimonio = f.get("patrimonio") or 0.0
            rendimientos = f.get("rendimientos") or {}
            vcp = rendimientos.get("valorCuotaparte")

            # Calculate daily return from ultimo/penultimo
            daily_change = None
            if name in ultimo_dict and name in penultimo_dict:
                u_vcp = ultimo_dict[name].get("vcp")
                p_vcp = penultimo_dict[name].get("vcp")
                if u_vcp and p_vcp and p_vcp > 0:
                    daily_change = round(((u_vcp - p_vcp) / p_vcp) * 100, 4)

            # Other variations (monthly, YTD, 12M)
            monthly_change = rendimientos.get("unMes")
            if monthly_change is not None:
                monthly_change = round(monthly_change, 2)
            ytd_change = rendimientos.get("enElAnio")
            if ytd_change is not None:
                ytd_change = round(ytd_change, 2)
            m12_change = rendimientos.get("doceMeses")
            if m12_change is not None:
                m12_change = round(m12_change, 2)

            results[tr][currency_key].append({
                "name": name,
                "manager": manager,
                "patrimonio": patrimonio,
                "vcp": vcp,
                "daily": daily_change,
                "monthly": monthly_change,
                "ytd": ytd_change,
                "m12": m12_change
            })

        # ── Fixed management houses we always include ─────────────────────────
        # Matched against 'manager' (administradora field) and 'name' (nombre field), lowercased.
        # Each entry: (keyword, search_in) where search_in is 'manager', 'name', or 'both'
        FIXED_HOUSES = [
            ("cocos",       "both"),    # Cocos Asset Management / Cocos Pesos Plus / etc.
            ("allaria",     "manager"), # Allaria Fondos Administrados S.G.F.C.I.S.A.
            ("one618",      "manager"), # One618 Asset Management S.G.F.C.I.S.A.
            ("toronto",     "name"),    # Toronto Trust - Clase A (admin is unrelated)
            ("schroder",    "manager"), # Schroder S.A.S.G.F.C.I.
            ("compass",     "name"),    # Compass Ahorro / Compass Renta (admin is unrelated)
            ("pellegrini",  "both"),    # Pellegrini S.A.S.G.F.C.I.
            ("galicia",     "manager"), # Galicia Asset Management S.A.U. -> Fima funds
            ("fima",        "name"),    # Fima Premium, Fima Renta Fija, etc.
            ("patagonia",   "manager"), # Patagonia Inversora S.A.S.G.F.C.I
            ("industrial",  "manager"), # Industrial Asset Management S.G.F.C.I.S.A.
        ]
        MIN_PATRIMONIO_USD = 20_000_000  # 20 million USD


        cat_labels = {
            "Mercado de Dinero": "Money Market",
            "Renta Fija": "Renta Fija",
            "Renta Variable": "Renta Variable",
            "Renta Mixta": "Renta Mixta",
            "Retorno Total": "Retorno Total"
        }

        final_results = {}
        selected_funds_to_fetch = []

        for tr_name in categories_map.keys():
            final_results[tr_name] = {}
            for curr in ["Pesos", "Dólares"]:
                group = results[tr_name][curr]

                # Ensure patrimonio is float
                for x in group:
                    try:
                        x["patrimonio"] = float(x.get("patrimonio") or 0.0)
                    except (TypeError, ValueError):
                        x["patrimonio"] = 0.0

                # ── Apply minimum patrimony filter ──────────────────────────
                if curr == "Pesos":
                    group = [x for x in group if x["patrimonio"] / max(mep_rate, 1) >= MIN_PATRIMONIO_USD]
                else:
                    group = [x for x in group if x["patrimonio"] >= MIN_PATRIMONIO_USD]

                selected_names = set()
                selected_group = []

                def _add(f, stype, _snames=selected_names, _sg=selected_group, _tr=tr_name, _lbl=cat_labels):
                    if f["name"] not in _snames:
                        fc = dict(f)
                        fc["selection_type"] = stype
                        fc["category_spanish"] = _lbl.get(_tr, _tr)
                        _snames.add(fc["name"])
                        _sg.append(fc)

                # Priority 1: fixed management houses
                for fund in group:
                    mgr = fund.get("manager", "").lower()
                    fname = fund.get("name", "").lower()
                    for house, search_in in FIXED_HOUSES:
                        if search_in == "manager" and house in mgr:
                            _add(fund, "Casa")
                            break
                        elif search_in == "name" and house in fname:
                            _add(fund, "Casa")
                            break
                        elif search_in == "both" and (house in mgr or house in fname):
                            _add(fund, "Casa")
                            break

                # Priority 2: top 5 by 12M return (not already selected)
                rem = [f for f in group if f["name"] not in selected_names]
                rem_12m = sorted(
                    [f for f in rem if f.get("m12") is not None],
                    key=lambda f: float(f["m12"]), reverse=True
                )
                for f in rem_12m[:5]:
                    _add(f, "Rendimiento 12M")

                # Priority 3: top 5 by AUM (not already selected)
                rem2 = sorted(
                    [f for f in group if f["name"] not in selected_names],
                    key=lambda f: f["patrimonio"], reverse=True
                )
                for f in rem2[:5]:
                    _add(f, "Patrimonio AUM")

                # Sort final group by 12M return desc (None values go to bottom)
                selected_group.sort(
                    key=lambda f: float(f["m12"]) if f.get("m12") is not None else -999999,
                    reverse=True
                )

                final_results[tr_name][curr] = selected_group
                selected_funds_to_fetch.extend(selected_group)




        # Fetch histories sequentially for all selected funds
        histories = {}
        if prev_histories is None: prev_histories = {}
        print(f"Starting optimized incremental history fetch for {len(selected_funds_to_fetch)} selected FCI funds...")
        for idx, f in enumerate(selected_funds_to_fetch):
            name = f["name"]
            slug = slugify(name)
            url_hist = f"https://api.argentinadatos.com/v1/finanzas/fci/fondos/{slug}/historico"

            # Incremental logic check
            cached_history = prev_histories.get(name)
            needs_full_fetch = True

            if cached_history and "daily" in cached_history and "dates" in cached_history["daily"] and len(cached_history["daily"]["dates"]) > 0:
                last_cached_date = cached_history["daily"]["dates"][-1]
                u_dt = ultimo_dict.get(name, {}).get("fecha")
                p_dt = penultimo_dict.get(name, {}).get("fecha")

                if last_cached_date == u_dt:
                    # Already up to date
                    histories[name] = cached_history
                    needs_full_fetch = False
                elif last_cached_date == p_dt and u_dt:
                    # Only missed one day, we can append it directly
                    cached_history["daily"]["dates"].append(u_dt)
                    cached_history["daily"]["prices"].append(float(ultimo_dict[name]["vcp"]))
                    cached_history["weekly"]["dates"].append(u_dt)
                    cached_history["weekly"]["prices"].append(float(ultimo_dict[name]["vcp"]))
                    histories[name] = cached_history
                    needs_full_fetch = False
                    # print(f"  Appending latest data for '{name}'")
                else:
                    print(f"  Gap detected for '{name}' (cached: {last_cached_date}, penultimo: {p_dt}, ultimo: {u_dt}). Fetching full history...")
            else:
                print(f"  Fund '{name}' not in cache. Fetching full history...")

            if not needs_full_fetch:
                continue

            # Full fetch fallback
            success = False
            attempts = 0
            while attempts < 2 and not success:
                try:
                    r_hist = requests.get(url_hist, timeout=12)
                    if r_hist.status_code == 200:
                        data = r_hist.json()
                        hist_list = data.get("historico", [])

                        dates = []
                        prices = []
                        for item in sorted(hist_list, key=lambda x: x.get('fecha', '')):
                            dt = item.get('fecha')
                            val = item.get('valorCuotaparte')
                            if dt and val is not None:
                                try:
                                    prices.append(float(val))
                                    dates.append(dt)
                                except (ValueError, TypeError):
                                    continue

                        histories[name] = {
                            "daily": {"dates": dates, "prices": prices},
                            "weekly": {"dates": dates, "prices": prices}
                        }
                        success = True
                    else:
                        print(f"  Warning: Failed to fetch history for '{name}' (status: {r_hist.status_code})")
                except Exception as e:
                    print(f"  Warning: Error fetching history for '{name}': {e}")
                attempts += 1
                if not success:
                    time.sleep(0.3)

        return final_results, histories

    except Exception as e:
        print(f"Error fetching FCI details: {e}")
        return get_fallback_fci_data(), {}

