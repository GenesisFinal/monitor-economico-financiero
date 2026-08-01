def format_bond_value(val, is_pct=False):
    """Safely format numeric values for JSON/HTML display."""
    if val is None or val == "-":
        return "-"
    try:
        val_f = float(val)
        if is_pct:
            return f"{val_f * 100:.2f}%"
        return f"{val_f:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def format_billones_pesos(val):
    """Formats values (which are in millions of pesos from source) to billones, mil millones, or millones."""
    if val is None or val == "-":
        return "-"
    try:
        val_f = float(val)
        val_abs = abs(val_f)
        sign = "-" if val_f < 0 else ""
        if val_abs >= 1000000.0:
            return f"{sign}${val_abs/1000000.0:,.2f} billones"
        elif val_abs >= 1000.0:
            return f"{sign}${val_abs/1000.0:,.2f} mil millones"
        else:
            return f"{sign}${val_abs:,.2f} millones"
    except (ValueError, TypeError):
        return str(val)


def format_month_year(date_str):
    if not date_str or not isinstance(date_str, str):
        return date_str
    
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return f"{months[dt.month-1]} {dt.year}"
        except Exception:
            pass
            
    return date_str


def format_quarter_year(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        q = (dt.month - 1) // 3 + 1
        return f"{q}T {dt.year}"
    except Exception:
        return date_str


def format_semester_year(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # In the API, Year-07-01 represents 1S Year, and (Year+1)-01-01 represents 2S Year
        if dt.month == 1:
            return f"2S {dt.year - 1}"
        else:
            return f"1S {dt.year}"
    except Exception:
        return date_str


def format_price_ars(val):
    if val is None:
        return "-"
    return f"${val:,.2f}"


def format_price_usd(val):
    if val is None:
        return "-"
    return f"USD {val:,.2f} M"


def format_percent(val):
    if val is None:
        return "-"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"


def format_points(val):
    if val is None:
        return "-"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f} pp"


def format_qty(val, unit=""):
    if val is None:
        return "-"
    return f"{val:,.0f} {unit}".strip()


def filter_format_price(val):
    if val is None or val == "-":
        return "-"
    try:
        val_f = float(val)
        return "{:,.2f}".format(val_f)
    except (ValueError, TypeError):
        return str(val)


def filter_format_pct(val):
    if val is None or val == "-":
        return "-"
    try:
        val_f = float(val)
        return "{:.2f}".format(val_f)
    except (ValueError, TypeError):
        return str(val)


def filter_format_billions_1d(val):
    if val is None or val == "-":
        return "-"
    try:
        v = float(val) / 1e9
        s = f"{v:,.1f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} mil M"
    except:
        return str(val)


def filter_format_billions(val):
    if val is None or val == "-":
        return "-"
    try:
        v = float(val)
        billions = int(v / 1e9)
        return f"{billions:,} mil M".replace(",", ".")
    except:
        return str(val)
