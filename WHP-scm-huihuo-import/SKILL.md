---
name: WHP-scm-huihuo-import
description: >
  SCM 回货计划导入 & 发放自动化。
  登录 SCM 系统，自动完成回货计划的新增导入（填写6列数据）、保存审核，
  以及回货计划的筛选全选发放。
  
  Trigger keywords: 回货, huihuo, 回货计划, SCM回货, 帮我回货, 无头回货, headless回货
  
  Usage examples:
  - "帮我回货 70C012345 5"
  - "帮我回货 70C012345 5 2026-06-01"
  - "帮我回货 70C012345 5 2026-06-01 售后配件"
  - "回货 70C11099 2, 70A01234 3 紧急补货"
  - "无头回货 70C012345 5"（后台静默执行）
---

# SCM 回货计划导入 & 发放

## 前置条件

- Python 3.11+ (`python --version`)
- Python 依赖:
  ```bash
  pip install playwright ddddocr cryptography
  playwright install msedge
  ```
- Edge 浏览器已安装
- 依赖验证: `python -c "from playwright.sync_api import sync_playwright; from cryptography.hazmat.primitives.ciphers import Cipher; print('ok')"`

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **POWERHELL 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，这会直接报语法错误，脚本不会运行。
> 必须通过 exec 的 `workdir` 参数传递工作目录。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js --material \"70C012345\" --qty \"5\" [--date \"YYYY-MM-DD\"] [--remarks \"备注文字\"] [--visible]",
    "workdir": "E:\\SKILLS\\WHP-scm-huihuo-import",
    "timeout": 600
  }
}
```
> ⚡ **command 里只放纯执行语句，不带 `cd`、不带 `&&`、不带 `|`。**

### "帮我回货 {料号} {数量} [日期] [备注]"
```bash
node scripts/run.js --material "70C012345" --qty "5"
# 带日期:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01"
# 带备注:
node scripts/run.js --material "70C012345" --qty "5" --remarks "售后配件"
# 全参数:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01" --remarks "售后配件"
```

### 可见模式（用户明确要求"显示浏览器窗口"/"调试"时）
```bash
node scripts/run.js --visible --material "70C012345" --qty "5"
# 多行：
node scripts/run.js --visible --data "70C11099 2, 70A01234 3"
```
> ⚡ 默认即无头模式：浏览器窗口不可见，后台静默运行。`--visible` 可放在任意位置。

### 多行回货
```
node scripts/run.js --data "70C11099 2, 70A01234 3 紧急补货"
```

### 多行换行格式回货（用户输入）
```
# 用户输入是换行分隔，需要合并为逗号分隔
# 输入:
#   PUA313 9000
#   3012111350140 2000
#   PUA223 131
# 合并为:
node scripts/run.js --data "PUA313 9000, 3012111350140 2000, PUA223 131"
```

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-scm-huihuo-import`
3. **命令体中禁止写 `cd ... && ...` 格式**，必须通过 `workdir` 参数传递工作目录
4. **禁止在 command 中使用 `python`**，必须用 `py`（系统只有 `py.exe`）
5. 用户输入的中文逗号 `，` → 自动替换为英文逗号 `,`
6. 多行输入先转换为逗号分隔后再传给 `--data`
7. 启动后必须用 `process(poll)` 等待完成并执行 `process(log)` 获取完整日志再汇报
8. 默认即无头模式（无需任何参数），浏览器窗口不可见后台静默运行；仅当用户明确要求「显示浏览器窗口」或「调试」时才追加 `--visible` 参数

## 执行流程（直通批量导入模式）

### 1. 输入格式检查
- 料号格式检查（字母+数字，3-25位）
- 数量检查（正整数）
- 格式不通过的物料跳过，其余继续处理

