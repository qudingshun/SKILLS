#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_forms - 登录后启动并操作 Oracle Forms（Java 应用）

背景
====
惠而浦 EBS 里很多“职责 / 功能”并不是网页，而是 **Oracle Forms**——一个
独立的 Java 程序（不是浏览器里的小程序）。点击这类职责时，EBS 会：

  (a) 触发一次 JNLP 文件下载（Web Start），或
  (b) 跳转到 /forms/frmservlet?... 并返回一个 JNLP。

本机已安装 Java Web Start（javaws.exe），因此可以：
  1. 用 Playwright 在已登录的 EBS 页面里点击目标职责，拦截 JNLP 下载；
  2. 用 javaws 启动 Forms（独立 Java 窗口，标题多为 “Oracle Applications” /
     “Oracle E-Business Suite” 或具体表单名）；
  3. 用 pywinauto 驱动该 Java 窗口（键入、点击按钮、选菜单、读字段）。

⚠️ 2026-10-20 实测更正：该 EBS 的 Forms 是 **Java Applet（JInitiator 架构）**，
   服务端不返回 JNLP，javaws 路线走不通。实测可行路径是
   **IE11 + Java 8 插件** 直接运行 FormsLauncher applet，弹出独立 Java 窗口
   （class=SunAwtFrame）。本模块的 launch_jnlp() 仅作历史保留，
   实际驱动请用 FormsApp.connect_by_hwnd()（见 erp_navigator.py）。

