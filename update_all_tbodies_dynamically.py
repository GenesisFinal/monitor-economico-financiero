import os, re, shutil, json

def format_price(val):
    if val is None or val == "":
        return "-.-"
    try:
        f = float(val)
        if f >= 1000:
            return f"${f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            return f"${f:.2f}".replace(".", ",")
    except Exception:
        return str(val)

def format_pct(val):
    if val is None or val == "":
        return "-.-"
    try:
        f = float(val)
        prefix = "+" if f > 0 else ""
        return f"{prefix}{f:.2f}%"
    except Exception:
        return str(val)

def update_all_tbodies_in_generator():
    print("==========================================================================")
    print("REPLACING ALL STATIC TABLE BODIES WITH DYNAMIC LIVE DATA FROM MASTER_DATASET")
    print("==========================================================================")
    
    with open('actualizar_valores.py', 'r', encoding='utf-8') as f:
        code = f.read()

    with open('master_dataset.json', 'r', encoding='utf-8') as f:
        ds = json.load(f)

    final_data = ds.get('final_data', {})

    # Helper to generate rows for standard category items
    def build_rows_for_category(items, cat_name):
        rows = []
        for item in items:
            if not isinstance(item, dict): continue
            if item.get("is_divider"):
                rows.append(f'<tr class="bg-darkBg/80 light:bg-slate-200/60 font-bold text-xs text-brandBlue uppercase border-y border-darkBorder/40"><td colspan="9" class="py-2 px-4">{item.get("title")}</td></tr>')
                continue

            ticker = item.get("ticker", "")
            name = item.get("name", ticker)
            price = item.get("price")
            change = item.get("change")
            chg_1m = item.get("change_1m")
            chg_ytd = item.get("change_ytd")
            chg_12m = item.get("change_12m")

            price_str = format_price(price)
            change_str = format_pct(change)
            chg_1m_str = format_pct(chg_1m)
            chg_ytd_str = format_pct(chg_ytd)
            chg_12m_str = format_pct(chg_12m)

            chg_num = float(change) if change is not None and str(change).replace('.','',1).replace('-','',1).isdigit() else 0
            chg_color = "text-emerald-500" if chg_num > 0 else ("text-brandRed" if chg_num < 0 else "text-slate-400")

            row = f'''<tr data-ticker="{ticker}" onclick="rowClick(event, '{cat_name}', '{ticker}')" class="hover:bg-brandBlue/5 transition-colors cursor-pointer border-b border-darkBorder/20 light:border-gray-200">
                <td class="py-2.5 px-4 text-center"><input type="checkbox" checked onchange="toggleSelect(event, '{cat_name}', '{ticker}')" class="rounded text-brandBlue focus:ring-brandBlue cursor-pointer"></td>
                <td class="py-2.5 px-4 font-semibold text-white light:text-slate-900 font-mono"><span class="font-bold">{ticker}</span></td>
                <td class="py-2.5 px-4 text-slate-300 light:text-slate-700">{name}</td>
                <td class="py-2.5 px-4 text-right font-mono font-semibold live-price-cell text-slate-400 light:text-slate-500 opacity-70" data-ticker="{ticker}" data-close-price="{price or ''}">-.-</td>
                <td class="py-2.5 px-4 text-right font-mono font-semibold text-white light:text-slate-900">{price_str}</td>
                <td class="py-2.5 px-4 text-right font-bold {chg_color}">{change_str}</td>
                <td class="py-2.5 px-4 text-right text-slate-400 hidden md:table-cell">{chg_1m_str}</td>
                <td class="py-2.5 px-4 text-right text-slate-400 hidden md:table-cell">{chg_ytd_str}</td>
                <td class="py-2.5 px-4 text-right text-slate-400 hidden md:table-cell">{chg_12m_str}</td>
            </tr>'''
            rows.append(row)
        return "\n".join(rows)

    # Replace tbody content for standard categories
    cat_mappings = {
        'tbl-indices': ('indices', final_data.get('indices', [])),
        'tbl-forex': ('forex', final_data.get('forex', [])),
        'tbl-commodities': ('commodities', final_data.get('commodities', [])),
        'tbl-etfs': ('etfs', final_data.get('etfs', [])),
        'tbl-acciones_arg': ('acciones_arg', final_data.get('acciones_arg', [])),
        'tbl-cryptos': ('cryptos', final_data.get('cryptos', [])),
        'tbl-cedears': ('cedears', final_data.get('cedears', [])),
        'tbl-stocks': ('stocks', final_data.get('stocks', []))
    }

    for tbody_id, (cat_name, items) in cat_mappings.items():
        if not items: continue
        new_rows = build_rows_for_category(items, cat_name)
        pattern = r'(<tbody\s+id="' + tbody_id + r'"[^>]*>)(.*?)(<\/tbody>)'
        match = re.search(pattern, code, re.DOTALL)
        if match:
            code = code[:match.start(2)] + "\n" + new_rows + "\n" + code[match.end(2):]
            print(f"Updated tbody #{tbody_id} ({len(items)} items)")

    # Replace tbody content for Bonds categories
    bonds = final_data.get('bonds', {})
    bond_mappings = {
        'tbl-bonds-usd': ('usd', bonds.get('usd', [])),
        'tbl-bonds-cer': ('cer', bonds.get('cer', [])),
        'tbl-bonds-pesos': ('pesos', bonds.get('pesos', [])),
        'tbl-bonds-ons_hard': ('ons_hard', bonds.get('ons_hard', [])),
        'tbl-bonds-ons_cer_dl': ('ons_cer_dl', bonds.get('ons_cer_dl', []))
    }

    for tbody_id, (b_type, b_items) in bond_mappings.items():
        if not b_items: continue
        rows = []
        for b in b_items:
            ticker = b.get("ticker", "")
            name = b.get("name", ticker)
            price = b.get("price")
            change = b.get("change")
            tir = b.get("tir", "-.-")
            duration = b.get("duration", "-.-")
            chg_ytd = b.get("change_ytd")

            price_str = format_price(price)
            change_str = format_pct(change)
            chg_ytd_str = format_pct(chg_ytd)

            chg_num = float(change) if change is not None and str(change).replace('.','',1).replace('-','',1).isdigit() else 0
            chg_color = "text-emerald-500" if chg_num > 0 else ("text-brandRed" if chg_num < 0 else "text-slate-400")

            row = f'''<tr data-ticker="{ticker}" onclick="rowClick(event, 'bonds', '{ticker}')" class="hover:bg-brandBlue/5 transition-colors cursor-pointer border-b border-darkBorder/20 light:border-gray-200">
                <td class="py-2.5 px-3 text-center"><input type="checkbox" checked onchange="toggleSelect(event, 'bonds', '{ticker}')" class="rounded text-brandBlue focus:ring-brandBlue cursor-pointer"></td>
                <td class="py-2.5 px-3 font-semibold text-white light:text-slate-900 font-mono"><span class="font-bold">{ticker}</span></td>
                <td class="py-2.5 px-3 text-slate-300 light:text-slate-700">{name}</td>
                <td class="py-2.5 px-3 text-right font-mono font-semibold live-price-cell text-slate-400 light:text-slate-500 opacity-70" data-ticker="{ticker}" data-close-price="{price or ''}">-.-</td>
                <td class="py-2.5 px-3 text-right font-mono font-semibold text-white light:text-slate-900">{price_str}</td>
                <td class="py-2.5 px-3 text-right font-bold {chg_color}">{change_str}</td>
                <td class="py-2.5 px-3 text-right text-slate-400">{chg_ytd_str}</td>
                <td class="py-2.5 px-3 text-right text-slate-400">{tir}</td>
                <td class="py-2.5 px-3 text-right text-slate-400">{duration}</td>
            </tr>'''
            rows.append(row)
        
        new_rows = "\n".join(rows)
        pattern = r'(<tbody\s+id="' + tbody_id + r'"[^>]*>)(.*?)(<\/tbody>)'
        match = re.search(pattern, code, re.DOTALL)
        if match:
            code = code[:match.start(2)] + "\n" + new_rows + "\n" + code[match.end(2):]
            print(f"Updated tbody #{tbody_id} ({len(b_items)} bonds)")

    with open('actualizar_valores.py', 'w', encoding='utf-8') as f:
        f.write(code)

    print("==========================================================================")
    print("SUCCESSFULLY REPLACED ALL STATIC TABLE BODIES WITH LIVE MARKET DATA!")
    print("==========================================================================")

if __name__ == '__main__':
    update_all_tbodies_in_generator()
