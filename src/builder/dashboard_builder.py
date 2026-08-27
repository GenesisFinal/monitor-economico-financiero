import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def main():
    print("==========================================================================")
    print("EXECUTING CLEAN DASHBOARD BUILDER PIPELINE...")
    print("==========================================================================")
    
    try:
        from actualizar_valores import build_dashboard
        build_dashboard()
    except Exception as e:
        print("Error running build_dashboard:", e)

    try:
        from permanent_nan_killer import kill_nan_in_all_files
        kill_nan_in_all_files()
    except Exception as e:
        print("Error running permanent_nan_killer:", e)

if __name__ == "__main__":
    main()
