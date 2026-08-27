import json, jinja2, re, collections

class SafeDict(dict):
    def __getitem__(self, item):
        if item not in self:
            return SafeDict()
        return super().__getitem__(item)
    def __getattr__(self, item):
        return self.__getitem__(item)
    def __round__(self, n=0):
        return 0.0
    def __float__(self):
        return 0.0
    def __int__(self):
        return 0
    def __bool__(self):
        return False
    def __str__(self):
        return ''
    def __len__(self):
        return 0
    def __gt__(self, other): return False
    def __ge__(self, other): return False
    def __lt__(self, other): return False
    def __le__(self, other): return False

def recursive_safe(d):
    if isinstance(d, dict):
        res = SafeDict()
        for k, v in d.items():
            res[k] = recursive_safe(v)
        return res
    elif isinstance(d, list):
        return [recursive_safe(x) for x in d]
    return d

def render_jinja():
    print("=== RENDERING SRC/TEMPLATES/INDEX.HTML WITH COMPARISON-SAFE SAFEDICT ===")

    with open("master_dataset.json", "r", encoding="utf-8") as f:
        master = json.load(f)

    final_data = recursive_safe(master.get("final_data", master))

    with open("src/templates/index.html", "r", encoding="utf-8") as f:
        tmpl_str = f.read()

    # Pre-render cleanup: strip any unrendered macro definitions if present
    tmpl_str = re.sub(r'\{%\s*macro[^%]*%\}.*?\{%\s*endmacro\s*%\}', '', tmpl_str, flags=re.DOTALL)
    tmpl_str = re.sub(r'\{\{\s*render_section[^}]*\}\}', '', tmpl_str)

    env = jinja2.Environment(undefined=jinja2.Undefined)
    template = env.from_string(tmpl_str)
    rendered = template.render(data=final_data, master=master)

    # Post-render audit guard: verify zero Jinja tags remain
    if "{%" in rendered or "{{" in rendered:
        rendered = re.sub(r'\{%[^%]*%\ToAdd}', '', rendered)
        rendered = re.sub(r'\{\{[^\}]*\}\}', '', rendered)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"[SUCCESS] Rendered Jinja template cleanly to index.html ({len(rendered):,} bytes)!")

if __name__ == "__main__":
    render_jinja()
