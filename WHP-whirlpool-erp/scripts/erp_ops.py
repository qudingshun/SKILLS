#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_ops - WHP ERP 操作编排（CLI 入口）

子命令：
  setup          交互式设置 ERP 密码（明文不落盘）
  check          校验密码能否解密
  doctor         【排错首选】诊断登录通道：IE11 COM / Edge IE 模式 / 纯 HTTP
  login-ie11     【登录主路径，2026-11-04 最终确认】IE11(COM) 登录 EBS，
                 自动切简体中文；结束自动注销+关 IE（--keep 保留）
  login-http     备用：纯 HTTP 登录 + 实读主页校验，1 秒级；不承载 Forms
  login          Playwright(Edge) 备用路径（老 TLS 下通常握手失败）
  open-forms     【IE11 路径】进入指定职责并拉起 Oracle Forms（Java 窗口）
                 用法: open-forms <职责名> [功能名]   功能名缺省=仅列出该职责下全部功能
  list-funcs     列出职责下全部功能（同 open-forms 缺省功能名）

IE 实例管理（免堆积）：每次运行前自动关闭上一次遗留的 IE 实例（只关本脚本登记的，
不碰用户自己开的）；运行结束默认关闭。登记记录在 .cache/ie_instances.json。

示例：
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py setup
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py check
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py login-ie11
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py open-forms "PO,SANYO合肥三洋物料计划员"
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py open-forms "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台"

登录通道说明（2026-11-04 三次复核，最终结论，详见 docs/DEV_PLAN.md 第七节）：
  * 服务器只认老 TLS，Chromium 系（Edge/Playwright）报
    ERR_SSL_VERSION_OR_CIPHER_MISMATCH；
  * IE11（COM 自动化）走 Windows SCHANNEL，能过老 TLS —— **登录主路径**；
  * 纯 HTTP（urllib + SECLEVEL=0）1 秒级 —— **备用**（不承载 Forms）；
  * Edge 的 IE 模式不提供 COM DOM、不加载 Java 插件 —— 不作为登录形式；
  * 360 浏览器不用（运行时抢占 IE 内核 COM 注册，干扰 IE11）。

  ⚠️ 关键教训：之前「Win11 停用 IE11」是误判。根因是 360 的
  `360chromeie.exe` 抢占 IE 内核 COM 注册导致 Dispatch 报 E_NOINTERFACE；
  360 退出后 IE11 立即恢复（login-ie11 --no-fallback 实测退出码 0）。
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erp_common import safe_print, ERP_USERNAME
import erp_secure_config as sec
import erp_login as login_mod
import erp_forms as forms_mod


JNLP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "forms_runtime")


def cmd_setup():
    sec.interactive_setup()


def cmd_check():
    ok = sec.check_service("erp")
    sys.exit(0 if ok else 2)


def cmd_login():
    headless = os.environ.get("WP_HEADLESS", "").strip() == "1"
    fresh = "--fresh" in sys.argv
    rc = asyncio.run(login_mod.login(headless=headless, fresh=fresh))
    sys.exit(rc)


def cmd_doctor():
    """诊断登录通道（IE11 COM / Edge IE 模式 / 纯 HTTP），不打开浏览器窗口。"""
    import erp_session
    sys.exit(erp_session.doctor())


def cmd_login_http():
    """登录主路径：纯 HTTP 会话 + 主页实读校验。"""
    import erp_session
    try:
        erp_session.login(verify=True)
        sys.exit(0)
    except Exception as e:
        safe_print(f"[FAIL] 登录失败：{type(e).__name__}: {e}")
        safe_print("[提示] 先跑 erp_ops.py doctor 看通道诊断 / erp_ops.py check 校验密码")
        sys.exit(2)


