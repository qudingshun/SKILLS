# -*- coding: utf-8 -*-
"""IE 内核宿主（32 位 WebBrowser 控件）—— 惠而浦 EBS 的浏览器入口。

为什么不用 Edge / iexplore：
  * EBS 的 https 只支持 **TLS 1.0 + AES256-SHA**（实测 TLS1.1/1.2 直接被拒），
    Edge 是 Chromium 内核，早就删了 TLS1.0 → ERR_SSL_VERSION_OR_CIPHER_MISMATCH；
    Edge 的「IE 兼容模式」同样走 Chromium 网络栈，一样打不开。
  * Win11 已经停用 iexplore.exe，但 **mshtml/ieframe 引擎还在**，Windows 自带的
    WebBrowser 控件走 Schannel，TLS1.0 默认仍然可用。
  * JRE 只装了 32 位，Java 插件（jp2iexp.dll）也只有 32 位 → 宿主必须是 32 位进程，
    所以用 `SysWOW64\\WindowsPowerShell` 跑 ie_host.ps1。

进程间只靠两个文件通信（简单、好调试）：
  * logs/ie_cmd.txt    —— 我们写 URL，宿主发现变了就跳转
  * logs/ie_status.txt —— 宿主写 `ReadyState\\tUrl\\tTitle`
"""

import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(BASE_DIR, "logs")
HOST_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ie_host.ps1")
CMD_FILE = os.path.join(LOGS, "ie_cmd.txt")
STATUS_FILE = os.path.join(LOGS, "ie_status.txt")
WINDOW_TITLE = "EBS-IE"

PS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                    r"SysWOW64\WindowsPowerShell\v1.0\powershell.exe")

ERP_BASE = "https://erp.whirlpool-china.com:4446"
LOGIN_URL = ERP_BASE + "/OA_HTML/AppsLogin"


def log(msg):
    print(msg, flush=True)


# ── 宿主进程 ───────────────────────────────────────────────────────────
def host_running():
    hwnd = find_window()
    if hwnd:
        return True
    return any("ie_host" in (p.args or "") for p in _ps_procs())


def _ps_procs():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
             "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30).stdout
        import json
        data = json.loads(out or "[]")
        if isinstance(data, dict):
            data = [data]

        class _P:
            def __init__(self, i, args):
                self.pid = i
                self.args = args or ""
        return [_P(d.get("ProcessId"), d.get("CommandLine")) for d in data]
    except Exception:
        return []


def find_window():
    import win32gui
    found = []

    def cb(h, _):
        if win32gui.GetWindowText(h) == WINDOW_TITLE and win32gui.IsWindowVisible(h):
            found.append(h)
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        return None
    return found[0] if found else None


def kill_hosts():
    for p in _ps_procs():
        if "ie_host.ps1" in p.args:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/F"],
                           capture_output=True)
    time.sleep(1)


def open_host(url=LOGIN_URL, timeout=90, fresh=True):
    """启动宿主并等窗口出来；返回 hwnd。"""
    if fresh:
        kill_hosts()
        hwnd = find_window()
        if hwnd:
            kill_hosts()
    else:
        hwnd = find_window()
        if hwnd:
            log(f"  [ie] 复用已有宿主窗口 {hwnd}")
            navigate(url)
            return hwnd

    os.makedirs(LOGS, exist_ok=True)
    with open(CMD_FILE, "w", encoding="utf-8") as f:
        f.write(url)
    try:
        os.remove(STATUS_FILE)
    except OSError:
        pass

    cmd = [PS32, "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", HOST_PS1, "-Url", url, "-Cmd", CMD_FILE, "-Status", STATUS_FILE]
    creation = 0x08000000          # CREATE_NO_WINDOW：别弹黑框挡页面
    errlog = os.path.join(LOGS, "ie_host.err")
    _err = open(errlog, "wb")
    subprocess.Popen(cmd, creationflags=creation, cwd=BASE_DIR,
                     stdout=subprocess.DEVNULL, stderr=_err)
    log(f"  [ie] 启动 IE 内核宿主（32 位 WebBrowser + Schannel，支持 TLS1.0）")

    t0 = time.time()
    while time.time() - t0 < timeout:
        hwnd = find_window()
        if hwnd:
            log(f"  [ie] 宿主窗口就绪 hwnd={hwnd} ({int(time.time() - t0)}s)")
            return hwnd
        time.sleep(1)
    raise RuntimeError(f"IE 内核宿主 {timeout}s 内没出来（{HOST_PS1}）")


def navigate(url):
    os.makedirs(LOGS, exist_ok=True)
    with open(CMD_FILE, "w", encoding="utf-8") as f:
        f.write(url)
    log(f"  [ie] → {url[:110]}")


def status():
    """返回 (ready_state, url, title)；宿主没写出来就返回 (None, '', '')。"""
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            line = f.read()
    except OSError:
        return None, "", ""
    parts = line.split("\t")
    while len(parts) < 3:
        parts.append("")
    ready = parts[0].strip()
    return ready, parts[1].strip(), parts[2].strip()


def wait_page(done, timeout=180, poll=2.0, note=""):
    """等 status() 的 (ready, url, title) 满足 done(...)。"""
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        st = status()
        if st != last:
            log(f"  [ie] {st[0]} | {st[2]} | {st[1][:90]}")
            last = st
        if done(*st):
            return st
        time.sleep(poll)
    raise RuntimeError(f"等页面超时（{note or timeout}）")


def close():
    kill_hosts()
    log("  [ie] 宿主已关闭")


if __name__ == "__main__":
    h = open_host()
    print("hwnd", h)
    for _ in range(30):
        time.sleep(2)
        print(status())
