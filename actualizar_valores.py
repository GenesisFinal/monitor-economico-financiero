import os, sys, json, re, requests, datetime

# Ensure sub-modules import cleanly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def build_tr_html(item, cat_name):
    ticker = item.get("ticker", "")
    name = item.get("name", ticker)
    price = item.get("price", 0.0)
    c1d = item.get("change", 0.0)
    c7d = item.get("change_7d", 0.0)
    c1m = item.get("change_1m", 0.0)
    c12m = item.get("change_12m", 0.0)

    if cat_name == "forex" and price < 10:
        price_str = f"${price:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        price_str = f"${price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def var_td(val, hidden=""):
        if val is None: return f'<td class="py-2.5 px-4 text-right font-mono {hidden}">-</td>'
        clr = "!text-emerald-500 light:!text-emerald-600 font-bold" if val > 0 else ("!text-rose-500 light:!text-rose-600 font-bold" if val < 0 else "text-slate-400")
        txt = f"+{val:.2f}%" if val > 0 else f"{val:.2f}%"
        return f'<td class="py-2.5 px-4 text-right font-mono {hidden} {clr}">{txt}</td>'

    link = f"https://finance.yahoo.com/quote/{ticker}"
    return f"""<tr data-ticker="{ticker}" onclick="rowClick(event, '{cat_name}', '{ticker}')" class="hover:bg-brandBlue/5 transition-colors cursor-pointer border-b border-darkBorder/20 light:border-gray-200">
    <td class="py-2.5 px-2 text-center"><input type="checkbox" onchange="toggleSelect(event, '{cat_name}', '{ticker}')" class="rounded text-brandBlue focus:ring-brandBlue cursor-pointer"></td>
    <td class="py-2.5 px-4 font-semibold text-white light:text-slate-900 font-mono whitespace-nowrap"><a href="{link}" target="_blank" rel="noopener noreferrer" class="hover:underline text-brandBlue flex items-center gap-1">{ticker}</a></td>
    <td class="py-2.5 px-4 text-slate-300 light:text-slate-700 whitespace-nowrap text-xs">{name}</td>
    <td class="py-2.5 px-4 text-right font-mono text-slate-400 light:text-slate-500">-.-</td>
    <td class="py-2.5 px-4 text-right font-mono text-white light:text-slate-900 font-semibold whitespace-nowrap">{price_str}</td>
    {var_td(c1d)}
    {var_td(c7d)}
    {var_td(c1m, "hidden md:table-cell")}
    {var_td(c12m, "hidden lg:table-cell")}
</tr>"""

def build_dashboard():
    print("==========================================================================")
    print("EXECUTING CLEAN DASHBOARD BUILDER...")
    print("==========================================================================")

    # 1. Populate 100% economic indicator historical keys into master_dataset
    try:
        from populate_all_econ_sparklines_data import populate_all_econ_keys
        populate_all_econ_keys()
    except Exception as e:
        print("[ECON WARN]", e)

    # 2. Read template from src/templates/index.html
    template_path = "src/templates/index.html"
    if not os.path.exists(template_path):
        template_path = "index.html"

    with open(template_path, "r", encoding="utf-8") as f:
        rendered_html = f.read()

    # 3. Read master_dataset.json
    with open("master_dataset.json", "r", encoding="utf-8") as f:
        master_data = json.load(f)

    # Embed master_store_data
    store_json = json.dumps(master_data.get("final_data", master_data), ensure_ascii=False)
    rendered_html = re.sub(
        r'const master_store_data\s*=\s*\{.*?\};',
        f'const master_store_data = {store_json};',
        rendered_html,
        flags=re.DOTALL
    )

    # 4. ALWAYS ENFORCE PERMANENT REMOVAL OF VALORES FINANCIEROS IN RENDERING
    rendered_html = re.sub(r'<button[^>]*id="btn-global-valores"[^>]*>.*?</button>', '', rendered_html, flags=re.DOTALL)
    
    pos_v = rendered_html.find('id="sec-global-valores"')
    if pos_v != -1:
        st_v = rendered_html.rfind('<section', 0, pos_v)
        if st_v == -1: st_v = rendered_html.rfind('<div', 0, pos_v)
        nx_pos = min([p for p in [rendered_html.find('id="sec-global-asegurador"', pos_v), rendered_html.find('id="sec-global-indicadores"', pos_v), rendered_html.find('id="sec-global-fuentes"', pos_v)] if p != -1])
        nx_st = rendered_html.rfind('<section', 0, nx_pos)
        if nx_st == -1: nx_st = rendered_html.rfind('<div', 0, nx_pos)
        rendered_html = rendered_html[:st_v] + rendered_html[nx_st:]

    # Remove container-valores if present
    pos_cv = rendered_html.find('id="container-valores"')
    if pos_cv != -1:
        st_cv = rendered_html.rfind('<div', 0, pos_cv)
        nx_cv = min([p for p in [rendered_html.find('id="container-asegurador"', pos_cv), rendered_html.find('id="container-indicadores-economicos"', pos_cv), rendered_html.find('id="container-fuentes"', pos_cv)] if p != -1])
        nx_st_cv = rendered_html.rfind('<div', 0, nx_cv)
        if st_cv != -1 and nx_st_cv != -1:
            rendered_html = rendered_html[:st_cv] + rendered_html[nx_st_cv:]

    rendered_html = rendered_html.replace("let currentGlobalSection = 'valores';", "let currentGlobalSection = 'asegurador';")
    rendered_html = rendered_html.replace("let activeGlobalSection = 'valores';", "let activeGlobalSection = 'asegurador';")
    rendered_html = rendered_html.replace("const currentGlobalTab = 'valores';", "const currentGlobalTab = 'asegurador';")

    # Add Info Buttons to bond rows
    for sec in ["bonds_usd", "bonds_cer", "bonds_pesos", "lecaps", "corporate"]:
        pos_tbl = rendered_html.find(f'id="tbl-{sec}"')
        if pos_tbl != -1:
            pos_end_tbl = rendered_html.find('</tbody>', pos_tbl)
            tbl_content = rendered_html[pos_tbl:pos_end_tbl]

            def repl_ticker(match):
                t = match.group(1)
                return f'<td class="py-2.5 px-4 font-semibold text-white light:text-slate-900 font-mono whitespace-nowrap flex items-center justify-between gap-2"><span>{t}</span><button onclick="event.stopPropagation(); showBondDetailsModal(\'{t}\')" class="text-brandBlue hover:text-white transition-colors p-1" title="Ver Ficha Técnica del Bono"><i class="fas fa-info-circle text-xs"></i></button></td>'

            new_tbl = re.sub(
                r'<td class="py-2.5 px-4 font-semibold text-white light:text-slate-900 font-mono whitespace-nowrap">\s*([A-Z0-9.\-]+)\s*</td>',
                repl_ticker,
                tbl_content
            )
            rendered_html = rendered_html[:pos_tbl] + new_tbl + rendered_html[pos_end_tbl:]

    # Write output to index.html
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(rendered_html)

    print(f"SUCCESS! Rendered updated index.html ({len(rendered_html):,} bytes) cleanly!")

if __name__ == "__main__":
    build_dashboard()
