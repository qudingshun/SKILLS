# -*- coding: utf-8 -*-
import os

CACHE = os.path.expanduser(r"~\AppData\LocalLow\Sun\Java\Deployment\cache\6.0")
KEYS = (b"frmservlet", b"RF.jsp", b"config=", b"<jnlp", b"codebase")
for root, _d, files in os.walk(CACHE):
    for f in files:
        p = os.path.join(root, f)
        try:
            data = open(p, "rb").read()
        except Exception:
            continue
        hits = {k.decode(): data.count(k) for k in KEYS if k in data}
        if hits:
            print(f, os.path.getsize(p), hits)
            i = min(data.find(k) for k in KEYS if k in data)
            print("   ctx:", data[max(0, i - 120): i + 260])
