from datetime import datetime
import urllib.request, json, ssl, time, math
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        res = urllib.request.urlopen(req, context=ctx, timeout=6).read().decode('utf-8')
        return json.loads(res)
    except Exception:
        return None

def fetch_yahoo_ticker(ticker):
    candidates = [ticker]
    if not any(c in ticker for c in ['.', '^', '=']):
        candidates.append(ticker + '.BA')
        candidates.append(ticker + 'D.BA')

    for c in candidates:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(c)}?interval=1d"
        data = fetch_json(url)
        if data and "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose", meta.get("chartPreviousClose"))
            if price is not None:
                return ticker, float(price), float(prev_close) if prev_close else None
    return ticker, None, None

def update_master_dataset_live():
    print("==========================================================================")
    print("SWEEPING ALL FINANCIAL ASSETS FOR LIVE MARKET UPDATE...")
    print("==========================================================================")
    
    with open("master_dataset.json", "r", encoding="utf-8") as f:
        ds = json.load(f)

    final_data = ds.get("final_data", {})
    updated_counts = {}

    # 1. UPDATE DÓLARES & COTIZACIONES (DolarApi & ArgentinaDatos)
    dolar_resp = fetch_json("https://dolarapi.com/v1/dolares")
    cotiz_resp = fetch_json("https://dolarapi.com/v1/cotizaciones")
    
    dolar_map = {}
    if isinstance(dolar_resp, list):
        for d in dolar_resp:
            casa = d.get("casa")
            venta = d.get("venta")
            if casa and venta:
                dolar_map[casa] = venta
    
    if isinstance(cotiz_resp, list):
        for c in cotiz_resp:
            moneda = c.get("moneda")
            venta = c.get("venta")
            if moneda and venta:
                dolar_map[moneda.lower()] = venta

    if "dolar" in final_data and isinstance(final_data["dolar"], list):
        for item in final_data["dolar"]:
            casa = item.get("casa")
            if casa in dolar_map:
                item["venta"] = dolar_map[casa]
                item["price"] = dolar_map[casa]
        updated_counts["dolar"] = len(dolar_map)
        print(f"[LIVE UPDATER] Updated {len(dolar_map)} Dollar / Forex rates via DolarApi.")

    # 2. UPDATE RIESGO PAÍS (ArgentinaDatos)
    rp_data = fetch_json("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais")
    if rp_data and isinstance(rp_data, list) and len(rp_data) > 0:
        latest = rp_data[-1]
        val = latest.get("valor")
        fecha = latest.get("fecha")
        if val:
            final_data["country_risk_latest"] = str(val)
            final_data["country_risk_date"] = str(fecha)
            print(f"[LIVE UPDATER] Updated Riesgo Pais: {val} pts (Date: {fecha}).")

    # 3. PARALLEL YAHOO FINANCE SWEEP (Indices, Forex, Commodities, ETFs, Acciones, CEDEARs, Bonds)
    all_tickers = set()

    categories_to_sweep = ['indices', 'forex', 'commodities', 'etfs', 'acciones_arg', 'cryptos', 'rates', 'local_rates', 'lecaps', 'stocks', 'cedears']
    for cat in categories_to_sweep:
        items = final_data.get(cat, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("ticker"):
                    all_tickers.add(item.get("ticker"))

    bonds = final_data.get("bonds", {})
    if isinstance(bonds, dict):
        for b_type, b_list in bonds.items():
            if isinstance(b_list, list):
                for b in b_list:
                    if isinstance(b, dict) and b.get("ticker"):
                        all_tickers.add(b.get("ticker"))

    print(f"[LIVE UPDATER] Launching parallel sweep for {len(all_tickers)} market tickers...")
    
    live_results = {}
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(fetch_yahoo_ticker, t): t for t in all_tickers}
        for future in as_completed(futures):
            ticker, price, prev_close = future.result()
            if price is not None:
                live_results[ticker] = (price, prev_close)

    print(f"[LIVE UPDATER] Successfully fetched {len(live_results)} / {len(all_tickers)} live asset prices.")

    # Apply fetched prices to final_data categories
    for cat in categories_to_sweep:
        items = final_data.get(cat, [])
        count = 0
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    t = item.get("ticker")
                    if t in live_results:
                        price, prev_close = live_results[t]
                        item["price"] = price
                        if prev_close and prev_close > 0:
                            chg_pct = round(((price - prev_close) / prev_close) * 100, 2)
                            item["change"] = chg_pct
                            item["change_val"] = chg_pct
                        count += 1
        updated_counts[cat] = count

    # Apply fetched prices to Bonds
    if isinstance(bonds, dict):
        for b_type, b_list in bonds.items():
            count = 0
            if isinstance(b_list, list):
                for b in b_list:
                    if isinstance(b, dict):
                        t = b.get("ticker")
                        if t in live_results:
                            price, prev_close = live_results[t]
                            b["price"] = f"{price:.2f}"
                            if prev_close and prev_close > 0:
                                chg_pct = round(((price - prev_close) / prev_close) * 100, 2)
                                b["change"] = chg_pct
                            count += 1
            updated_counts[f"bonds_{b_type}"] = count

    # Save updated dataset
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S hs")
    ds["last_updated"] = now_str
    final_data["update_time_financial"] = now_str
    ds["final_data"] = final_data
    with open("master_dataset.json", "w", encoding="utf-8") as f:
        json.dump(ds, f, ensure_ascii=False, indent=2)

    print("==========================================================================")
    print(f"COMPLETE 100% MARKET SWEEP SUCCESSFUL! Summary of updated categories:")
    for k, v in updated_counts.items():
        print(f"  - {k:20s}: {v} assets updated")
    print("==========================================================================")

if __name__ == "__main__":
    update_master_dataset_live()
