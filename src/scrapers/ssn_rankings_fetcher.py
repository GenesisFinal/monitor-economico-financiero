import os
import io
import requests
import pandas as pd
import json

def fetch_ssn_rankings():
    print("[SSN Rankings] Fetching SSN Quarterly Production Data...")
    url = "https://www.argentina.gob.ar/sites/default/files/ssn_202603_prod_trimestral_boletin.xlsx"
    
    try:
        r = requests.get(url, verify=False, timeout=30)
        if r.status_code != 200:
            print(f"[SSN Rankings] Error {r.status_code} downloading {url}")
            return None
            
        xls = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
        
        results = {}
        
        # Helper to safely clean entity names
        def clean_entidad(name):
            if not isinstance(name, str):
                return ""
            return name.strip().upper()
            
        # =====================================================================
        # SHEET 1: Total de Primas del Mercado y Grupos Aseguradores
        # =====================================================================
        sheet1 = xls.get("1- Total de Primas del Mercado")
        if sheet1 is not None:
            # Data starts at row 4
            df1 = sheet1.iloc[4:].copy()
            df1.columns = ["Orden", "NJ", "Entidad", "Prima", "Part_pct"]
            df1 = df1.dropna(subset=["Entidad", "Prima"])
            df1["Entidad"] = df1["Entidad"].apply(clean_entidad)
            df1["Prima"] = pd.to_numeric(df1["Prima"], errors='coerce').fillna(0)
            
            # --- Total del Mercado (Top 50) ---
            df1_sorted = df1.sort_values(by="Prima", ascending=False).head(50).copy()
            total_mercado_prima = df1["Prima"].sum()
            df1_sorted["Part_pct"] = (df1_sorted["Prima"] / total_mercado_prima * 100).round(2)
            
            tm_data = []
            for i, row in enumerate(df1_sorted.itertuples(), 1):
                tm_data.append({
                    "posicion": i,
                    "entidad": row.Entidad,
                    "prima": float(row.Prima),
                    "participacion": float(row.Part_pct)
                })
            results["total_mercado"] = tm_data
            
            # --- Grupos Aseguradores ---
            grupos_rules = {
                "Sancor Seguros": ["SANCOR", "PREVENC"],
                "Federación Patronal": ["FED. PATRONAL", "FEDERACION PATRONAL"],
                "Provincia (Grupo Bapro)": ["PROVINCIA SEGUROS", "PROVINCIA ART", "PROVINCIA VIDA", "EXACT:PROVINCIA"],
                "San Cristóbal": ["SAN CRIST", "ASOCIART", "IUNIGO", "INIGO"],
                "Zurich Argentina": ["ZURICH"],
                "La Segunda": ["SEGUNDA"], # Matches SEGUNDA, LA SEGUNDA ART, SEGUNDA PERSONAS, SEGUNDA RETIRO
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
            
            for row in df1.itertuples():
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
                        break # mapped to one group
                        
            grupos_df = pd.DataFrame(list(grupos_totals.items()), columns=["Grupo", "Prima"])
            grupos_df = grupos_df[grupos_df["Prima"] > 0]
            grupos_df = grupos_df.sort_values(by="Prima", ascending=False).reset_index(drop=True)
            grupos_df["Part_pct"] = (grupos_df["Prima"] / total_mercado_prima * 100).round(2)
            
            ga_data = []
            for i, row in enumerate(grupos_df.itertuples(), 1):
                ga_data.append({
                    "posicion": i,
                    "entidad": row.Grupo,
                    "prima": float(row.Prima),
                    "participacion": float(row.Part_pct)
                })
            results["grupos_aseguradores"] = ga_data

            # --- Grupo La Segunda ---
            la_segunda_data = {
                "empresas": [],
                "total_grupo": 0,
                "patrimoniales": {"total": 0, "ramos": []},
                "personas": {"total": 0, "ramos": []}
            }
            
            empresas_target = ["SEGUNDA", "SEGUNDA ART", "SEGUNDA PERSONAS", "SEGUNDA RETIRO"]
            for ent in empresas_target:
                row_ls = df1[df1["Entidad"] == ent]
                if not row_ls.empty:
                    prima_ls = float(row_ls["Prima"].iloc[0])
                    ent_display = "SEGUNDA COOP" if ent == "SEGUNDA" else ent
                    la_segunda_data["empresas"].append({"entidad": ent_display, "prima": prima_ls})
                    la_segunda_data["total_grupo"] += prima_ls
                    
            if la_segunda_data["total_grupo"] > 0:
                for emp in la_segunda_data["empresas"]:
                    emp["participacion"] = round((emp["prima"] / la_segunda_data["total_grupo"]) * 100, 2)
                    
            # 2. Patrimoniales
            sheet2 = xls.get("2- Seguros Patrimoniales")
            if sheet2 is not None:
                df2 = sheet2.iloc[4:].copy()
                df2.columns = ['Orden', 'NJ', 'Entidad', 'Prima', 'Part_pct', 'Ramos']
                df2 = df2.dropna(subset=["Entidad", "Prima"])
                df2["Entidad"] = df2["Entidad"].apply(clean_entidad)
                df2["Prima"] = pd.to_numeric(df2["Prima"], errors='coerce').fillna(0)
                
                patrimoniales_entidades = ["SEGUNDA", "SEGUNDA ART"]
                df2_ls = df2[df2["Entidad"].isin(patrimoniales_entidades)]
                
                ramos_pat_agrupados = df2_ls.groupby("Ramos")["Prima"].sum().reset_index()
                ramos_pat_agrupados = ramos_pat_agrupados.sort_values(by="Prima", ascending=False)
                
                la_segunda_data["patrimoniales"]["total"] = float(ramos_pat_agrupados["Prima"].sum())
                
                for _, row_pat in ramos_pat_agrupados.iterrows():
                    ramo = row_pat["Ramos"].strip()
                    prima = float(row_pat["Prima"])
                    if prima > 0:
                        la_segunda_data["patrimoniales"]["ramos"].append({
                            "ramo": ramo,
                            "prima": prima,
                            "part_patrimoniales": round((prima / la_segunda_data["patrimoniales"]["total"]) * 100, 2) if la_segunda_data["patrimoniales"]["total"] > 0 else 0,
                            "part_grupo": round((prima / la_segunda_data["total_grupo"]) * 100, 2) if la_segunda_data["total_grupo"] > 0 else 0
                        })
            
            # 3. Personas
            sheet3 = xls.get("3- Seg. de Personas")
            if sheet3 is not None:
                df3 = sheet3.iloc[4:].copy()
                df3.columns = ['Orden', 'NJ', 'Entidad', 'Prima', 'Part_pct', 'Ramos']
                df3 = df3.dropna(subset=["Entidad", "Prima"])
                df3["Entidad"] = df3["Entidad"].apply(clean_entidad)
                df3["Prima"] = pd.to_numeric(df3["Prima"], errors='coerce').fillna(0)
                
                personas_entidades = ["SEGUNDA PERSONAS", "SEGUNDA RETIRO"]
                df3_ls = df3[df3["Entidad"].isin(personas_entidades)]
                
                ramos_per_agrupados = df3_ls.groupby("Ramos")["Prima"].sum().reset_index()
                ramos_per_agrupados["Ramos"] = ramos_per_agrupados["Ramos"].str.strip()
                
                la_segunda_data["personas"]["total"] = float(ramos_per_agrupados["Prima"].sum())
                
                def get_main_ramo(ramo_name):
                    rn = ramo_name.lower()
                    if "acc" in rn and "personal" in rn:
                        return "Total de Accidentes Personales"
                    elif "salud" in rn:
                        return "Total de Salud"
                    elif "retiro" in rn:
                        return "Total de Retiro"
                    elif "vida" in rn:
                        return "Total de Vida"
                    return "Otros"
                    
                grouped_personas = {}
                for _, row_per in ramos_per_agrupados.iterrows():
                    r = row_per["Ramos"]
                    p = float(row_per["Prima"])
                    if p <= 0: continue
                    
                    main_r = get_main_ramo(r)
                    if main_r not in grouped_personas:
                        grouped_personas[main_r] = {"total": 0, "subs": []}
                    
                    grouped_personas[main_r]["total"] += p
                    grouped_personas[main_r]["subs"].append({
                        "ramo": r,
                        "prima": p,
                        "part_personas": round((p / la_segunda_data["personas"]["total"]) * 100, 2) if la_segunda_data["personas"]["total"] > 0 else 0,
                        "part_grupo": round((p / la_segunda_data["total_grupo"]) * 100, 2) if la_segunda_data["total_grupo"] > 0 else 0
                    })
                    
                fixed_order = ["Total de Accidentes Personales", "Total de Vida", "Total de Salud", "Total de Retiro", "Otros"]
                for mr in fixed_order:
                    if mr in grouped_personas:
                        main_prima = grouped_personas[mr]["total"]
                        la_segunda_data["personas"]["ramos"].append({
                            "ramo": mr,
                            "prima": main_prima,
                            "part_personas": round((main_prima / la_segunda_data["personas"]["total"]) * 100, 2) if la_segunda_data["personas"]["total"] > 0 else 0,
                            "part_grupo": round((main_prima / la_segunda_data["total_grupo"]) * 100, 2) if la_segunda_data["total_grupo"] > 0 else 0,
                            "sub_ramos": grouped_personas[mr]["subs"]
                        })
                        
            results["la_segunda"] = la_segunda_data


        # Helper to process segment rankings (sum by entity across given ramos, get top 10 + La Segunda)
        def process_segment(df, ramo_filter_fn=None):
            if ramo_filter_fn:
                df_filtered = df[df["Ramos"].apply(ramo_filter_fn)]
            else:
                df_filtered = df
                
            if df_filtered.empty:
                return []
                
            total_prima = df_filtered["Prima"].sum()
            if total_prima == 0:
                return []
                
            # Sum by entity
            entity_sums = df_filtered.groupby("Entidad")["Prima"].sum().reset_index()
            entity_sums = entity_sums.sort_values(by="Prima", ascending=False).reset_index(drop=True)
            entity_sums["Part_pct"] = (entity_sums["Prima"] / total_prima * 100).round(2)
            entity_sums["Posicion"] = entity_sums.index + 1
            
            # Get Top 10
            top10 = entity_sums.head(10).copy()
            
            # Check for La Segunda
            la_segunda_ents = entity_sums[
                entity_sums["Entidad"].str.contains("SEGUNDA", na=False) & 
                (entity_sums["Posicion"] > 10)
            ]
            
            final_df = pd.concat([top10, la_segunda_ents])
            
            seg_data = []
            for row in final_df.itertuples():
                seg_data.append({
                    "posicion": int(row.Posicion),
                    "entidad": row.Entidad,
                    "prima": float(row.Prima),
                    "participacion": float(row.Part_pct)
                })
            return seg_data

        # =====================================================================
        # SHEET 2: Seguros Patrimoniales
        # =====================================================================
        sheet2 = xls.get("2- Seguros Patrimoniales")
        if sheet2 is not None:
            df2 = sheet2.iloc[3:].copy()
            df2.columns = ["Orden", "NJ", "Entidad", "Prima", "Part_pct", "Ramos"]
            df2 = df2.dropna(subset=["Entidad", "Prima", "Ramos"])
            df2["Entidad"] = df2["Entidad"].apply(clean_entidad)
            df2["Prima"] = pd.to_numeric(df2["Prima"], errors='coerce').fillna(0)
            df2["Ramos"] = df2["Ramos"].astype(str).str.upper().str.strip()
            
            # 1. Total del Mercado de Patrimoniales (All in sheet 2)
            results["total_patrimoniales"] = process_segment(df2)
            
            # 2. Automotores y Motovehículos
            results["total_automotores"] = process_segment(
                df2, lambda r: "AUTOMOTORES" in r or "MOTOVEH" in r or "MOTO VEH" in r
            )
            
            # 3. ART
            results["total_art"] = process_segment(
                df2, lambda r: "RIESGOS DEL TRABAJO" in r or "ART" in r
            )
            
            # 4. Riesgos Agropecuarios
            results["total_agro"] = process_segment(
                df2, lambda r: "GRANIZO" in r or "GANADO" in r or "AGRO" in r
            )
            
            # 5. Otros Riesgos Patrimoniales
            # Negate the above three conditions
            def otros_patrimoniales(r):
                is_auto = "AUTOMOTORES" in r or "MOTOVEH" in r or "MOTO VEH" in r
                is_art = "RIESGOS DEL TRABAJO" in r or "ART" in r
                is_agro = "GRANIZO" in r or "GANADO" in r or "AGRO" in r
                return not (is_auto or is_art or is_agro)
                
            results["total_otros_patrimoniales"] = process_segment(df2, otros_patrimoniales)


        # =====================================================================
        # SHEET 3: Seg. de Personas
        # =====================================================================
        sheet3 = xls.get("3- Seg. de Personas")
        if sheet3 is not None:
            df3 = sheet3.iloc[3:].copy()
            df3.columns = ["Orden", "NJ", "Entidad", "Prima", "Part_pct", "Ramos"]
            df3 = df3.dropna(subset=["Entidad", "Prima", "Ramos"])
            df3["Entidad"] = df3["Entidad"].apply(clean_entidad)
            df3["Prima"] = pd.to_numeric(df3["Prima"], errors='coerce').fillna(0)
            df3["Ramos"] = df3["Ramos"].astype(str).str.upper().str.strip()
            
            # 1. Total del Mercado de Personas
            results["total_personas"] = process_segment(df3)
            
            # 2. Accidentes Personales
            results["total_accidentes_personales"] = process_segment(
                df3, lambda r: "ACCIDENTES" in r or "ACC." in r
            )
            
            # 3. Vida
            results["total_vida"] = process_segment(
                df3, lambda r: "VIDA" in r
            )
            
            # 4. Sepelio
            results["total_sepelio"] = process_segment(
                df3, lambda r: "SEPELIO" in r
            )
            
            # 5. Salud
            results["total_salud"] = process_segment(
                df3, lambda r: "SALUD" in r
            )
            
            # 6. Retiro
            results["total_retiro"] = process_segment(
                df3, lambda r: "RETIRO" in r
            )


        # =====================================================================
        # NEW FEATURE: Personas y Retiro - Indicadores
        # =====================================================================
        print("[SSN Rankings] Fetching Personas y Retiro (Indicadores)...")
        results["personas_retiro"] = {}
        try:
            mercado_personas = [0.0] * 6
            mercado_retiro = [0.0] * 6
            l2_personas = [0.0] * 6
            l2_retiro = [0.0] * 6
            
            # Fetch indicadores de gestion para Mercado y LA SEGUNDA
            url_ind = "https://www.argentina.gob.ar/sites/default/files/ssn_202603_indicadores_mercado.xlsx"
            r_ind = requests.get(url_ind, verify=False, timeout=30)
            xls_ind = pd.read_excel(io.BytesIO(r_ind.content), sheet_name=None, header=None)
            
            sheet_ges = xls_ind.get("Indicadores de Gestion")
            if sheet_ges is not None:
                for idx, row in sheet_ges.iterrows():
                    name = str(row[2]).strip()
                    
                    # Fetching Mercado Promedio
                    if name == "Seguros de Personas":
                        for i in range(6):
                            try:
                                v = float(row[3 + i])
                                if not pd.isna(v): mercado_personas[i] = v
                            except: pass
                    elif name == "Exclusivas Retiro":
                        for i in range(6):
                            try:
                                v = float(row[3 + i])
                                if not pd.isna(v): mercado_retiro[i] = v
                            except: pass
                            
                    # Fetching LA SEGUNDA
                    name = str(row[2])
                    if "SEGUNDA PERSONAS" in name:
                        for i in range(6):
                            try:
                                v = float(row[3 + i])
                                if not pd.isna(v): l2_personas[i] = v
                            except:
                                pass
                    elif "SEGUNDA RETIRO" in name:
                        for i in range(6):
                            try:
                                v = float(row[3 + i])
                                if not pd.isna(v): l2_retiro[i] = v
                            except:
                                pass
                                
            results["personas_retiro"] = {
                "mercado_personas": mercado_personas,
                "mercado_retiro": mercado_retiro,
                "l2_personas": l2_personas,
                "l2_retiro": l2_retiro
            }
        except Exception as e:
            print(f"[SSN Rankings] Error fetching Personas y Retiro: {e}")
            
        print("[SSN Rankings] Parsed successfully.")
        return results

    except Exception as e:
        print(f"[SSN Rankings] Error parsing SSN Rankings: {e}")
        return None

if __name__ == "__main__":
    res = fetch_ssn_rankings()
    if res:
        for k, v in res.items():
            print(f"--- {k} ---")
            if v:
                print(v)
            else:
                print("No data")
