import os
import glob
import json
import pandas as pd
from datetime import datetime
import re

# Import the existing grouping logic from the main fetcher
# Since the fetcher uses an internal helper, we might need to redefine it or import it.
# To ensure no breakage and perfect independence, we will redefine the logic here cleanly.

def clean_entidad(name):
    if not isinstance(name, str):
        return ""
    return name.strip().upper()

def parse_ssn_excel(filepath):
    """Parses a single SSN excel file and returns the rankings dictionary."""
    print(f"[Historical] Parsing {filepath}...")
    try:
        xls = pd.read_excel(filepath, sheet_name=None, header=None)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None
        
    results = {}
    
    # helper to find where the data starts
    def find_header_row(sheet_df):
        for i in range(min(15, len(sheet_df))):
            row_vals = [str(x).lower().strip() for x in sheet_df.iloc[i].values]
            if "entidad" in row_vals or "entidad " in row_vals:
                return i
        return 4 # fallback
        
    # =====================================================================
    # SHEET 1: Total de Primas del Mercado y Grupos Aseguradores
    # =====================================================================
    sheet1_name = None
    for s in xls.keys():
        if s.startswith("1-") or s.startswith("1 -"):
            sheet1_name = s
            break
            
    if sheet1_name:
        sheet1 = xls[sheet1_name]
        start_row = find_header_row(sheet1) + 1
        df1 = sheet1.iloc[start_row:].copy()
        
        # We need to map columns since they might shift. 
        # Usually it's Orden, NJ, Entidad, Prima, Part_pct
        # Let's just use column indices assuming Entidad is col 2 and Prima is col 3
        
        # Find exact columns
        header_row = sheet1.iloc[start_row - 1]
        entidad_col = -1
        prima_col = -1
        for col_idx, val in enumerate(header_row):
            val_str = str(val).lower()
            if "entidad" in val_str:
                entidad_col = col_idx
            elif "prima" in val_str and prima_col == -1: # take the first prima column
                prima_col = col_idx
                
        if entidad_col != -1 and prima_col != -1:
            df1_clean = pd.DataFrame({
                "Entidad": df1.iloc[:, entidad_col],
                "Prima": df1.iloc[:, prima_col]
            })
            df1_clean = df1_clean.dropna(subset=["Entidad", "Prima"])
            df1_clean["Entidad"] = df1_clean["Entidad"].apply(clean_entidad)
            df1_clean["Prima"] = pd.to_numeric(df1_clean["Prima"], errors='coerce').fillna(0)
            
            # --- Total del Mercado ---
            df1_sorted = df1_clean.sort_values(by="Prima", ascending=False).reset_index(drop=True)
            df1_sorted["posicion"] = df1_sorted.index + 1
            
            tm_data = []
            for row in df1_sorted.itertuples():
                tm_data.append({"posicion": int(row.posicion), "entidad": row.Entidad, "prima": float(row.Prima)})
            results["total_mercado"] = tm_data
            
            # --- Grupos Aseguradores ---
            grupos_rules = {
                "Sancor Seguros": ["SANCOR", "PREVENC"],
                "Federación Patronal": ["FED. PATRONAL", "FEDERACION PATRONAL"],
                "Provincia (Grupo Bapro)": ["PROVINCIA SEGUROS", "PROVINCIA ART", "PROVINCIA VIDA", "EXACT:PROVINCIA"],
                "San Cristóbal": ["SAN CRIST", "ASOCIART", "IUNIGO", "INIGO"],
                "Zurich Argentina": ["ZURICH"],
                "La Segunda": ["SEGUNDA"], 
                "Generali / La Caja": ["CAJA DE AHORRO Y SEGURO", "CAJA DE SEGUROS", "CAJA GENERALES", "CAJA SEGUROS", "CAJA VIDA", "INSTITUTO DEL SEGURO DE MISIONES", "GENERALI"],
                "Mercantil Andina": ["MERCANTIL ANDINA", "ANDINA ART"],
                "Nación Seguros": ["NACION SEGUROS", "NACIN SEGUROS", "NACION REASEGUROS", "NACIN REASEGUROS"],
                "Bernardino Rivadavia": ["BERNARDINO RIVADAVIA", "RIVADAVIA SEGUROS"],
                "Galicia (GGAL)": ["GALICIA", "SURA"],
                "Werthein": ["EXPERTA", "ESTRELLA"],
                "Swiss Medical": ["SWISS MEDICAL"],
                "Grupo ST": ["LIFE", "ORIGENES", "ORGENES", "CARTERAS ADQUIRIDAS"]
            }
            
            grupos_totals = {g: 0.0 for g in grupos_rules.keys()}
            
            for row in df1_clean.itertuples():
                ent = row.Entidad
                for g_name, rules in grupos_rules.items():
                    matched = False
                    for rule in rules:
                        if rule.startswith("EXACT:"):
                            if ent == rule.split("EXACT:")[1]:
                                matched = True
                                break
                        elif rule in ent:
                            matched = True
                            break
                    if matched:
                        grupos_totals[g_name] += row.Prima
                        break 
                        
            grupos_df = pd.DataFrame(list(grupos_totals.items()), columns=["Grupo", "Prima"])
            grupos_df = grupos_df[grupos_df["Prima"] > 0].sort_values(by="Prima", ascending=False).reset_index(drop=True)
            grupos_df["posicion"] = grupos_df.index + 1
            
            ga_data = []
            for row in grupos_df.itertuples():
                ga_data.append({"posicion": int(row.posicion), "entidad": row.Grupo, "prima": float(row.Prima)})
            results["grupos_aseguradores"] = ga_data

    # Helper for segments (patrimoniales, personas, etc)
    def process_segment_sheet(sheet_name_start, result_key, ramo_filter_fn=None):
        sheet_name = None
        for s in xls.keys():
            if s.startswith(sheet_name_start):
                sheet_name = s
                break
        if sheet_name:
            sheet_df = xls[sheet_name]
            start_row = find_header_row(sheet_df) + 1
            header_row = sheet_df.iloc[start_row - 1]
            
            entidad_col = -1
            prima_col = -1
            ramo_col = -1
            
            for col_idx, val in enumerate(header_row):
                val_str = str(val).lower()
                if "entidad" in val_str:
                    entidad_col = col_idx
                elif "prima" in val_str and prima_col == -1:
                    prima_col = col_idx
                elif "ramo" in val_str:
                    ramo_col = col_idx
                    
            if entidad_col != -1 and prima_col != -1:
                cols = {"Entidad": sheet_df.iloc[start_row:, entidad_col], "Prima": sheet_df.iloc[start_row:, prima_col]}
                if ramo_col != -1:
                    cols["Ramos"] = sheet_df.iloc[start_row:, ramo_col]
                    
                df_seg = pd.DataFrame(cols)
                df_seg = df_seg.dropna(subset=["Entidad", "Prima"])
                df_seg["Entidad"] = df_seg["Entidad"].apply(clean_entidad)
                df_seg["Prima"] = pd.to_numeric(df_seg["Prima"], errors='coerce').fillna(0)
                
                if ramo_filter_fn and "Ramos" in df_seg.columns:
                    df_seg["Ramos"] = df_seg["Ramos"].astype(str).str.upper().str.strip()
                    df_seg = df_seg[df_seg["Ramos"].apply(ramo_filter_fn)]
                    
                entity_sums = df_seg.groupby("Entidad")["Prima"].sum().reset_index()
                entity_sums = entity_sums[entity_sums["Prima"] > 0]
                entity_sums = entity_sums.sort_values(by="Prima", ascending=False).reset_index(drop=True)
                entity_sums["posicion"] = entity_sums.index + 1
                
                seg_data = []
                for row in entity_sums.itertuples():
                    seg_data.append({"posicion": int(row.posicion), "entidad": row.Entidad, "prima": float(row.Prima)})
                results[result_key] = seg_data

    # Seguros Patrimoniales
    process_segment_sheet("2-", "patrimoniales")
    process_segment_sheet("2-", "automotores", lambda r: "AUTOMOTORES" in r or "MOTOVEH" in r or "MOTO VEH" in r)
    # Riesgos Agropecuarios
    process_segment_sheet("2-", "agro", lambda r: "RA Y F" in r or "GRANIZO" in r or "GANADO" in r or "AGRO" in r)
    # Otros Riesgos Patrimoniales
    process_segment_sheet("2-", "otros_patrimoniales", lambda r: "OTROS RIESGOS PATRIMONIALES" in r)
    # Seguros de Personas
    process_segment_sheet("3-", "personas")
    # Seguros de Vida
    process_segment_sheet("3-", "vida", lambda r: "VIDA" in r)
    # Accidentes Personales
    process_segment_sheet("3-", "accidentes_personales", lambda r: "ACC. PERSONALES" in r or "ACCIDENTES PERSONALES" in r)
    # Retiro
    process_segment_sheet("3-", "retiro", lambda r: "RETIRO" in r)
    # Sepelio
    process_segment_sheet("3-", "sepelio", lambda r: "SEPELIO" in r)
    # Salud
    process_segment_sheet("3-", "salud", lambda r: "SALUD" in r)
    # Riesgos del Trabajo
    # A veces está en una hoja "4-", a veces dentro de "2- Patrimoniales" como "RIESGOS DEL TRABAJO"
    process_segment_sheet("4-", "art")
    if "art" not in results or len(results["art"]) == 0:
        process_segment_sheet("2-", "art", lambda r: "RIESGOS DEL TRABAJO" in r or "ACCIDENTES DEL TRABAJO" in r)

    return results

