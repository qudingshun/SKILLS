# -*- coding: utf-8 -*-
import re

h = open(r"E:\SKILLS\WHP-whirlpool-erp\logs\oaf_after.html", encoding="utf-8").read()
for m in re.finditer(r"<iframe[^>]*>", h, re.I):
    print("IFRAME", m.group(0)[:220])
for m in re.finditer(r'src="([^"]+)"', h, re.I):
    s = m.group(1)
    if "js" in s.lower() or "jsp" in s.lower():
        print("SRC", s[:150])
print("--- function_id ctx ---")
i = h.find("function_id")
print(h[max(0, i - 400): i + 300])
