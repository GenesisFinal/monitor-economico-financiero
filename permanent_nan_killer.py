import re, json

def sanitize_file(filepath):
    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read()

        # Remove null bytes and multiple carriage returns
        cleaned_bytes = raw_bytes.replace(b'\x00', b'').replace(b'\r\r', b'\r').replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        raw_js = cleaned_bytes.decode('utf-8', errors='ignore')

        # Replace NaN with null
        clean_js = re.sub(r':\s*NaN\b', ': null', raw_js)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(clean_js)

        print(f"[NAN KILLER] Sanitized {filepath} cleanly!")
    except Exception as e:
        print(f"[NAN KILLER WARN] Could not sanitize {filepath}:", e)

def main():
    print("==========================================================================")
    print("PERMANENTLY KILLING ALL NAN OCCURRENCES & BAD BYTES IN FILES...")
    print("==========================================================================")
    sanitize_file("master_dataset.json")
    sanitize_file("historical_series.json")
    sanitize_file("index.html")
    print("==========================================================================")

if __name__ == "__main__":
    main()
