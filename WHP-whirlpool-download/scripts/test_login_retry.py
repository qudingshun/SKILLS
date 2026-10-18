# -*- coding: utf-8 -*-
"""离线桩测试：验证 SCM 登录的"验证码 OCR 识别错 → 自动整轮重试"逻辑。

背景（2026-10-15 修复）：
    旧实现把 `for attempt in range(1,4)` 用来重试「OCR 有没有返回字符串」，
    而 ddddocr 几乎总会返回一个字符串，于是 `if captcha: break` 立即跳出，
    实际只提交 1 次登录请求 —— OCR 认错了就直接判定登录失败。
    修复后 3 次循环重试的是「整轮登录」（识别 → 填码 → 提交 → 判断是否登录成功），
    每次失败会关闭"验证码错误"弹窗并刷新验证码。

本测试不联网、不访问 SCM，用假 page 对象驱动 SCMSystem.login()，覆盖三种场景：
    1. 前两次失败、第 3 次成功  → 应提交 3 次、刷新验证码 2 次、返回 True
    2. 第 1 次就成功            → 应提交 1 次、不刷新验证码、返回 True
    3. 三次全失败（非交互环境） → 应提交 3 次后返回 False，且不得卡在 input()

运行：
    E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-whirlpool-download/scripts/test_login_retry.py
退出码 0 = 全部通过，1 = 存在失败。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unified_report_downloader as u


async def _noop():
    return None


async def _ret(value):
    return value


class FakeCM:
    def get_sc_config(self, key, default=None):
        return {"username": "hsa697"}.get(key, default)


class FakeSM:
    def load_password(self, service):
        return "dummy-pw"


class FakeEl:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    async def click(self, **kw):
        self.page.clicks.append(self.sel)

    async def fill(self, value):
        self.page.fills.append((self.sel, value))
        # 只统计"填入真实验证码"，fill("") 清空不算一次提交
        if self.sel == "#kaptcha" and value:
            self.page.kaptcha_fills += 1


class FakeLoc:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    async def is_visible(self, timeout=0):
        # 只有"验证码错误"弹窗的确定按钮可见
        return "确定" in self.sel and self.page.dialog_visible

    async def click(self, **kw):
        self.page.clicks.append(self.sel)
        if "确定" in self.sel:
            self.page.dialog_visible = False


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.keys.append(key)


class FakePage:
    """模拟 SCM 登录页：连续 kaptcha_fills 次提交失败后 is_logged_in 变 True。"""

    def __init__(self, succeed_on_submit=3):
        self.fills, self.clicks, self.keys = [], [], []
        self.kaptcha_fills = 0
        self.dialog_visible = True   # 失败后弹出"验证码错误"
        self.url = "https://scm.example/websrm/"
        self.keyboard = FakeKeyboard(self)

    async def goto(self, *a, **k):
        pass

    async def wait_for_selector(self, sel, timeout=0):
        return FakeEl(self, sel)

    async def query_selector(self, sel):
        return FakeEl(self, sel)

    async def wait_for_load_state(self, *a, **k):
        pass

    async def screenshot(self, **k):
        pass

    async def title(self):
        return "fake"

    def locator(self, sel):
        return FakeLoc(self, sel)


async def main():
    # 让被测代码里的 asyncio.sleep 立即返回，测试不必真等 90 秒
    asyncio.sleep = lambda _t=0: _noop()

    ok = True
    for target, expect_attempts, expect_success in ((3, 3, True), (1, 1, True)):
        scm = u.SCMSystem(FakeCM(), FakeSM())
        page = FakePage(succeed_on_submit=target)
        # OCR 每次都返回非空字符串（复现旧 bug：非空即 break，导致只提交 1 次）
        scm._recognize_captcha = lambda p: _ret("abcd")
        scm.is_logged_in = lambda p: _ret(p.kaptcha_fills >= target)

        result = await scm.login(page)
        changecode = sum(1 for c in page.clicks if c == "#changeCode")
        dismissed = sum(1 for c in page.clicks if "确定" in c)
        print(f"目标: 第{target}次提交成功 | 返回值={result} | 验证码填写次数={page.kaptcha_fills} "
              f"| 刷新验证码={changecode} | 关闭错误弹窗={dismissed}")

        if result != expect_success or page.kaptcha_fills != expect_attempts:
            print("  ✘ 不符合预期")
            ok = False
        else:
            print("  ✔ 符合预期")
        # 每次失败后都应刷新验证码（最后一次成功不算失败）
        if expect_success and changecode != expect_attempts - 1:
            print(f"  ✘ 刷新验证码次数应为 {expect_attempts - 1}，实际 {changecode}")
            ok = False

    # 三次仍失败：应走完 3 轮并返回 False（非交互环境不得挂住、不得调用 input()）
    import types
    u.sys.stdin = types.SimpleNamespace(isatty=lambda: False)
    scm = u.SCMSystem(FakeCM(), FakeSM())
    page = FakePage(succeed_on_submit=99)
    scm._recognize_captcha = lambda p: _ret("abcd")
    scm.is_logged_in = lambda p: _ret(False)
    result = await scm.login(page)
    print(f"全部失败场景: 返回值={result} | 验证码填写次数={page.kaptcha_fills}")
    if result is not False or page.kaptcha_fills != 3:
        print("  ✘ 应尝试 3 轮后返回 False")
        ok = False
    else:
        print("  ✔ 3 轮后干净失败，未卡在 input()")

    print("\n=== 测试结果:", "全部通过 ✔" if ok else "存在失败 ✘", "===")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
