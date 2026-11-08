# -*- coding: utf-8 -*-
"""临时探针：javaws 起来后逐秒看 jp2launcher/java 进程的 TCP 连接，
判断 applet 是「连服务器失败」还是「根本没发起连接」。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws
import subprocess

LOGS = erp_jws.LOGS


def procs():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match 'java|jp2' } | "
         "ForEach-Object { \"$($_.Id) $($_.ProcessName)\" }"],
        capture_output=True, text=True).stdout
    return [ln.split() for ln in out.splitlines() if ln.strip()]


def conns(pids):
    ps = ("Get-NetTCPConnection -ErrorAction SilentlyContinue | "
          "Where-Object { $_.OwningProcess -in @(" + ",".join(pids) + ") } | "
          "ForEach-Object { \"$($_.State) $($_.LocalPort) -> $($_.RemoteAddress):$($_.RemotePort) pid=$($_.OwningProcess)\" }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


if __name__ == "__main__":
    op, _jar, home = erp_jws.login()
    _page, params, jars = erp_jws.fetch_applet(op)
    jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_conn.jnlp"))
    erp_jws.launch(jp)

    seen = set()
    t0 = time.time()
    while time.time() - t0 < 100:
        time.sleep(1)
        pl = procs()
        pids = [p[0] for p in pl]
        cs = conns(pids) if pids else []
        for c in cs:
            if c not in seen:
                seen.add(c)
                print(f"[{int(time.time()-t0):3d}s] {c}", flush=True)
        if int(time.time() - t0) % 10 == 0:
            erp_jws.accept_security_warning()
        if not pl:
            print(f"[{int(time.time()-t0):3d}s] 没有 java 进程了", flush=True)
            break
    print("=== 结束 ===", flush=True)
