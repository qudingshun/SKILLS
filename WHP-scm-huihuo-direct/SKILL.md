---
name: WHP-scm-huihuo-direct
description: >
  SCM 回货计划导入 & 发放——默认直通版（免前置核查）。
  不做任何前置核查（不查 PO 剩余/已分配、不算实际可用、不写待办），用户报多少数量就直接回多少。
  执行引擎复用 WHP-scm-huihuo-import 的 huihuo_scm.py（同一自动化脚本与加密凭证）。

  Trigger keywords: 回货, 帮我回货, huihuo, 回货计划, SCM回货, 直接回货, 免核查回货, 不核查回货, 直通回货, 不用核查, 直接回, huihuo direct

  Usage examples:
  - "回货 70C012345 5"
  - "帮我回货 70C012345 5 2026-06-01 售后配件"
  - "直接回货 70C11099 2, 70A01234 3"

  ⚠️ 路由规则（2026-10-24 起）：用户说"回货 / 帮我回货 / huihuo" → **本技能**（直通版，不核查）；
  用户说"审核回货 / 核查回货" → WHP-scm-huihuo-import（先核查确认再回货）。
---

# SCM 直接回货（免核查）

> **默认路由**：用户只说"回货 / 帮我回货 / huihuo"时，**默认由本技能执行**（直通，不做前置核查）。
> 只有用户明确说"审核回货 / 核查回货"才走核查版 `WHP-scm-huihuo-import`。

## 与核查版（WHP-scm-huihuo-import）的区别

| | 本技能（直通/免核查，默认） | WHP-scm-huihuo-import（审核版） |
|---|---|---|
| 触发词 | 回货 / 帮我回货 / huihuo / 回货计划 / 直接回货 / 免核查回货 / 不用核查 | 审核回货 / 核查回货 / 审核后回货 / 复核回货 |
| 前置核查 | **无**，不查任何数据 | 先查 PO 剩余 - 已分配 = 实际可用，确认后再回多少 |
| 数量依据 | **用户给多少回多少** | 实际可用（不足时按实际可用回，剩余写待办） |
| 待办事项 `logs/todo.md` | **不读不写** | 由 `huihuo_todo_checker.py` 维护 |
| 报表时效性检查 | **不检查**，不触发重新下载 | >1 小时要询问是否重新下载 |
| 执行引擎 / 凭证 / 日志 | 复用原技能（完全一致） | 同左 |

> **路由铁律**：不带"审核/核查"字样的回货请求（如"回货"、"帮我回货"、"huihuo"）一律走本技能；
> 只有用户明确说"审核回货/核查回货/审核后回货"时才走 `WHP-scm-huihuo-import` 核查版。

## 前置条件

- Python 3.11+（统一使用 `E:\SKILLS\.venv` 虚拟环境）
- 依赖已随仓库 requirements.txt 统一安装（本技能**不新增任何依赖**）:
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe -m pip install -r E:/SKILLS/requirements.txt
  E:/SKILLS/.venv/Scripts/python.exe -m playwright install msedge
  ```
- Edge 浏览器已安装
- 依赖验证: `E:/SKILLS/.venv/Scripts/python.exe -c "from playwright.sync_api import sync_playwright; from cryptography.hazmat.primitives.ciphers import Cipher; print('ok')"`
- **依赖原技能完整**：`E:\SKILLS\WHP-scm-huihuo-import\scripts\huihuo_scm.py` 必须存在（执行引擎、加密凭证都在那边）

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，必须通过 exec 的 `workdir` 参数传递工作目录。
> 路径统一用正斜杠：`E:/SKILLS/...`（bash 不支持反斜杠路径）。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js --material \"70C012345\" --qty \"5\" [--date \"YYYY-MM-DD\"] [--remarks \"备注文字\"] [--headless]",
    "workdir": "E:\\SKILLS\\WHP-scm-huihuo-direct",
    "timeout": 600
  }
}
```

