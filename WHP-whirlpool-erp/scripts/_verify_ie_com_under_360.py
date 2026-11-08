#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时验证脚本：360 运行时，哪种方式能拿到真正的 IE11 COM 对象。
运行前请先开启 360（让它跑起来），再执行本脚本。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import pythoncom
import win32com.client
import win32gui

CLSID = "{0002DF01-0000-0000-C000-000000000046}"
IID_IDISPATCH = "{00020400-0000-0000-C000-000000000046}"


def _is_360_running():
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info["name"] or "").lower()
            except Exception:
                continue
            if n in ("360se.exe", "360chromeie.exe"):
                return True
    except Exception:
        pass
    return False


def show(name, fn):
    o = None
    try:
        o = fn()
        try:
            hwnd = int(o.HWND)
            nm = o.Name
        except Exception as e:
            hwnd = None
            nm = f"<无HWND/Name: {type(e).__name__}>"
        print(f"[{name}] OK  hwnd={hwnd}  Name={nm!r}")
    except Exception as e:
        code = ""
        try:
            code = f"0x{(e.args[0] & 0xFFFFFFFF):08X}"
        except Exception:
            pass
        print(f"[{name}] FAIL {type(e).__name__} {code} {str(e)[:90]}")
    finally:
        if o is not None:
            try:
                o.Quit()
            except Exception:
                pass


if __name__ == "__main__":
    print("360 正在运行:" , _is_360_running())
    print("=" * 60)
    show("1.Dispatch(ProgID)      ", lambda: win32com.client.Dispatch("InternetExplorer.Application"))
    show("2.DispatchEx(ProgID)    ", lambda: win32com.client.DispatchEx("InternetExplorer.Application"))
    def co():
        obj = pythoncom.CoCreateInstance(
            pythoncom.MakeIID(CLSID), None,
            pythoncom.CLSCTX_LOCAL_SERVER, pythoncom.MakeIID(IID_IDISPATCH))
        return win32com.client.Dispatch(obj)
    show("3.CoCreateInstance(CLSID)", co)
    print("=" * 60)
    # 另外看看 Shell.Windows 里有没有 360 的 IE 内核对象
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        ws = shell.Windows()
        print(f"Shell.Windows 数量: {ws.Count}")
        for i in range(ws.Count):
            try:
                w = ws.Item(i)
                print(f"  [{i}] FullName={w.FullName[-40:]} url={str(w.LocationURL)[:60]}")
            except Exception as e:
                print(f"  [{i}] err {str(e)[:50]}")
    except Exception as e:
        print("Shell.Windows 枚举失败:", str(e)[:100])
