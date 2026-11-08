# -*- coding: utf-8 -*-
import os
import re

CACHE = os.path.expanduser(r"~\AppData\LocalLow\Sun\Java\Deployment\cache\6.0")
pat = re.compile(rb"https?://[^\x00-\x20\"'<>]{10,400}(?:frmservlet|\.jnlp)[^\x00-\x20\"'<>]{0,200}")
for root, _dirs, files in os.walk(CACHE):
    for f in files:
        p = os.path.join(root, f)
        try:
            if os.path.getsize(p) > 3_000_000:
                continue
            data = open(p, "rb").read()
        except Exception:
            continue
        for m in pat.finditer(data):
            s = m.group(0).decode("utf-8", "replace")
            print(f"{f}: {s[:300]}")