### 执行规则（本技能专属）
1. **收到"回货 X N"（含"直接回货/免核查回货"）指令后立即执行，不查任何数据**——不调 `material-inventory-check`、不跑 `huihuo_todo_checker.py`、不检查报表时效性
2. **不做任何数量判断**：用户给多少就回多少，即使怀疑数量过大也不拦截（这是直通/免核查模式）
3. 用户输入的中文逗号 `，` → 自动替换为英文逗号 `,`
4. 多行输入先转换为逗号分隔后再传给 `--data`
5. 默认即有头模式；仅当用户明确要求「后台静默」或「无头」时才追加 `--headless`
6. 启动后等待完成（timeout 600s）并获取完整日志再汇报
7. **执行后必须查日志确认**：`WHP-scm-huihuo-import/logs/huihuo_success_log.log` 有该料号记录才算成功；仅凭 exit_code=0 不算

### 输出规则
- **回货成功** → 只回复一条 **「回货成功」** 即可，禁止输出清单/日志/耗时等技术细节
- **回货失败** → 输出具体数据：**料号、数量、失败原因**（SCM 弹窗原文 / `release_error` / `[SKIP]` 原因）
- **失败不写待办**（本技能不维护 todo.md），只报告失败原因，由用户决定后续

### 命令示例
```bash
# 单条
node scripts/run.js --material "70C012345" --qty "5"
# 带日期和备注
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01" --remarks "售后配件"
# 多条（逗号分隔最可靠）
node scripts/run.js --data "70C11099 2, 70A01234 3 紧急补货"
# 无头
node scripts/run.js --headless --material "70C012345" --qty "5"
```

### ⚠️ 批量回货已知限制（与核查版相同）
- **`--data` + 换行格式只处理第一行**，多料号一律用**英文逗号分隔**，或逐条调用 `--material/--qty`

## 参数说明

| 参数 | 必须 | 默认值 | 说明 | 示例 |
|------|:----:|:--------|------|------|
| 料号 | ✅ | — | 物料编码（字母+数字，3-25位） | `70C012345` |
| 数量 | ✅ | — | 回货数量（正整数），**按用户给定值直接执行** | `5` |
| 日期 | ❌ | 当前月最后一天 | 固定格式 `YYYY-MM-DD` | `2026-06-01` |
| 备注 | ❌ | 空 | 可选 | `售后配件` |

## 输出路径 / 日志

| 文件 | 说明 |
|------|------|
| `E:\SKILLS\WHP-scm-huihuo-import\logs\scm_huihuo.log` | 回货操作日志（自动轮转 2MB×5） |
| `E:\SKILLS\WHP-scm-huihuo-import\logs\huihuo_success_log.log` | 回货成功日志（增量 CSV，查重/确认用） |

> 日志写在原技能目录下（执行引擎共用），两个技能的操作记录统一审计。

## 异常处理

- 仅运行一次，失败直接报错退出，不自动重试
- **填写数据后异常不重试**：从点击「新增」开始数据可能已部分写入，重试会造成重复计划记录 → 直接中止并报告
- **SCM 弹窗含错误信息**（失败/错误/非法/Error/异常/操作失败）→ 脚本拦截弹窗并把原文作为失败原因返回，直接转告用户
- **超时**（600s）：大数量（≥5,000）或网络慢时导入可能超时 → 先查 `huihuo_success_log.log` 确认是否部分完成，再决定是否重试
- 已知 SCM 拦截规则（重复计划累计、已承诺量超出等）详见 `WHP-scm-huihuo-import/SKILL.md` 的「已知修复记录」——免核查模式下更容易触发，遇到 `非法数据：...已超出 采购订单未完成量...` 时**禁止加大数量重试**，直接报告用户

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口：解析参数 → 调用原技能的 `huihuo_scm.py`（免核查直通，无前置判断） |

> 无独立 Python 脚本、无独立凭证——执行引擎、AES-256 加密密码、运行时配置全部复用 `WHP-scm-huihuo-import`。

## 登录凭证

- URL: https://scm.whirlpool-china.com:7580/websrm/
- 账号/密码/验证码 OCR 配置均在原技能内（`WHP-scm-huihuo-import/scripts/huihuo_runtime_config.json` + 加密密码文件）
- 修改密码：`E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-scm-huihuo-import/scripts/huihuo_secure_config.py`