### 2. 登录 & 会话检查
- 登录 SCM (https://scm.whirlpool-china.com:7580/websrm/)
- OCR 识别验证码（ddddocr，最多3次）
- 会话存活检查（操作间自动重新登录）

### 3. 批量导入（一次导航，逐行新增，统一保存审核）
- 导航到「回货计划导入」
- 逐行：点击新增 → 填入6列数据（日期/料号/数量/组织M03/接收地址/备注）
- 每行填完立即保存，最后一行保存+审核+启动
- 保存失败时报告失败原因

### 4. 逐条发放（一次导航，逐条筛选发放，容错模式）
- 导航到「回货计划发放」
- 逐条：筛选料号 → 勾选复选框（只显示未完全分配） → 取消滤掉缺料为0 → 全选 → 发放
- **容错**：单条发放失败不中断后续，记录失败原因
- 最终输出：成功/失败清单

## 异常处理

- 仅运行一次，失败直接报错退出
- **失败时返回弹窗错误文本**：无论是导入还是发放，如果 SCM 弹窗包含错误信息（含"失败/错误/非法/Error/异常/操作失败"关键词），脚本会拦截弹窗、关闭它，并将弹窗内容（如 `非法数据：物料[XXX]...超出...` ）作为错误原因返回，附在 SUMMARY 和回复中。你直接看消息就知道为什么失败，不用再进 SCM 查
- **填写数据后异常不重试**：
  - 从点击「新增」按钮开始标记为"已开始填写数据"
  - 此后的任何异常（浏览器崩溃、页面异常）→ 直接中止运行
  - 原因：数据可能已部分写入，重试可能导致重复或数据不一致
- 任何步骤失败都会中止流程并提示，请人工检查 SCM 系统

## 参数说明

| 参数 | 必须 | 默认值 | 说明 | 示例 |
|------|:----:|:--------|------|------|
| 料号 | ✅ | — | 物料编码（字母+数字，3-25位） | `70C012345` |
| 数量 | ✅ | — | 回货数量（正整数） | `5` |
| 日期 | ❌ | **当前月最后一天** | 写了就用写的，不写就默认 | `2026-06-01` |
| 备注 | ❌ | 空 | 可选 | `售后配件` |

多行数据用逗号分隔：`70C11099 2, 70A01234 3 紧急补货`

### 日期参数说明
- **默认值不是当前日期，而是当前月的最后一天**（2026年6月→`2026-06-30`）
- 用户写了日期 → 使用用户提供的日期
- 用户没写日期 → 不传 `--date`，`run.js` 内部默认取当前月最后一天
- 日期格式固定为 `YYYY-MM-DD`
- 批量回货时，日期参数适用于**所有料号**

## 登录凭证

- URL: https://scm.whirlpool-china.com:7580/websrm/
- 账号: 配置于 `scripts/huihuo_runtime_config.json` → `scm.username`
- 密码: AES-256 加密存储于 `scripts/huihuo_runtime_config/passwords/scm_password.dat`
- 验证码: 自动 OCR 识别
- 密码管理: 运行 `python scripts/huihuo_secure_config.py` 可交互式设置各服务密码

## 浏览器

- 使用 msedge
- 默认无头模式（`headless=True`，浏览器窗口不可见，后台静默运行）
- `--visible` 参数启用可见模式（窗口可见便于调试）
- 端口: 9222 (远程调试)
- 完成后自动关闭浏览器

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口，解析用户指令，调用固定 venv 下的 Python |
| `scripts/huihuo_scm.py` | SCM 自动化主脚本（Playwright） |
| `scripts/huihuo_secure_config.py` | 配置/密码管理（AES-256 加密） |
| `scripts/install_deps.py` | 一键安装依赖（`py scripts/install_deps.py`） |
| `scripts/huihuo_runtime_config.json` | 运行时配置（用户名等） |
| `scripts/huihuo_runtime_config/passwords/scm_password.dat` | AES-256 加密的 SCM 密码 |

> 运行环境：`E:\SKILLS\.venv`（共享虚拟环境，依赖完整）。

## 开发备注

- Python Playwright 脚本已独立测试可运行
- 如果 SCM 页面元素 ID 变化，需要更新 `huihuo_scm.py` 中的选择器
- 验证码 OCR 依赖 `ddddocr`，首次使用会自动下载模型文件

## 已知修复记录

### 2026-09-16 — 运行环境固定为共享 venv（重要）
- 解释器**固定为** `E:\SKILLS\.venv\Scripts\python.exe`：`run.js` 写死该路径并做存在性校验（缺失直接报错，不再静默用错环境）
- 根因：曾出现放错位置的 `E:\SKILLS\scm-huihuo-import\scripts\.venv`（uv 生成，只有 playwright、缺 cryptography）→ 运行报 `No module named 'cryptography'`。该错误 venv 已删除
- 同时删除 `scripts/pyproject.toml` / `scripts/uv.lock`，避免再次生成不完整 venv
- 清理无用文件：`scripts/_optimize.py`、`scripts/debug_login.py`（含明文密码）、`scripts/huihuo_scm_headless.py`、`scripts/run_headless.js`、`scripts/q.py`、根目录 `_upd_skill.py` / `_update_skill.py`

### 2026-07-19 — 安全升级 / 有头无头合并 / 日志升级
- **凭据安全**：SCM 密码改为 AES-256 加密存储（`huihuo_secure_config.py` + `huihuo_runtime_config/passwords/scm_password.dat`），移除源码明文密码；`huihuo_secure_config.py` 去除 `whirlpool_common` 外部依赖
- **有头/无头合并**：`create_browser(playwright, headless=False)` 统一入口；`run.js` 透传 `--headless`；删除独立无头脚本（`huihuo_scm_headless.py` / `run_headless.js`）
- **依赖新增** `cryptography`
- **日志升级**：`logging` + `RotatingFileHandler` 写 `scripts/scm_huihuo.log`（2MB×5，UTF-8）；`ts()` 改走 logger；`SUMMARY` JSON 写入日志，便于 grep/jq 解析
- **审计修复**：`_capture_save_dialog` 的 `time.sleep` → `asyncio.sleep`（避免阻塞协程）

### 2026-05-30 — 简化 v2.2（去四阶段，直通批量导入）
- 移除四阶段框架和 mode 参数
- 移除 `--mode`/`--batch-size` 参数
- 移除 single 模式，仅保留批量导入
- 移除 `import_single_item` 末尾的 6 列验证补填代码
- 简化 SUMMARY（移除 phase/validation_errors/mode）
- 简化文档

### 2026-05-29 — 四阶段重构 v2.0（已归档为 backup_20260529）
- 新增 Phase 0 纯格式校验
- Phase 2 批量导入
- Phase 3 逐条发放容错模式
- 新增 `--mode auto|batch|single` 和 `--batch-size` 参数

### 2026-05-25 — run_excel.py 不再强制关闭已有 Excel
- 启动前检测 Excel 是否已在运行
- 已运行 → 只关自己打开的 workbook，不调 Quit()
- 未运行 → 正常 Quit()
- 加了 `pythoncom.CoInitialize()`

### 2026-05-25 — 弹窗检测完全失效（CSS 伪类不兼容）

- **根因**：`querySelectorAll` **不支持** `:visible` 伪类（那是 jQuery 伪类/Playwright locator 伪类），两处弹窗检测的 CSS 选择器全部不命中，`dialog_text` 永远为空，错误检测从未触发
- **第一轮修复**：添加关键词 `"非法"`（误以为只是漏词，实际选择器本身就没生效）
- **第二轮修复（完全解决）**：
  1. 删除所有 `:visible` 伪类，改用自定义 `isVisible()` 函数（`offsetParent` + `getComputedStyle` 双重检测）
  2. 扩展 ExtJS 弹窗选择器：`.x-window-body`, `.x-window-bwrap`, `.x-message-box`, `[class*="msgbox"]`
  3. 所有 `page.evaluate` 内不再使用 `:visible`
- **涉及函数**：`save_and_audit_row()`（导入弹窗）、`release_huihuo()`（发放弹窗）
- **测试验证**：修复后 `301B220025494 x3500` 发放弹窗正确识别 `非法数据：物料[301B220025494]...已超出...`，成功拦截报 FAIL，不再误报成功

## 💾 操作经验总结 (Memory Integration)

> 以下要点来自实操沉淀，执行回货任务前请先过一遍。

### 填写顺序（关键！）
日期 → 料号 → 数量 → 组织(M03) → 接收地址 → 备注
**日期必须先填**，否则 ExtJS 行校验会冲掉料号。

### Tab 规则
- 日期、料号、数量：**不要 Tab**（`tab=False`）
- 组织、地址、备注：**可以 Tab**（默认 `tab=True`）
- 不用 Tab 时，下一个 `fill_cell_click_type` 会直接点击目标单元格

### 保存与审核
- 每行填完**立即保存**（`save_row_only`）
- **最后一行**保存后要加**审核+启动**（`save_and_audit_row`）
- 不审核的话，发放页面搜不到数据

### ⚠️ 保存后物料行验证（2026-06-01 新增）
- SCM 在物料编码不合法时**不会弹错误提示**，仅静默丢弃该行 + 显示「保存成功」
- 修复后：`_click_save(mat_code)` 会检查物料编码是否真实出现在弹窗单据明细中
- 未出现则返回错误，不再误报 `import=OK`

### 执行时序（跨模型必须一致）
1. 收到用户指令 → **立即在同一轮输出中包含 `exec` 调用**，不写纯叙述性占位文字
2. workdir 固定为 skill 目录：`E:\SKILLS\WHP-scm-huihuo-import`
3. 命令路径统一用：`node scripts/run.js`（相对 skill 目录）
4. 超时设 600s，等待完成后用 `process(poll)` 获取结果并汇报

### 发放筛选条件
- 勾选「只显示未完全分配的数据」
- **取消**「滤掉缺料为0的数据」（新导入计划缺料=0）
- 料号范围用 `itemcode_start` + `itemcode_end`

<!-- 2026-06-12 经验固化：6条全满贯，多料号逗号/空格分隔均可 -->
