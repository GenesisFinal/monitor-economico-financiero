def get_t2_inflation(y, m, inflation_data):
    if m == 1:
        t2_y, t2_m = y - 1, 11
    elif m == 2:
        t2_y, t2_m = y - 1, 12
    else:
        t2_y, t2_m = y, m - 2

    rate = inflation_data.get((t2_y, t2_m))
    if rate is None:
        fallbacks = {(2025, 4): 0.025, (2025, 5): 0.02, (2025, 6): 0.02}
        rate = fallbacks.get((t2_y, t2_m), 0.02)
    return rate
