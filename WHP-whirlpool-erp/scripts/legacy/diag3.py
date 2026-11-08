#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag3 - 枚举当前桌面所有窗口（class + 标题 + 尺寸），排查 Forms / 提示框"""
import win32gui


def _cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    cls = win32gui.GetClassName(hwnd)
    title = win32gui.GetWindowText(hwnd)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    print(f"hwnd={hwnd:<10} class={cls:<28} size={r-l}x{b-t:<6} "
          f"pos=({l},{t}) title={title!r}")


if __name__ == "__main__":
    win32gui.EnumWindows(_cb, None)