def cmd_login_ie11():
    """登录主路径：IE11（COM）。可用走原路径；不可用（常见因 360 抢占 COM）则诊断。

    IE11 本身可用（2026-11-04 实测 login-ie11 --no-fallback 退出码 0）。
    若 COM 报 E_NOINTERFACE，最常见原因是 360 浏览器在跑（`360chromeie.exe`
    抢占 IE 内核 COM 注册），先退出 360 再试；纯 HTTP 仅作临时替代（不承载 Forms）。
    """
    import erp_ie11
    import erp_session

    if "--no-fallback" not in sys.argv:
        state = erp_session.probe_ie11_com()
        if not state["ok"]:
            safe_print(f"[诊断] IE11 COM 不可用：{state['detail']}")
            safe_print("[诊断] 最常见原因：360 浏览器（360se.exe/360chromeie.exe）正在运行，")
            safe_print("        抢占 IE 内核 COM 注册。请先退出 360 再重试（IE11 本身可用）。")
            safe_print("[诊断] 若仍要临时登录，可用 login-http（纯 HTTP，但不承载 Forms）。")
            safe_print("[提示] erp_ops.py doctor 看完整评估；--no-fallback 强制走原 IE11 路径")
            return cmd_login_http()

    keep = "--keep" in sys.argv or "--keep-ie" in sys.argv
    lang = "" if "--en" in sys.argv else "ZHS"
    rc = erp_ie11.login_ie11(visible=True, close_after=not keep, lang=lang,
                             logout=(not keep))
    sys.exit(rc)


def cmd_logout():
    """注销 EBS 会话并关闭本脚本开的全部 IE 窗口（程序退出收口）"""
    import erp_ie11
    logout_only = "--no-close" in sys.argv      # 只注销、不关窗口
    if logout_only:
        ok = erp_ie11.logout_ebs()
        sys.exit(0 if ok else 2)
    closed = erp_ie11.close_all(logout=True)
    sys.exit(0 if closed >= 0 else 2)


def cmd_open_forms(responsibility: str, func_name: str = ""):
    """
    【IE11 路径，实测可行】登录 -> 点职责展开 -> 点功能 -> 等 Oracle Forms
    Java 窗口（SunAwtFrame）出现 -> pywinauto 连接。

    func_name 缺省时仅列出该职责下全部功能，不拉起 Forms。
    """
    import erp_navigator
    import erp_ie11
    from erp_ie11 import is_logged_in

    shot = os.path.join(JNLP_DIR, "..", "logs", "forms_window.png")

    if not func_name:
        # 仅列出职责下的功能
        ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
        if ie is None or not is_logged_in(ie):
            safe_print("[FAIL] 登录失败")
            sys.exit(2)
        if not erp_navigator.expand_responsibility(ie, responsibility):
            sys.exit(3)
        funcs = erp_navigator.list_functions(ie, resp_name=responsibility)
        safe_print(f"职责「{responsibility}」下共 {len(funcs)} 个功能:")
        for f in funcs:
            safe_print(f"  - {f['name']}")
        safe_print("[提示] 用 open-forms <职责名> <功能名> 拉起对应 Forms")
        # 只列功能、未拉起 Forms，IE 用完即关（会先注销 EBS）
        erp_ie11.close_all(logout=True)
        return

    keep = "--keep-ie" in sys.argv or "--keep" in sys.argv
    app = erp_navigator.open_function(
        responsibility, func_name, timeout=150,
        shot_path=os.path.normpath(shot),
        close_ie=not keep)
    try:
        if app is None:
            safe_print("[FAIL] Forms 拉起失败，详见 logs/erp.log")
            sys.exit(4)
        safe_print("[OK] Forms 已就绪，可用 erp_forms.FormsApp 驱动（键盘/坐标/菜单）")
        safe_print(f"MEDIA:{os.path.normpath(shot)}")
    finally:
        # 收口：默认注销 EBS + 关闭 IE/Forms；--keep-ie 才保留（此后可用
        # erp_ops.py logout 结束，或在后续流程里复用该窗口）
        if not keep:
            import erp_ie11
            erp_ie11.close_all(logout=True)


