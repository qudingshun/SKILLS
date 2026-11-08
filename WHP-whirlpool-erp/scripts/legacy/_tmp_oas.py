# -*- coding: utf-8 -*-
import re

h = open(r"E:\SKILLS\WHP-whirlpool-erp\logs\oaf_after.html", encoding="utf-8").read()
oas = re.findall(r"oas=([A-Za-z0-9_.\-]+)", h)
print("oas tokens:", set(oas))
print("count", len(oas))
for m in re.finditer(r"McreateTree\([^)]*\)", h):
    print("TREE:", m.group(0)[:200])
print("--- any oas ctx ---")
i = h.find("oas=")
print(h[max(0, i - 200): i + 120])
