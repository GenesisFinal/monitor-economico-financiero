import pandas as pd
import requests
import io
import urllib3
import logging

urllib3.disable_warnings()

def get_previous_period(period_str):
    # period_str format "YYYYMM" e.g. "202603"
    year = int(period_str[:4])
    month = period_str[4:]
    return f"{year - 1}{month}"

def parse_row(row, sheet_type):
    def get_val(idx):
        try:
            v = float(row[idx])
            return v if not pd.isna(v) else 0.0
        except:
            return 0.0

    if sheet_type == "patrimoniales":
        return {
            "Disponibilidades": get_val(3),
            "Inversiones": get_val(4),
            "Créditos": get_val(5),
            "Inmuebles": get_val(6),
            "Bienes de Uso": get_val(7),
            "Otros": get_val(8),
            "Activos": get_val(9),
            "Deudas c/Asegurados": get_val(10),
            "Otras Deudas": get_val(11),
            "Compromisos Técnicos": get_val(12),
            "Previsiones": get_val(13),
            "Pasivo": get_val(14),
            "Patrimonio Neto": get_val(15),
        }
    elif sheet_type == "resultados":
        return {
            "Resultado Técnico Seg. Directo": get_val(3),
            "Resultado Técnico Reaseg. Activo": get_val(4),
            "Otros Ingresos": get_val(5),
            "Otros Egresos": get_val(6),
            "Resultado Técnico": get_val(7),
            "Resultado Financiero": get_val(8),
            "Rdo. Operaciones Ordinarias": get_val(9),
            "Rdo. Operaciones Extraordinarias": get_val(10),
            "Impuesto a las Ganancias": get_val(11),
            "Resultado del Ejercicio": get_val(12),
        }
    elif sheet_type == "tecnico":
        return {
            "Primas Netas Devengadas": get_val(3),
            "Siniestros Netos Devengados": get_val(4),
            "Rescates": get_val(5),
            "Rentas Vitalicias y Periódicas": get_val(6),
            "Gastos Totales": get_val(7),
            "Total Resultado Técnico de Seguros Directos": get_val(8),
            "Total Resultado Técnico de Reaseguros Activos": get_val(12),
            "Gastos de Prevención": get_val(13),
            "Otros Ingresos": get_val(14),
            "Otros Egresos": get_val(15),
            "Otras Indemnizaciones y Beneficios": get_val(16),
            "Resultado Técnico Total": get_val(17),
        }
    elif sheet_type == "financiero":
        return {
            "Rentas": get_val(3),
            "Resultados por Realización": get_val(4),
            "Resultados por Tenencia": get_val(5),
            "Otros Ingresos": get_val(6),
            "Otros Egresos": get_val(7),
            "Gastos de Explotación y Otros Cargos": get_val(8),
            "RECPAM": get_val(9),
            "Resultado Financiero Total": get_val(10),
        }
    return {}

def fetch_sheet_data(df, sheet_type):
    data = {}
    current_segment = None
    
    # Exact mappings matching SSN's typos and conventions
    segment_map = {
        "TOTAL DE MERCADO": "Total del Mercado",
        "Seguros Patrimoniales": "Seguros Patrimoniales",
        "Patrimoniales y Mixtas": "Seguros Patrimoniales",
        "Exclusivas Riesgos del Trabajo": "Riesgos del Trabajo",
        "Riesgos del Trabajo": "Riesgos del Trabajo",
        "Exclusivas Transporte Pblico Pasajeros": "Transporte Pblico de Pasajeros",
        "Exclusivas Transporte Pblico Pasajeros": "Transporte Pblico de Pasajeros",
        "Operatoria Mixta (Patrim. / Pers.)": "Empresas Mixtas",
        "Seguros de Personas": "Seguros de Personas",
        "Seguros de Vida": "Seguros de Personas",
        "Exclusivas Retiro": "Exclusivas de Retiro",
        "Seguros de Retiro": "Exclusivas de Retiro",
    }
    
    for i, row in df.iterrows():
        col0 = row[0]
        col1 = str(row[1]).strip() if pd.notna(row[1]) else ""
        col2 = str(row[2]).strip() if pd.notna(row[2]) else ""
        
        found_segment = None
        for key in segment_map:
            if key in col1 or key in col2:
                found_segment = segment_map[key]
                break
        
        if pd.isna(col0) and found_segment:
            current_segment = found_segment
            if current_segment not in data:
                data[current_segment] = {}
            
            company_name = f"Total {current_segment}" if current_segment != "Total del Mercado" else "Total del Mercado"
            data[current_segment][company_name] = parse_row(row, sheet_type)
            
        elif current_segment and not pd.isna(col0) and isinstance(col0, (int, float)):
            company_name = col2
            data[current_segment][company_name] = parse_row(row, sheet_type)
            
    return data

