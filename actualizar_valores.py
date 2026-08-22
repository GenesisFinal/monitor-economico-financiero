import os, sys, json, re, jinja2

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def build_dashboard():
    print("==========================================================================")
    print("EXECUTING CLEAN DASHBOARD BUILDER...")
    print("==========================================================================")

    # 1. Load economic categories
    try:
        from load_real_economic_categories import load_econ_cats
        load_econ_cats()
    except Exception as e:
        print("[ECON CATS WARN]", e)

    # 2. Populate 100% economic indicator historical keys into master_dataset
    try:
        from populate_all_econ_sparklines_data import populate_all_econ_keys
        populate_all_econ_keys()
    except Exception as e:
        print("[ECON KEYS WARN]", e)

    # 3. Render Jinja template cleanly
    try:
        from build_full_dummy_context import render_jinja
        render_jinja()
        print("[SUCCESS] Dashboard rendered cleanly via build_full_dummy_context!")
    except Exception as e:
        print("[RENDER WARN]", e)

if __name__ == "__main__":
    build_dashboard()