def get_date_from_filename(filename):
    # ssn_202312_prod... -> 2023-12-01
    m = re.search(r'ssn_(\d{4})(\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    if '152' in filename:
        return "2023-09"
    return "2000-01"

def build_historical_rankings():
    files = glob.glob("data/historico_ssn/*.xlsx")
    files_with_dates = [(f, get_date_from_filename(f)) for f in files]
    # Sort chronologically
    files_with_dates.sort(key=lambda x: x[1])
    
    historical_data = {
        "grupos_aseguradores": {},
        "total_mercado": {},
        "patrimoniales": {},
        "automotores": {},
        "agro": {},
        "otros_patrimoniales": {},
        "personas": {},
        "vida": {},
        "accidentes_personales": {},
        "retiro": {},
        "sepelio": {},
        "salud": {},
        "art": {}
    }
    
    quarters_list = []
    
    for filepath, date_str in files_with_dates:
        print(f"Processing quarter: {date_str} from {filepath}")
        quarters_list.append(date_str)
        ranks = parse_ssn_excel(filepath)
        
        if not ranks:
            continue
            
        for segment, segment_ranks in ranks.items():
            if segment not in historical_data:
                continue
            
            # Find Top 3 and La Segunda
            # For groups, 'La Segunda'. For total_mercado, it's "LA SEGUNDA COOP...", "LA SEGUNDA ART", etc.
            # So let's just match "SEGUNDA" inside the entity name for La Segunda.
            
            top3 = segment_ranks[:3]
            
            la_seg_entries = [r for r in segment_ranks if "SEGUNDA" in r["entidad"].upper()]
            
            # We will store the full array of selected entities for this quarter.
            # To plot correctly on frontend, we will store: 
            # entity_name -> [pos_q1, pos_q2, ...]
            # We will build this structure in frontend if we have the list.
            # But let's build the ready-to-use structure here.
            
            # For each tracked entity, append its position for this quarter
            # If not in top 3 and not la segunda, we don't care.
            tracked_entities_dict = {}
            for ent_data in top3 + la_seg_entries:
                tracked_entities_dict[ent_data["entidad"]] = ent_data
            
            tracked_entities = list(tracked_entities_dict.values())
            
            for ent_data in tracked_entities:
                e_name = ent_data["entidad"]
                e_pos = ent_data["posicion"]
                
                if e_name not in historical_data[segment]:
                    # initialize with nulls for past quarters
                    historical_data[segment][e_name] = [None] * (len(quarters_list) - 1)
                
                historical_data[segment][e_name].append(e_pos)
                
            # Pad any previously tracked entity that wasn't found in this quarter
            for e_name in historical_data[segment].keys():
                if len(historical_data[segment][e_name]) < len(quarters_list):
                    historical_data[segment][e_name].append(None)
                    
    # Format output
    output = {
        "quarters": quarters_list,
        "segments": historical_data
    }
    
    with open("data/historical_rankings.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    print("Historical rankings generated successfully.")

if __name__ == "__main__":
    build_historical_rankings()
