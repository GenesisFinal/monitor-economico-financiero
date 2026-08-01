import io
import requests
import zipfile
import pandas as pd
import urllib3

urllib3.disable_warnings()

def _fix_strict_xml(url):
    print(f"[SSN Retiro] Fetching {url}...")
    r = requests.get(url, verify=False)
    if r.status_code != 200:
        print(f"[SSN Retiro] Failed to fetch {url} (Status: {r.status_code})")
        return None
    
    fixed_zip = io.BytesIO()
    try:
        with zipfile.ZipFile(io.BytesIO(r.content), 'r') as zin:
            with zipfile.ZipFile(fixed_zip, 'w') as zout:
                for item in zin.infolist():
                    content = zin.read(item.filename)
                    if item.filename.endswith('.xml') or item.filename.endswith('.rels'):
                        content = content.replace(b'http://purl.oclc.org/ooxml/spreadsheetml/main', b'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
                        content = content.replace(b'http://purl.oclc.org/ooxml/officeDocument/relationships', b'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
                    zout.writestr(item, content)
        fixed_zip.seek(0)
        return fixed_zip
    except Exception as e:
        print(f"[SSN Retiro] Error fixing zip: {e}")
        return None

def _clean_entidad(name):
    if not isinstance(name, str):
        return ""
    name = name.strip().upper()
    # Remove footnote references like (2) or (3)
    import re
    name = re.sub(r'\(\d+\)$', '', name).strip()
    return name

def _safe_float(val):
    try:
        v = float(val)
        return v if not pd.isna(v) else 0.0
    except:
        return 0.0

def parse_res_mat(df, results):
    # Compromisos Técnicos: "1 Res. Mat."
    # Cols: B(1), C(2), D(3), E(4), F(5), G(6), H(7), I(8), J(9), M(12)
    start_row = None
    for idx, row in df.iterrows():
        val = str(row.iloc[0]).strip().upper()
        if val == "TOTAL":
            start_row = idx + 1
            break
            
    if start_row is None: return
    
    for idx in range(start_row, len(df)):
        entidad = _clean_entidad(df.iloc[idx, 0])
        if not entidad or pd.isna(entidad) or entidad.startswith('('): 
            continue
            
        row = df.iloc[idx]
        if entidad not in results:
            results[entidad] = {"compromisos": {}, "asegurados": {}}
            
        results[entidad]["compromisos"] = {
            "Total": _safe_float(row.iloc[1]) + _safe_float(row.iloc[12]),
            "Periodo Ahorro": _safe_float(row.iloc[2]),
            "Periodo Ahorro Indiv": _safe_float(row.iloc[3]),
            "Periodo Ahorro Col": _safe_float(row.iloc[4]),
            "Rentas Vitalicias": _safe_float(row.iloc[5]),
            "Rentas Vitalicias Indiv": _safe_float(row.iloc[6]),
            "Rentas Vitalicias Col": _safe_float(row.iloc[7]),
            "RVP y ART": _safe_float(row.iloc[8]) + _safe_float(row.iloc[9]),
            "Otros": _safe_float(row.iloc[12])
        }

def parse_stacked_asegurados(df, results, col_key_indiv, col_key_col):
    subtotal_indices = df[df.iloc[:, 0].astype(str).str.strip().str.upper() == 'SUBTOTAL'].index.tolist()
    if len(subtotal_indices) >= 2:
        # Individual
        idx_indiv = subtotal_indices[0] + 1
        for idx in range(idx_indiv, subtotal_indices[1]):
            entidad = _clean_entidad(df.iloc[idx, 0])
            if not entidad or pd.isna(entidad) or entidad.startswith('('): continue
            if entidad not in results: results[entidad] = {"compromisos": {}, "asegurados": {}}
            results[entidad]["asegurados"][col_key_indiv] = _safe_float(df.iloc[idx, 1])
            
        # Colectivo
        idx_col = subtotal_indices[1] + 1
        for idx in range(idx_col, len(df)):
            entidad = _clean_entidad(df.iloc[idx, 0])
            if not entidad or pd.isna(entidad) or entidad.startswith('('): continue
            if entidad not in results: results[entidad] = {"compromisos": {}, "asegurados": {}}
            results[entidad]["asegurados"][col_key_col] = _safe_float(df.iloc[idx, 1])

def parse_simple_asegurados(df, results, col_key):
    start_row = None
    for idx, row in df.iterrows():
        val = str(row.iloc[0]).strip().upper()
        if val == "TOTAL":
            start_row = idx + 1
            break
            
    if start_row is None: return
    
    for idx in range(start_row, len(df)):
        entidad = _clean_entidad(df.iloc[idx, 0])
        if not entidad or pd.isna(entidad) or entidad.startswith('('): 
            continue
            
        if entidad not in results:
            results[entidad] = {"compromisos": {}, "asegurados": {}}
            
        results[entidad]["asegurados"][col_key] = _safe_float(df.iloc[idx, 1])

def process_period(url):
    fixed_zip = _fix_strict_xml(url)
    if not fixed_zip: return {}
    
    try:
        xls = pd.read_excel(fixed_zip, sheet_name=None, header=None, engine='openpyxl')
    except Exception as e:
        print(f"[SSN Retiro] Failed to read fixed excel: {e}")
        return {}
        
    results = {}
    
    # 1 Res. Mat.
    df_res_mat = xls.get("1 Res. Mat.")
    if df_res_mat is not None:
        parse_res_mat(df_res_mat, results)
        
    # 3 Aseg.  Indiv y  Colec
    df_aseg3 = xls.get("3 Aseg.  Indiv y  Colec")
    if df_aseg3 is not None:
        parse_stacked_asegurados(df_aseg3, results, "ahorro_indiv", "ahorro_col")
        
    # 4 Rentistas Indiv y Colec
    df_aseg4 = xls.get("4 Rentistas Indiv y Colec")
    if df_aseg4 is not None:
        parse_stacked_asegurados(df_aseg4, results, "renta_indiv", "renta_col")
        
    # 5 Rentistas Previsional
    df_aseg5 = xls.get("5 Rentistas Previsional")
    if df_aseg5 is not None:
        parse_simple_asegurados(df_aseg5, results, "renta_prev_1")
        
    # 6 Rentistas ART
    df_aseg6 = xls.get("6 Rentistas ART ") # Notice the trailing space in some versions
    if df_aseg6 is None: df_aseg6 = xls.get("6 Rentistas ART")
    if df_aseg6 is not None:
        parse_simple_asegurados(df_aseg6, results, "renta_prev_2")
        
    # Consolidate Asegurados
    for entidad, data in results.items():
        aseg = data["asegurados"]
        # Default 0.0 for missing keys
        for k in ["ahorro_indiv", "ahorro_col", "renta_indiv", "renta_col", "renta_prev_1", "renta_prev_2"]:
            if k not in aseg: aseg[k] = 0.0
            
        aseg["Ahorro Indiv"] = aseg["ahorro_indiv"]
        aseg["Ahorro Col"] = aseg["ahorro_col"]
        aseg["Periodo Ahorro"] = aseg["Ahorro Indiv"] + aseg["Ahorro Col"]
        
        aseg["Renta Indiv"] = aseg["renta_indiv"]
        aseg["Renta Col"] = aseg["renta_col"]
        aseg["Renta Previsional"] = aseg["renta_prev_1"] + aseg["renta_prev_2"]
        aseg["Periodo Renta"] = aseg["Renta Indiv"] + aseg["Renta Col"] + aseg["Renta Previsional"]
        
        aseg["Cantidad Total"] = aseg["Periodo Ahorro"] + aseg["Periodo Renta"]
        
    return results

def get_possible_retiro_urls(period):
    year = period[:4]
    month = period[4:]
    
    urls = []
    # 1. Standard format
    urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{period}_reserva_matematica.xlsx")
    
    # 2. Named month format (mar, jun, sep, dic) used in 2025
    month_map = {"03": "mar", "06": "jun", "09": "sep", "12": "dic"}
    if month in month_map:
        named_month = month_map[month]
        urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{year}_{named_month}_reserva_matematica.xlsx")
        
    return urls

def fetch_retiro_data(period_current="202603", period_prev="202503"):
    print(f"[SSN Retiro] Fetching data for periods {period_current} and {period_prev}...")
    
    data_curr = {}
    for url in get_possible_retiro_urls(period_current):
        data_curr = process_period(url)
        if data_curr: break
        
    data_prev = {}
    for url in get_possible_retiro_urls(period_prev):
        data_prev = process_period(url)
        if data_prev: break
    
    # Merge and calculate YoY
    final_data = {}
    
    all_entidades = set(list(data_curr.keys()) + list(data_prev.keys()))
    
    def calc_yoy(curr_val, prev_val):
        if prev_val == 0:
            return 0.0 if curr_val == 0 else 100.0
        return ((curr_val - prev_val) / abs(prev_val)) * 100
        
    for entidad in all_entidades:
        curr = data_curr.get(entidad, {"compromisos": {}, "asegurados": {}})
        prev = data_prev.get(entidad, {"compromisos": {}, "asegurados": {}})
        
        # Build structure for entity
        final_data[entidad] = {
            "compromisos": {},
            "asegurados": {}
        }
        
        # Keys to process
        comp_keys = ["Total", "Periodo Ahorro", "Periodo Ahorro Indiv", "Periodo Ahorro Col", "Rentas Vitalicias", "Rentas Vitalicias Indiv", "Rentas Vitalicias Col", "RVP y ART", "Otros"]
        for k in comp_keys:
            c_val = curr["compromisos"].get(k, 0.0)
            p_val = prev["compromisos"].get(k, 0.0)
            final_data[entidad]["compromisos"][k] = {
                "val": c_val,
                "yoy": calc_yoy(c_val, p_val)
            }
            
        aseg_keys = ["Cantidad Total", "Periodo Ahorro", "Ahorro Indiv", "Ahorro Col", "Periodo Renta", "Renta Indiv", "Renta Col", "Renta Previsional"]
        for k in aseg_keys:
            c_val = curr["asegurados"].get(k, 0.0)
            p_val = prev["asegurados"].get(k, 0.0)
            final_data[entidad]["asegurados"][k] = {
                "val": c_val,
                "yoy": calc_yoy(c_val, p_val)
            }
            
    # Remove entities that have 0 total in current year to keep list clean
    final_data = {k: v for k, v in final_data.items() if v["compromisos"]["Total"]["val"] > 0 or v["asegurados"]["Cantidad Total"]["val"] > 0}
    
    # Calculate market totals for percentage calculation (only current year)
    total_compromisos = sum(v["compromisos"]["Total"]["val"] for v in final_data.values())
    total_ahorro = sum(v["compromisos"]["Periodo Ahorro"]["val"] for v in final_data.values())
    total_rentas = sum(v["compromisos"]["Rentas Vitalicias"]["val"] for v in final_data.values())
    
    for k, v in final_data.items():
        # calculate percentages
        v["compromisos"]["Total"]["pct"] = (v["compromisos"]["Total"]["val"] / total_compromisos * 100) if total_compromisos > 0 else 0
        v["compromisos"]["Periodo Ahorro"]["pct"] = (v["compromisos"]["Periodo Ahorro"]["val"] / total_ahorro * 100) if total_ahorro > 0 else 0
        v["compromisos"]["Rentas Vitalicias"]["pct"] = (v["compromisos"]["Rentas Vitalicias"]["val"] / total_rentas * 100) if total_rentas > 0 else 0
        
    # Sort final_data by Compromisos Total by default, but it's a dict so we just return it. 
    # Sorting can be done in Jinja or returned as a sorted list.
    # Let's return as a list of dicts to preserve order and make jinja easier.
    
    final_list = []
    for k, v in final_data.items():
        v["Entidad"] = k
        final_list.append(v)
        
    # Sort by Compromisos Total descending
    final_list.sort(key=lambda x: x["compromisos"]["Total"]["val"], reverse=True)
    
    return final_list
