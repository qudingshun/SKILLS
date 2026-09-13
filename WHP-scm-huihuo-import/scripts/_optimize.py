"""
Transform huihuo_scm.py v2.0 with optimizations:
1. Extract duplicate dialog detection -> shared detect_dialog_error()
2. Reduce sleep constants by ~50%
3. Remove unused --batch-size parameter
4. Fix is_logged_in variable naming
"""
import re

SRC = r'C:\Users\qudin\.openclaw\workspace\skills\WHP-scm-huihuo-import\scripts\huihuo_scm.py'
DST = r'E:\whirlpool-china\SCM.py'

with open(SRC, 'r', encoding='utf-8') as f:
    text = f.read()

# ================================================================
# 1. Insert detect_dialog_error function after wait_loadmask
# ================================================================

DIALOG_FUNC_PREFIX = """\
async def detect_dialog_error(page, action_label="操作"):
    \"\"\"检测SCM弹窗，返回错误文本（有错误）或空字符串（无/普通弹窗）\"\"\"
    dialog_text = \"\"
    try:
        dialog_text = await page.evaluate(\"\"\"() => {
            function isVisible(el) {
                if (el.offsetParent !== null) return true;
                try {
                    var style = window.getComputedStyle(el);
                    return style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0';
                } catch(e) {
                    return false;
                }
            }
            function getVisibleText(sel) {
                var els = document.querySelectorAll(sel);
                var texts = [];
                for (var el of els) {
                    if (isVisible(el)) {
                        var t = el.textContent.replace(/\\s+/g, ' ').trim();
                        if (t) texts.push(t);
                    }
                }
                return texts;
            }
            function getWindowText(w) {
                if (!isVisible(w)) return '';
                var body = w.querySelector('.x-window-body, .x-window-bwrap');
                if (!body) return '';
                return body.textContent.replace(/\\s+/g, ' ').trim();
            }
            var allTexts = [];
            allTexts = allTexts.concat(getVisibleText('.layui-layer-content'));
            var wins = document.querySelectorAll('.x-window');
            for (var w of wins) {
                var t = getWindowText(w);
                if (t) allTexts.push(t);
            }
            allTexts = allTexts.concat(getVisibleText('.x-message-box'));
            allTexts = allTexts.concat(getVisibleText('[class*="msgbox"]'));
            return allTexts.join(' |\\\\n');
        }()\"\"\")
    except Exception as e:
        print(f\" [WARN] 弹窗检测异常: {e}\")
        return \"\"

    if dialog_text:
        print(f\" [{action_label}] 弹窗: {dialog_text[:200]}\")
        if any(kw in dialog_text for kw in [\"失败\", \"错误\", \"非法\", \"Error\", \"error\", \"异常\", \"操作失败\", \"请选择需要修改\", \"没有符合\"]):
            print(f\" [{action_label}] 弹窗含失败信息，中止\")
            for sel in ['.layui-layer-btn1', 'a.layui-layer-btn1',
                        '.layui-layer-close', '.x-tool-close']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue
            return dialog_text.split('|')[0].strip()
    else:
        print(f\" [{action_label}] 弹窗: (空/未检测到)\")
    return \"\"

"""

# Insert before "# 回货计划导入 — 新增行填数据"
insert_marker = "# 回货计划导入 — 新增行填数据"
idx = text.find(insert_marker)
if idx == -1:
    print("ERROR: marker not found")
    exit(1)
text = text[:idx] + DIALOG_FUNC_PREFIX + "\n" + text[idx:]

# ================================================================
# 2. Replace dialog blocks with function calls
# ================================================================

# Phase A: save_row_only dialog block
a_marker = '    # 保存确认前检测弹窗内容\n    await asyncio.sleep(0.3)\n    dialog_text = ""\n    try:\n        dialog_text = await page.evaluate("""() => {'
a_end_marker = '    else:\n        print(" [弹窗] (空/未检测到弹窗文本)")'

# Find the full blocks using markers
def find_block_ends(text, start_marker, end_marker):
    """Find start and end positions of a block"""
    start = text.find(start_marker)
    if start == -1:
        return None
    end = text.find(end_marker, start)
    if end == -1:
        return None
    end += len(end_marker)
    return start, end

# save_row_only block
block1 = find_block_ends(text, a_marker, a_end_marker)
if block1:
    s, e = block1
    print(f"save_row_only dialog block: {s}..{e}")
    text = text[:s] + "    dialog_error = await detect_dialog_error(page, \"保存\")\n    if dialog_error:\n        return dialog_error" + text[e:]