def cmd_describe():
    """
    打开（或复用）EBS 主页并【实读】页面内容做验证：
      - 页面标题
      - 登录身份（用户名）
      - 主页上全部职责列表
      - 页面可见文本片段
      - 截图
    默认保留 IE 窗口（供继续操作）；加 --close 则读完注销并关闭。
    """
    import erp_ie11
    import erp_navigator
    import re

    ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
    if ie is None or not erp_ie11.is_logged_in(ie):
        safe_print("[FAIL] 登录失败")
        erp_ie11.close_all(logout=True)
        sys.exit(2)

    try:
        title = erp_ie11.page_title(ie)
        text = erp_ie11.body_text(ie)
        m = re.search(r"登录身份\s*([A-Za-z0-9]+)", text)
        user = m.group(1) if m else "?"
        resps = erp_navigator.list_responsibilities(ie)

        safe_print("=" * 56)
        safe_print(f"[识别] 页面标题 : {title}")
        safe_print(f"[识别] 登录身份 : {user}")
        safe_print(f"[识别] 当前 URL : {(ie.LocationURL or '')[:80]}")
        safe_print(f"[识别] 职责列表 : 共 {len(resps)} 个")
        for i, r in enumerate(resps, 1):
            safe_print(f"   {i:>2}. {r}")
        safe_print("-" * 56)
        snippet = re.sub(r"\s+", " ", text)[:260]
        safe_print(f"[识别] 页面文本片段: {snippet}")
        safe_print("-" * 56)

        shot = os.path.normpath(os.path.join(
            JNLP_DIR, "..", "logs", "ebs_home_describe.png"))
        ok = erp_ie11.screenshot_ie(ie, shot)
        if ok and os.path.exists(shot):
            safe_print(f"[识别] 截图: {os.path.abspath(shot)}")
            safe_print(f"MEDIA:{os.path.abspath(shot)}")
        safe_print("[提示] IE 窗口已保留；退出时运行 "
                   "erp_ops.py logout 注销并关闭")
    except Exception as e:
        safe_print(f"[FAIL] 识别过程出错: {e}")
    finally:
        if "--close" in sys.argv or "--close-ie" in sys.argv:
            erp_ie11.close_all(logout=True)


def cmd_ui_probe(responsibility: str, func_name: str):
    """
    【界面元素识别】进入职责/功能拉起 Oracle Forms，然后：
      - 截图
      - 用模板库自动识别界面元素（查找/确定/取消/打开…）的位置
      - 打印相对坐标 + 置信度
    """
    import erp_navigator
    import erp_ui

    form = erp_ui.form_id(responsibility, func_name)
    store = erp_ui.TemplateStore()
    if not store.exists(form):
        safe_print(f"[FAIL] 模板库「{form}」不存在。先用 crop 建模板：")
        safe_print(f"       E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py "
                   f"crop <截图> \"{form}\" <名字> <x> <y> <w> <h>")
        sys.exit(5)

    shot = os.path.join(JNLP_DIR, "..", "logs", "ui_probe.png")
    keep = "--keep-ie" in sys.argv or "--keep" in sys.argv
    app = erp_navigator.open_function(
        responsibility, func_name, timeout=150,
        shot_path=os.path.normpath(shot), close_ie=not keep)
    if app is None:
        safe_print("[FAIL] Forms 拉起失败，详见 logs/erp.log")
        sys.exit(4)

    try:
        found = erp_ui.locate_all(app, form)
        wr = erp_ui.window_rect(app)
        safe_print(f"窗口屏幕矩形: {wr}")
        if not found:
            safe_print("[WARN] 未识别到任何元素（模板库与当前界面不匹配？）")
            sys.exit(6)
        for name, r in found.items():
            safe_print(f"  {name}: 相对({r.x},{r.y},{r.w},{r.h}) "
                       f"置信度={r.score:.3f}  中心=({r.center[0]},{r.center[1]})")
        safe_print(f"MEDIA:{os.path.normpath(shot)}")
    finally:
        # 收口：默认注销 EBS + 关闭 IE/Forms；--keep-ie 才保留
        if not keep:
            import erp_ie11
            erp_ie11.close_all(logout=True)


