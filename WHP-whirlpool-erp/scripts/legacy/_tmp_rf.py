# -*- coding: utf-8 -*-
import re

p = r"E:\SKILLS\WHP-whirlpool-erp\logs\rf_page_196.html"
h = open(p, encoding="utf-8").read()
i = h.lower().find("<applet")
print("applet idx", i, "len", len(h))
if i >= 0:
    print(h[i:i + 3000])
print("==== frmservlet/jnlp mentions ====")
for m in re.finditer(r"(frmservlet|jnlp|serverURL|serverArgs|form_params)", h, re.I):
    s = h[max(0, m.start() - 120): m.start() + 160].replace("\n", " ")
    print("...", s[:280])