关于 360 浏览器
==============
**本技能不主动使用 360**（用户明确要求）。登录走 IE11（COM 自动化），
360 回退已默认禁用（须显式 WP_ENABLE_360=1）。
若系统自行把 launchForm 的新窗口交给 360（其双核兼容模式能跑 applet），
按约定**不干预其进程**，照常等待 Forms 拉起即可。
"""
import os
import subprocess
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Forms 是 32 位 Java 应用，pywinauto 的位数提示噪音较大，静音（功能不受影响）
warnings.filterwarnings("ignore", message="32-bit application should be automated*")

from erp_common import safe_print

JAVAWS_CANDIDATES = [
    r"C:\Program Files (x86)\Common Files\Oracle\Java\javapath\javaws.exe",
    r"C:\Program Files\Java\jre\bin\javaws.exe",
    r"C:\Program Files\Java\jdk\bin\javaws.exe",
]


def find_javaws():
    for c in JAVAWS_CANDIDATES:
        if os.path.exists(c):
            return c
    # 尝试 PATH
    import shutil
    p = shutil.which("javaws")
    return p


def launch_jnlp(jnlp_path: str, javaws: str = None, timeout: int = 60) -> bool:
    """用 javaws 启动 Forms；返回是否成功拉起进程"""
    javaws = javaws or find_javaws()
    if not javaws:
        safe_print("[FAIL] 未找到 javaws.exe，无法启动 Oracle Forms")
        return False
    if not os.path.exists(jnlp_path):
        safe_print(f"[FAIL] JNLP 文件不存在: {jnlp_path}")
        return False
    safe_print(f"[Forms] 启动: {javaws} -open {jnlp_path}")
    try:
        subprocess.Popen([javaws, "-open", jnlp_path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        safe_print(f"[FAIL] 启动 Forms 失败: {e}")
        return False


# ── pywinauto 驱动 Oracle Forms 窗口 ────────────────────────────────────
class FormsApp:
    """
    Oracle Forms Java 窗口的 pywinauto 封装。

    用法：
        app = FormsApp()
        app.connect(title_re=".*Oracle.*")     # 连接已拉起的 Forms 窗口
        app.type_text("查询条件")               # 在焦点控件键入
        app.click_button("确定")                # 按中文标签点按钮
        app.select_menu("文件->新建")            # 选菜单
        val = app.get_edit_text(0)              # 读第 0 个编辑框
    """

    def __init__(self, backend: str = "uia"):
        from pywinauto import Application
        self.Application = Application
        self.app = None
        self.window = None
        self.backend = backend

    def connect(self, title=None, title_re=None, timeout: int = 60):
        """连接到 Forms 窗口；title_re 用正则匹配窗口标题"""
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                self.app = self.Application(backend=self.backend).connect(
                    title=title, title_re=title_re, timeout=3
                )
                wins = self.app.windows()
                if wins:
                    self.window = wins[0]
                    safe_print(f"[Forms] 已连接窗口: {self.window.window_text()}")
                    return True
            except Exception as e:
                last_err = e
                time.sleep(2)
        safe_print(f"[FAIL] 未能连接到 Forms 窗口: {last_err}")
        return False

    def connect_by_hwnd(self, hwnd: int, timeout: int = 30) -> bool:
        """
        按 hwnd 连接 Forms Java 窗口（erp_navigator 拉起后调用）。

        注意：Java AWT(SunAwtFrame) 对 UIA backend 只暴露 TitleBar，
        所以这里固定用 win32 backend —— 足够做 set_focus / type_keys /
        菜单/截图；内部自绘控件无法枚举，驱动靠键盘与坐标。
        """
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                self.app = self.Application(backend="win32").connect(
                    handle=hwnd, timeout=3)
                self.window = self.app.window(handle=hwnd)
                safe_print(f"[Forms] 已连接窗口: {self.window.window_text()}")
                return True
            except Exception as e:
                last_err = e
                time.sleep(2)
        safe_print(f"[FAIL] 未能按 hwnd 连接 Forms 窗口: {last_err}")
        return False

    def type_text(self, text: str, into=None):
        """在焦点控件（或指定控件）键入文本"""
        if into is not None:
            ctrl = self.window.child_window(**into)
            ctrl.set_focus()
            ctrl.type_keys(text, with_spaces=True)
        else:
            self.window.type_keys(text, with_spaces=True)
        safe_print(f"[Forms] 键入: {text}")

    def click_button(self, label: str):
        """按可见文字点击按钮（支持中文标签）"""
        btn = self.window.child_window(title=label, control_type="Button")
        btn.click()
        safe_print(f"[Forms] 点击按钮: {label}")

    def select_menu(self, path: str):
        """选菜单，path 形如 '文件->新建' 或 'View->Query'"""
        parts = [p.strip() for p in path.split("->")]
        item = self.window.menu_select(path if "->" in path else parts[0])
        safe_print(f"[Forms] 选择菜单: {path}")
        return item

    def get_edit_text(self, index: int = 0):
        """读取第 index 个 Edit 控件的文本"""
        edits = self.window.child_windows(control_type="Edit")
        if index < len(edits):
            val = edits[index].window_text()
            safe_print(f"[Forms] 读取字段[{index}]: {val}")
            return val
        safe_print(f"[WARN] 未找到第 {index} 个编辑框")
        return None

    def screenshot(self, path: str):
        try:
            self.window.capture_as_image().save(path)
            safe_print(f"[Forms] 截图已保存: {path}")
        except Exception as e:
            safe_print(f"[WARN] 截图失败: {e}")


# ── 在已登录页面里触发 Forms 职责并捕获 JNLP ─────────────────────────────
async def trigger_forms_and_capture(page, responsibility: str, jnlp_dir: str,
                                    jnlp_name: str = "erp_forms.jnlp") -> str:
    """
    在已登录的 EBS 页面中点击名为 responsibility 的职责，拦截由此产生的
    JNLP 下载，保存到 jnlp_dir/jnlp_name，返回 jnlp 路径（未捕获返回 None）。

    说明：EBS 的 Navigator 树 / 职责列表结构各异，这里用“按文字点击”的通用方式；
    若你的环境职责入口不同，可在 erp_ops.py 里定制点击路径后再调用本函数。
    """
    os.makedirs(jnlp_dir, exist_ok=True)
    jnlp_path = os.path.join(jnlp_dir, jnlp_name)

    from playwright.async_api import expect
    try:
        async with page.expect_download(timeout=30000) as dl_info:
            # 优先按职责文字点击；失败则回退到通用链接
            try:
                await page.get_by_text(responsibility, exact=False).first.click()
            except Exception:
                await page.locator(f"a:has-text('{responsibility}')").first.click()
        download = await dl_info.value
        suggested = download.suggested_filename or jnlp_name
        if not suggested.lower().endswith(".jnlp"):
            suggested = jnlp_name
        jnlp_path = os.path.join(jnlp_dir, suggested)
        await download.save_as(jnlp_path)
        safe_print(f"[Forms] 已捕获 JNLP: {jnlp_path}")
        return jnlp_path
    except Exception as e:
        safe_print(f"[WARN] 未捕获到 JNLP（可能该职责是网页或入口不同）: {e}")
        # 兜底：检查当前 URL 是否直接是 forms 启动地址
        url = page.url
        if "forms" in url.lower() or "frmservlet" in url.lower():
            safe_print(f"[Forms] 检测到 forms 启动地址: {url}（可手动用 javaws 打开）")
        return None


def demo_open_and_drive(responsibility: str, jnlp_dir: str):
    """
    端到端示例（需在已登录上下文之后调用，或单独演示 pywinauto 部分）：
      1. 启动 Forms（需先有 jnlp_path；此处仅演示窗口驱动）
      2. 连接、键入、点按钮、读字段、截图
    实际项目中请按真实表单字段替换下面的标签/索引。
    """
    app = FormsApp()
    if not app.connect(title_re=".*Oracle.*|.*Forms.*", timeout=60):
        return False
    app.screenshot(os.path.join(jnlp_dir, "forms_shot.png"))
    # ↓↓↓ 下面按你实际的表单替换 ↓↓↓
    # app.type_text("示例查询条件")
    # app.click_button("确定")
    # val = app.get_edit_text(0)
    safe_print("[Forms] 已就绪，请按实际表单在 erp_ops.py 中编写具体操作步骤")
    return True


if __name__ == "__main__":
    # 单独运行：仅校验 javaws 是否可用
    jw = find_javaws()
    safe_print(f"javaws: {jw or 'NOT FOUND'}")