def cmd_ui_click(responsibility: str, func_name: str, element: str):
    """定位并点击界面元素（验证「自动识别 + 点击」闭环）"""
    import erp_navigator
    import erp_ui

    form = erp_ui.form_id(responsibility, func_name)
    shot = os.path.join(JNLP_DIR, "..", "logs", "ui_click.png")
    keep = "--keep-ie" in sys.argv or "--keep" in sys.argv
    app = erp_navigator.open_function(
        responsibility, func_name, timeout=150,
        shot_path=os.path.normpath(shot), close_ie=not keep)
    if app is None:
        safe_print("[FAIL] Forms 拉起失败")
        sys.exit(4)
    try:
        if not erp_ui.click(app, element, form):
            safe_print(f"[FAIL] 未识别/未点击成功: {element}")
            sys.exit(6)
        safe_print(f"[OK] 已点击: {element}")
        time.sleep(1)
        app.screenshot(os.path.normpath(shot))
        safe_print(f"MEDIA:{os.path.normpath(shot)}")
    finally:
        # 收口：默认注销 EBS + 关闭 IE/Forms；--keep-ie 才保留
        if not keep:
            import erp_ie11
            erp_ie11.close_all(logout=True)


def main():
    args = sys.argv[1:]
    if not args:
        safe_print("用法: erp_ops.py {setup|check|doctor|login-http|login-ie11|login|"
                   "logout|describe|open-forms <职责名> [功能名]|"
                   "ui-probe <职责名> <功能名>|ui-click <职责名> <功能名> <元素名>}")
        safe_print("      登录请用 login-http；排错请先跑 doctor")
        safe_print("      所有连 ERP 的命令结束时默认注销 EBS + 关闭 IE；"
                   "想保留窗口加 --keep-ie")
        sys.exit(1)
    cmd = args[0]
    if cmd == "setup":
        cmd_setup()
    elif cmd == "check":
        cmd_check()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd in ("login-http", "login-session"):
        cmd_login_http()
    elif cmd == "login":
        cmd_login()
    elif cmd == "login-ie11":
        cmd_login_ie11()
    elif cmd in ("logout", "close"):
        cmd_logout()
    elif cmd == "describe":
        cmd_describe()
    elif cmd == "cleanup":
        import erp_ie11
        force = "--force" in sys.argv
        n = erp_ie11.cleanup_automation_leftovers(dry_run=not force)
        if force:
            safe_print(f"[OK] 已关闭 {n} 个 360 承接窗口"
                       "（Forms 窗口一律不自动关闭，不干预 360 进程）")
        else:
            safe_print("[OK] 只做发现/预览，未关闭任何窗口；"
                       "确需清理 360 承接页请显式加 --force")
        sys.exit(0)
    elif cmd in ("open-forms", "list-funcs"):
        resp = args[1] if len(args) > 1 else ""
        if not resp:
            safe_print("[FAIL] 请提供职责名称: erp_ops.py open-forms "
                       "\"PO,SANYO合肥三洋物料计划员\" [功能名]")
            sys.exit(1)
        func = args[2] if len(args) > 2 else ""
        cmd_open_forms(resp, func)
    elif cmd == "ui-probe":
        if len(args) < 3:
            safe_print("[FAIL] 用法: ui-probe <职责名> <功能名>")
            sys.exit(1)
        cmd_ui_probe(args[1], args[2])
    elif cmd == "ui-click":
        if len(args) < 4:
            safe_print("[FAIL] 用法: ui-click <职责名> <功能名> <元素名>")
            sys.exit(1)
        cmd_ui_click(args[1], args[2], args[3])
    else:
        safe_print(f"[FAIL] 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