# save_and_audit_row block (same marker, only one should remain)
block2 = find_block_ends(text, a_marker, a_end_marker)
if block2:
    s, e = block2
    print(f"save_and_audit_row dialog block: {s}..{e}")
    text = text[:s] + "    dialog_error = await detect_dialog_error(page, \"保存\")\n    if dialog_error:\n        return dialog_error" + text[e:]

# release_huihuo dialog block - different marker
r_marker = '    # 检测弹窗内容——读取对话框文本\n    await asyncio.sleep(0.5)\n    dialog_text = ""\n    try:\n        dialog_text = await page.evaluate("""() => {'
r_end = '    else:\n        print(" [弹窗] (空/未检测到弹窗文本)")'
block3 = find_block_ends(text, r_marker, r_end)
if block3:
    s, e = block3
    print(f"release_huihuo dialog block: {s}..{e}")
    text = text[:s] + """    dialog_error = await detect_dialog_error(page, "发放")
    if dialog_error:
        print("\\n [FAIL] 发放失败！")
        return dialog_error""" + text[e:]

# ================================================================
# 3. Reduce sleep constants
# ================================================================

# sleep(5) -> sleep(2)  (login page loading)
# sleep(3) -> sleep(1.5) (general waits)
# sleep(2) -> sleep(1)   (most confirm waits)
# sleep(1.5) -> sleep(0.8) (navigation waits)

print(f"\nBefore sleep reduction:")
sleeps_before = re.findall(r'asyncio\.sleep\(([\d.]+)\)', text)
total_before = sum(float(x) for x in sleeps_before)
print(f"  Total sleep time: {total_before:.1f}s")

# Order matters: replace larger values first
for old_val, new_val in [("asyncio.sleep(5)", "asyncio.sleep(2)"),
                          ("asyncio.sleep(3)", "asyncio.sleep(1.5)")]:
    cnt = text.count(old_val)
    text = text.replace(old_val, new_val)
    print(f"  {old_val} -> {new_val}: {cnt}x")

# Replace sleep(2) -> sleep(1)
cnt = text.count("asyncio.sleep(2)")
text = text.replace("asyncio.sleep(2)", "asyncio.sleep(1)")
print(f"  sleep(2) -> sleep(1): {cnt}x")

# Replace sleep(1.5) -> sleep(0.8)
cnt = text.count("asyncio.sleep(1.5)")
text = text.replace("asyncio.sleep(1.5)", "asyncio.sleep(0.8)")
print(f"  sleep(1.5) -> sleep(0.8): {cnt}x")

sleeps_after = re.findall(r'asyncio\.sleep\(([\d.]+)\)', text)
total_after = sum(float(x) for x in sleeps_after)
print(f"After sleep reduction:")
print(f"  Total sleep time: {total_after:.1f}s")
print(f"  Reduction: {total_before - total_after:.1f}s ({(1 - total_after/total_before)*100:.0f}%)")

# ================================================================
# 4. Fix is_logged_in variable naming
# ================================================================

text = text.replace(
    '        has_login = await page.evaluate(',
    '        has_login_form = await page.evaluate('
)
text = text.replace(
    '        return not has_login',
    '        return not has_login_form'
)

# ================================================================
# 5. Remove unused --batch-size parameter
# ================================================================

text = text.replace(
    '    parser.add_argument("--batch-size", type=int, default=20,\n                        help="批量模式每批上限（默认20）")',
    ''
)
text = text.replace(
    'async def run_main(items, mode="auto", batch_size=20):',
    'async def run_main(items, mode="auto"):'
)
text = text.replace(
    '    success = await run_main(items, mode=args.mode, batch_size=args.batch_size)',
    '    success = await run_main(items, mode=args.mode)'
)

# ================================================================
# 6. Update version header
# ================================================================

text = text.replace(
    'v2.0 — 四阶段重构：格式校验 → 批量录入 → 批量审批 → 逐条发放',
    'v2.1 — 四阶段优化：dialog检测合并，强制等待减半',
    1
)

# ================================================================
# Write output
# ================================================================

with open(DST, 'w', encoding='utf-8') as f:
    f.write(text)

final_lines = len(text.splitlines())
print(f"\nWritten to: {DST}")
print(f"Final lines: {final_lines}")

# Verify
remaining_dialog = text.count("function isVisible")
print(f"Remaining isVisible blocks: {remaining_dialog} (should be 1, in detect_dialog_error)")