def process_period_excel(url):
    logging.info(f"Downloading balances from: {url}")
    try:
        r = requests.get(url, verify=False, timeout=30)
        if r.status_code != 200:
            logging.error(f"Failed to fetch {url}")
            return {}
    except Exception as e:
        logging.error(f"Network error fetching {url}: {e}")
        return {}
        
    xls = pd.ExcelFile(io.BytesIO(r.content))
    
    sheet_patrimoniales = None
    sheet_resultados = None
    sheet_tecnico = None
    sheet_financiero = None
    
    for s in xls.sheet_names:
        if s.startswith('1'): sheet_patrimoniales = s
        elif s.startswith('2'): sheet_resultados = s
        elif s.startswith('3'): sheet_tecnico = s
        elif s.startswith('5'): sheet_financiero = s
        
    res = {}
    if sheet_patrimoniales:
        res["patrimoniales"] = fetch_sheet_data(pd.read_excel(xls, sheet_name=sheet_patrimoniales, header=None), "patrimoniales")
    if sheet_resultados:
        res["resultados"] = fetch_sheet_data(pd.read_excel(xls, sheet_name=sheet_resultados, header=None), "resultados")
    if sheet_tecnico:
        res["tecnico"] = fetch_sheet_data(pd.read_excel(xls, sheet_name=sheet_tecnico, header=None), "tecnico")
    if sheet_financiero:
        res["financiero"] = fetch_sheet_data(pd.read_excel(xls, sheet_name=sheet_financiero, header=None), "financiero")
        
    return res

def get_possible_urls(period):
    year = period[:4]
    month = period[4:]
    urls = []
    # 1. Standard format (used in 2026 onwards)
    urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{period}_estados_patrimoniales.xlsx")
    
    # 2. Quarter format (used in 2025)
    quarter = "0" + str((int(month) - 1) // 3 + 1)
    q_period = year + quarter
    urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{q_period}_estados_patrimoniales.xlsx")
    urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{q_period}_estados_patrimoniales.xls")
    urls.append(f"https://www.argentina.gob.ar/sites/default/files/ssn_{period}_estados_patrimoniales.xls")
    return urls

def fetch_balances_data(current_period="202603"):
    print(f"[SSN Balances] Fetching data for period {current_period}...")
    prev_period = get_previous_period(current_period)
    
    data_curr = {}
    for url in get_possible_urls(current_period):
        data_curr = process_period_excel(url)
        if data_curr: break
        
    data_prev = {}
    for url in get_possible_urls(prev_period):
        data_prev = process_period_excel(url)
        if data_prev: break
    
    if not data_curr:
        print("[SSN Balances] Error: Current period data not found.")
        return {}
        
    # TODO: When the previous year also has the "Empresas Mixtas" separated, revert this logic.
    # We are adding "Empresas Mixtas" -> "Total del Mercado" into "Seguros Patrimoniales" -> "Total del Mercado"
    # so that the 2026 vs 2025 YoY comparison for Patrimoniales is accurate (since in 2025 they were merged).
    if data_curr:
        for sheet_type in data_curr:
            if "Empresas Mixtas" in data_curr[sheet_type] and "Seguros Patrimoniales" in data_curr[sheet_type]:
                mixtas_total = data_curr[sheet_type]["Empresas Mixtas"].get("Total Empresas Mixtas")
                patrimoniales_total = data_curr[sheet_type]["Seguros Patrimoniales"].get("Total Seguros Patrimoniales")
                if mixtas_total and patrimoniales_total:
                    for key, val in mixtas_total.items():
                        if key in patrimoniales_total:
                            patrimoniales_total[key] += val
                        else:
                            patrimoniales_total[key] = val
        
    # Combine data into { segment: { company: { period: { sheet: { data } } } } }
    combined = {}
    
    # We will iterate through current data as the source of truth for segments and companies
    for sheet_type, segments in data_curr.items():
        for segment, companies in segments.items():
            if segment not in combined:
                combined[segment] = {}
                
            for company, metrics in companies.items():
                if company not in combined[segment]:
                    combined[segment][company] = {
                        current_period: {},
                        prev_period: {}
                    }
                combined[segment][company][current_period][sheet_type] = metrics
                
    # Now merge previous data
    if data_prev:
        for sheet_type, segments in data_curr.items():
            for segment, companies in segments.items():
                for company in companies:
                    # Try to get previous period data
                    prev_company_data = None
                    if sheet_type in data_prev:
                        if segment in data_prev[sheet_type] and company in data_prev[sheet_type][segment]:
                            prev_company_data = data_prev[sheet_type][segment][company]
                        else:
                            # Fallback: company might have changed segments between years
                            for prev_seg in data_prev[sheet_type].values():
                                if company in prev_seg:
                                    prev_company_data = prev_seg[company]
                                    break
                                    
                    if prev_company_data:
                        combined[segment][company][prev_period][sheet_type] = prev_company_data
                        
    return combined

if __name__ == "__main__":
    data = fetch_balances_data("202603")
    print("Segments loaded:", list(data.keys()))
    if "Total del Mercado" in data:
        print("Total Mercado, patrimoniales, 202603:")
        print(data["Total del Mercado"]["Total del Mercado"]["202603"]["patrimoniales"])
