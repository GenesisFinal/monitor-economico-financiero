from datetime import datetime, timedelta

def safe_float(v):
    try:
        return float(v)
    except:
        return 0.0


def calc_var(val_new, val_old):
    if not val_old or val_old == 0:
        return 0
    return (val_new / val_old - 1) * 100


def deduplicate(lst):
    seen = set()
    dedup = []
    for x in lst:
        ticker = x.get("ticker")
        if ticker not in seen:
            seen.add(ticker)
            dedup.append(x)
    return dedup


def normalize(s):
    import unicodedata

    return (
        unicodedata.normalize("NFKD", s)
        .encode("ASCII", "ignore")
        .decode("utf-8")
        .lower()
    )


def calculate_variations(series):
    """
    Given a pandas Series (sorted by date), calculates 1D, 1M, 12M and YTD changes.
    """
    if series.empty or len(series) == 0:
        return {"change": 0.0, "change_1m": 0.0, "change_12m": 0.0, "change_ytd": 0.0}
        
    last_price = float(series.iloc[-1])
    last_date = series.index[-1]

    # 1D Change
    prev_1d = float(series.iloc[-2]) if len(series) > 1 else last_price
    c_1d = ((last_price - prev_1d) / prev_1d) * 100 if prev_1d else 0.0

    # Helper to get price closest to a target date (must be <= target_date)
    def get_price_near(target_dt):
        past = series[:target_dt]
        if not past.empty:
            return float(past.iloc[-1])
        return float(series.iloc[0])
        
    # 1M (approx 30 days)
    price_1m = get_price_near(last_date - timedelta(days=30))
    c_1m = ((last_price - price_1m) / price_1m) * 100 if price_1m else 0.0

    # 12M (approx 365 days)
    price_12m = get_price_near(last_date - timedelta(days=365))
    c_12m = ((last_price - price_12m) / price_12m) * 100 if price_12m else 0.0

    # YTD (last day of previous year)
    price_ytd = get_price_near(datetime(last_date.year - 1, 12, 31))
    c_ytd = ((last_price - price_ytd) / price_ytd) * 100 if price_ytd else 0.0

    return {
        "change": round(c_1d, 2),
        "change_1m": round(c_1m, 2),
        "change_12m": round(c_12m, 2),
        "change_ytd": round(c_ytd, 2)
    }

