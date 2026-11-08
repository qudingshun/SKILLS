---
name: WHP-scm-huihuo-import
description: >
  SCM 回货计划「审核后回货」自动化（核查版）。
  登录 SCM 系统，先核查 PO 实际可用 / 已分配并确认，再完成回货计划的新增导入（填写6列数据）、保存审核，
  以及回货计划的筛选全选发放。

  Trigger keywords: 审核回货, 核查回货, 审核后回货, 复核回货, 审核回货计划, 审核后回, huihuo audit

  ⚠️ 路由规则（2026-10-24 起）：用户只说「回货 / 帮我回货 / huihuo」（未提审核）→ 改用 WHP-scm-huihuo-direct 技能（直通版，不核查）；
  只有「审核回货 / 核查回货」才由本技能执行（先核查确认再回货）。

  Usage examples:
  - "审核回货 70C012345 5"
  - "审核回货 70C012345 5 2026-06-01"
  - "审核回货 70C012345 5 2026-06-01 售后配件"
  - "核查回货 70C11099 2, 70A01234 3 紧急补货"
  - "无头审核回货 70C012345 5"（后台静默执行）
---

# SCM 回货计划导入 & 发放

> **技能区分**：本技能 = **审核版**（先查 PO 实际可用 → 确认 → 再回货 → 不足写待办），只在用户说"审核回货 / 核查回货"时使用。
> 用户只说「回货 / 帮我回货 / huihuo」时，改用 **`WHP-scm-huihuo-direct`** 技能（直通版：不查数据、按用户给定数量直接执行，执行引擎复用本技能）。

## 前置条件

- Python 3.11+（统一使用 `E:\SKILLS\.venv` 虚拟环境）
- Python 依赖（已随仓库 requirements.txt 统一安装）:
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe -m pip install -r E:/SKILLS/requirements.txt
  E:/SKILLS/.venv/Scripts/python.exe -m playwright install msedge
  ```
- Edge 浏览器已安装
- 依赖验证: `E:/SKILLS/.venv/Scripts/python.exe -c "from playwright.sync_api import sync_playwright; from cryptography.hazmat.primitives.ciphers import Cipher; print('ok')"`
- 运行环境：`E:\SKILLS\.venv`（共享虚拟环境，依赖完整）

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，这会直接报语法错误，脚本不会运行。
> 必须通过 exec 的 `workdir` 参数传递工作目录。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js --material \"70C012345\" --qty \"5\" [--date \"YYYY-MM-DD\"] [--remarks \"备注文字\"] [--headless]",
    "workdir": "E:\\SKILLS\\WHP-scm-huihuo-import",
    "timeout": 600
  }
}
```

### ❗ 待办事项输出铁律（跨模型，绝不可违反）

> **当用户要求输出待办事项/待处理报表时，必须严格按以下规则执行：**
>
> 1. **先读取** `logs/todo.md` 的完整内容
> 2. **原样输出** todo.md 中的 Markdown 表格（含所有列、所有行），不得增删行、不得省略列、不得简化格式
> 3. **禁止用自己的理解重新格式化**——用户要的就是日志文件里那张表的精确副本，包括列顺序和每一列的数据
> 4. 物料名称必须来自 `get_mat_names.py`，不得留空
> 5. 表格下方附合计行：`**未回货合计：X**`
>
> **核心规则：读到什么就输出什么，列一条都不能少。**
>    列结构固定为：`# | 料号 | 物料名称 | 原计划回货 | 已回货 | 未回货 | 采购订单剩余 | 未分配已回货 | 实际可用 | 采购申请(参考) | 能否处理`
>    绝对禁止遗漏任何列，尤其是"原计划回货"和"已回货"两列。
>
> **反面示例**（这些都是用户纠正过的错误）：
> - ❌ 只输出料号和未回货数量（遗漏列）
> - ❌ 用文字列表代替表格
> - ❌ 省略物料名称列
> - ❌ 对齐不齐（Markdown表格格式错误）
> - ❌ "按这个格式输出"后自己发明新格式
> - ❌ 漏掉"原计划回货"列或"已回货"列
>
> **正确做法**：读取 `logs/todo.md` → 原样复制其中的表格 → 输出给用户。
>
> **⚡ 更新后必须输出**：当用户要求"更新数据后输出报表"时，先执行更新流程（修改 todo.md），然后读取更新后的 todo.md 并原样输出表格。禁止更新完数据后用自己的理解重新拼凑表格。

> **执行回货前，必须先用 `material-inventory-check` 技能查询采购订单剩余和已回货未分配，判断逻辑：**
>
> ```
> 实际可用 = 采购订单剩余 - 已回货未分配
>
> if 实际可用 >= 用户要求量:
>     按用户要求量回货
>     回货成功后：新已分配 = 原已分配 + 回货量
>     若 订单剩余 - 新已分配 >= 0 → 完成
>     若不足 → 剩余写待办
> else:
>     按实际可用回货（不是用户要求量）
>     回货成功后：新已分配 = 原已分配 + 回货量
>     实际可用 = 订单剩余 - 新已分配
>     若 实际可用 >= 剩余未回 → 继续回
>     否则 → 剩余写待办
> ```
>
> **示例：** 要求回1000，订单剩余1200，已分配500
> - 实际可用 = 1200 - 500 = 700 < 1000 → 回700
> - 回货后：新已分配 = 500 + 700 = 1200
> - 实际可用 = 1200 - 1200 = 0 < 300 → 300写待办
>
> **待办格式：** 原计划回货 | 已回货 | 未回货 | 采购订单剩余 | 未分配已回货 | 实际可用 | 采购申请 | 能否处理
>
> - 绝不允许跳过判断直接回货
> **⚡ 禁止未经用户明确指令重跑回货。**用户说"不要重新跑""不要再执行""算了"时立即停止；已在待办的料号不得擅自回货。
> ⚡ **command 里只放纯执行语句，不带 `cd`、不带 `&&`、不带 `|`。**
>
> ### 特殊模式：按未回货数字回货
>
> **当用户明确说"按未回货数字回货"或"直接按X数量回货，不用复核"时：**
> - **跳过** 实际可用判断，直接按用户指定的数量（通常是 todo.md 中的"未回货"列值）回货
> - 用户明确说"系统数字刚好够了"或类似表态时，信任用户判断，不要二次查询PO数据再争议
> - 仍需执行成功后查日志确认的步骤
> - 此模式适用于用户基于业务知识知道PO充足的情况

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-scm-huihuo-import`
3. **命令体中禁止写 `cd ... && ...` 格式**，必须通过 `workdir` 参数传递工作目录
4. **统一用仓库虚拟环境调用 Python 脚本**：命令一律 `E:/SKILLS/.venv/Scripts/python.exe scripts/xxx.py`。所有技能共享 `E:\SKILLS\.venv`，禁止使用全局 `py` / `python`（版本可能不一致）
5. 用户输入的中文逗号 `，` → 自动替换为英文逗号 `,`
6. 多行输入先转换为逗号分隔后再传给 `--data`
7. 启动后必须用 `process(poll)` 等待完成并执行 `process(log)` 获取完整日志再汇报
8. 默认即有头模式（显示浏览器窗口）；仅当用户明确要求「后台静默」或「无头」时才追加 `--headless` 参数

### Cross-model rules (IRONCLAD)

#### ⚡ Cron 定时任务模型失效修复

> **当定时任务因模型弃用失败时（报错 `HTTP 404: This model is no longer free` 或 `HTTP 401: Model X is not supported`）：**
>
> 1. 查看 cron 任务配置：`cat ~/AppData/Local/hermes/cron/jobs.json`，找到 `model: "hy3-free"`（或其他已弃用模型）
> 2. 直接编辑 `~/AppData/Local/hermes/cron/jobs.json`，将 `model` 和 `provider` 字段设为 `null`
> 3. 或使用 `cronjob_manage(action='resnap', job_id='...')` 将任务采用当前全局默认模型
> 4. 确认修复后用 `cronjob_manage(action='run', job_id='...')` 触发测试
>
> **注意**：`cronjob_manage(action='update')` 不直接支持 `model`/`provider` 参数，需直接编辑 JSON 或用 `resnap`。

#### ⚡ Bash 环境路径分隔符

> **terminal 在 Windows 上走 bash（git-bash / MSYS），不支持反斜杠路径！**
> 命令中**绝对禁止**写 `E:\SKILLS\...
un.js`，bash 会把 `\` 吃掉/转义，路径被拼接成乱码。
> 必须用正斜杠：`E:/SKILLS/.../run.js`
>
> ❌ `node E:\SKILLS\WHP-scm-huihuo-import\scripts
un.js`
> ✅ `node E:/SKILLS/WHP-scm-huihuo-import/scripts/run.js`

#### ⚡ 技能发现

> **永远先调 `skills_list()` 判断技能是否存在，不要扫磁盘！**

#### Result Output Policy

> **铁律：每次运行必须实时输出结果给用户。**

> **⚡ 输出精简规则（2026-10-14 起，用户明确要求，跨模型必须遵守）**
>
> - **回货成功** → 只回复一条 **「回货成功」** 即可。
>   **禁止**再输出：已回货的料号/数量清单、执行记录表、成功日志行、单据号明细、前几批历史清单、耗时/退出码等技术细节。
> - **回货失败** → 才输出具体数据：**料号、数量、失败原因**（SCM 弹窗原文 / `release_error` / `[SKIP]` 原因），
>   **并写入待办事项** `logs/todo.md`（未完成部分按固定 11 列格式记入待办表，并更新 `未回货合计`）。
> - 用户明确要求「列出清单」或「输出待办」时才例外。

### "审核回货 {料号} {数量} [日期] [备注]"
```bash
node scripts/run.js --material "70C012345" --qty "5"
# 带日期:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01"
# 带备注:
node scripts/run.js --material "70C012345" --qty "5" --remarks "售后配件"
# 全参数:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01" --remarks "售后配件"
```

### 无头模式（用户明确要求"后台静默"/"无头"时）
```bash
node scripts/run.js --headless --material "70C012345" --qty "5"
# 多行：
node scripts/run.js --headless --data "70C11099 2, 70A01234 3"
```
> ⚡ 默认即有头模式：显示浏览器窗口，便于观察进度和排错。`--headless` 可放在任意位置，用于后台静默运行（浏览器窗口不可见）。

### 文件推送格式

> 向用户发送文件时使用 `MEDIA:/absolute/path/to/file` 格式，微信端直接收到附件。例如：`MEDIA:C:/Users/qudin/Pictures/ScreenCaptures/screen_20260926_131812.png`

### 多行回货
```
node scripts/run.js --data "70C11099 2, 70A01234 3 紧急补货"
```

### ⚠️ 批量回货已知限制（重要！）

**`--data` + 换行格式只处理第一行！**

- **现象**：用户输入多行数据（换行分隔），脚本只执行第一条，其余料号不处理
- **原因**：`run.js` 的 `parse_data()` 函数未正确解析换行符，将后续行误读为备注
- **错误示例**：
  ```bash
  node scripts/run.js --data "3010856506140 132
  301B801100177 130"
  # 结果：只处理了 3010856506140，301B801100177 被当成备注
  ```

**推荐方案（按优先级）**：
1. **逗号分隔**（最可靠）：`node scripts/run.js --data "料号 数量，料号 数量"`
2. **逐条调用**（最稳定）：每条用 `--material XXX --qty YYY` 单独执行
3. **换行格式**（不推荐）：脚本只处理第一行

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-scm-huihuo-import`
3. **命令体中禁止写 `cd ... && ...` 格式**，必须通过 `workdir` 参数传递工作目录
4. **统一用仓库虚拟环境调用 Python 脚本**：命令一律 `E:/SKILLS/.venv/Scripts/python.exe scripts/xxx.py`。所有技能共享 `E:\SKILLS\.venv`，禁止使用全局 `py` / `python`（版本可能不一致）
5. 用户输入的中文逗号 `，` → 自动替换为英文逗号 `,`
6. 多行输入先转换为逗号分隔后再传给 `--data`
7. 启动后必须用 `process(poll)` 等待完成并执行 `process(log)` 获取完整日志再汇报
8. 默认即有头模式（显示浏览器窗口）；仅当用户明确要求「后台静默」或「无头」时才追加 `--headless` 参数

### Cross-model rules (IRONCLAD)

#### ⚡ Cron 定时任务模型失效修复

> **当定时任务因模型弃用失败时（报错 `HTTP 404: This model is no longer free` 或 `HTTP 401: Model X is not supported`）：**
>
> 1. 查看 cron 任务配置：`cat ~/AppData/Local/hermes/cron/jobs.json`，找到 `model: "hy3-free"`（或其他已弃用模型）
> 2. 直接编辑 `~/AppData/Local/hermes/cron/jobs.json`，将 `model` 和 `provider` 字段设为 `null`
> 3. 或使用 `cronjob_manage(action='resnap', job_id='...')` 将任务采用当前全局默认模型
> 4. 确认修复后用 `cronjob_manage(action='run', job_id='...')` 触发测试
>
> **注意**：`cronjob_manage(action='update')` 不直接支持 `model`/`provider` 参数，需直接编辑 JSON 或用 `resnap`。

#### ⚡ Bash 环境路径分隔符

> **terminal 在 Windows 上走 bash（git-bash / MSYS），不支持反斜杠路径！**
> 命令中**绝对禁止**写 `E:\SKILLS\...
un.js`，bash 会把 `\` 吃掉/转义，路径被拼接成乱码。
> 必须用正斜杠：`E:/SKILLS/.../run.js`
>
> ❌ `node E:\SKILLS\WHP-scm-huihuo-import\scripts
un.js`
> ✅ `node E:/SKILLS/WHP-scm-huihuo-import/scripts/run.js`

#### ⚡ 技能发现

> **永远先调 `skills_list()` 判断技能是否存在，不要扫磁盘！**

#### Result Output Policy

> **铁律：每次运行必须实时输出结果给用户。**

> **⚡ 输出精简规则（2026-10-14 起，用户明确要求，跨模型必须遵守）**
>
> - **回货成功** → 只回复一条 **「回货成功」** 即可。
>   **禁止**再输出：已回货的料号/数量清单、执行记录表、成功日志行、单据号明细、前几批历史清单、耗时/退出码等技术细节。
> - **回货失败** → 才输出具体数据：**料号、数量、失败原因**（SCM 弹窗原文 / `release_error` / `[SKIP]` 原因），
>   **并写入待办事项** `logs/todo.md`（未完成部分按固定 11 列格式记入待办表，并更新 `未回货合计`）。
> - 用户明确要求「列出清单」或「输出待办」时才例外。

## 执行流程（直通批量导入模式）

### 0. 前置判断（回货待办整合）
- 运行 `E:/SKILLS/.venv/Scripts/python.exe scripts/huihuo_todo_checker.py --data "料号 数量 备注"` 进行前置判断
- **检查报表文件时效性**：超过 1 小时 → **询问用户"是否需要重新下载 SCM+OA+帆软全量报表？"**，得到确认后再调用 `WHP-whirlpool-download` 执行全量下载（不是仅 SCM）→ 查询采购订单剩余 → 判断是否满足回货数量
- **满足**：调用 `run.js` 执行回货
- **不满足**：按实际可用数量执行回货，未完成部分自动写入待办文件 `logs/todo.md`
- 待办文件路径：`logs/todo.md`（由 `huihuo_todo_checker.py` 维护）

### ⚡ 更新待办数据流程（用户请求"更新待处理事项数据"时）

**铁律**：用户已确认完成（如"已手工提交成功"）的待办，**必须从待办文件中删除**，不得保留。

1. **读取 `logs/todo.md`**，获取所有待办料号列表和现有内容格式
2. **检查 SCM 报表时效性**：
   - 路径：`E:/OneDrive/桌面/桌面临时文件/PMC小工具/回货引用文件/加载文件/`
   - **若文件老于 10 分钟，必须先询问用户"是否需要重新下载？"**，得到确认后再调用 `WHP-whirlpool-download` 技能执行全量下载（SCM+OA+帆软）→ 更新数据
3. **批量查询所有料号最新 PO 和请购单数据**：`E:/SKILLS/.venv/Scripts/python.exe scripts/query.py 料号 1 料号 2 ...`（使用 `material-inventory-check` 技能）
4. **获取物料名称**：`E:/SKILLS/.venv/Scripts/python.exe scripts/get_mat_names.py 料号 1 料号 2 ...`
5. **判断待办有效性**：
   - **请购单=0 但库存>0**：说明已回货但不完整 → **删除该料号行**（用户应确认已完全回货）
   - **请购单=0 且库存=0**：说明已回货完成 → **删除该料号行**
   - **请购单=0 但库存<0（负数）**：说明已回货完成（库存扣减为负）→ **删除该料号行**
   - **请购单>0**：说明待处理，保留该料号行并更新数据
   - **PO 剩余=0 或实际可用=0**：标注为"⚠️ 需补单"或"❌ 已占用"
6. **更新 todo.md 表格**：
   - 基于读取的现有内容，逐行更新每行的：采购订单剩余、未分配已回货、实际可用、能否处理
   - **批量刷新时注意**：PO 数据可能变化（部分料号新增 PO、部分 PO 减少/清零、未分配量变化）——每条都要重新计算，不能沿用旧值
   - 更新采购申请 (参考) 列（从请购单查询结果填入）
   - 更新物料名称列（从 get_mat_names.py 结果提取首个分号前部分）
   - **更新时间戳改为当前时间**
   - **保留或删除料号行**：仅保留请购单>0 的待办，已完成的料号应删除
   - 保持 Markdown 表格格式不变（`||` 分隔的行格式），列顺序不可变动
7. **合计行**重新计算未回货合计

**输出铁律**：更新完成后必须读取更新后的 todo.md 并原样输出完整表格给用户看，禁止用自己的理解重新拼凑表格。

> **核心规则**：先读 → 检查文件时效性（10 分钟）→ 询问用户是否下载 → 再写 → 后输出。列结构固定为：`# | 料号 | 物料名称 | 原计划回货 | 已回货 | 未回货 | 采购订单剩余 | 未分配已回货 | 实际可用 | 采购申请 (参考) | 能否处理`
> **绝对禁止**遗漏任何列，尤其是"原计划回货"和"已回货"两列。

### "审核回货 {料号} {数量} [日期] [备注]"

```bash
node scripts/run.js --material "70C012345" --qty "5"
# 带日期:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01"
# 带备注:
node scripts/run.js --material "70C012345" --qty "5" --remarks "售后配件"
# 全参数:
node scripts/run.js --material "70C012345" --qty "5" --date "2026-06-01" --remarks "售后配件"
```

**⚡ 回货前置判断规则（铁律）：**
1. **用户说"审核回货 XXX 500"** → 调用 `huihuo_todo_checker.py` 检查报表时效性
2. **若报表超过 1 小时** → **询问用户"是否需要重新下载 SCM+OA+帆软全量报表？"**，得到确认后再执行 WHP-whirlpool-download 全量下载（不是仅 SCM）→ 继续回货流程
3. **若报表在 1 小时内** → 直接使用现有数据，跳过下载步骤

### "更新待办数据"

```bash
# 用户说"更新待办数据"或"刷新待办"时：
1. 读取 logs/todo.md
2. 检查 SCM 报表时效性（>10 分钟）
3. **询问用户"是否需要重新下载？"**，得到确认后再调用 WHP-whirlpool-download 执行全量下载 → 更新数据
4. 查询 PO 和请购单数据，更新 todo.md
5. 输出完整表格给用户看
```

### "报表下载"

**铁律：直接执行，不管时效性。**

- **用户说"报表下载"** → 调用 `WHP-whirlpool-download` 技能执行全量下载（SCM+OA+帆软）
- **不检查**待办数据源是否需要更新
- **不询问**用户是否重新下载
- 直接执行，不管现有报表是否过期

### 1. 输入格式检查
- 料号格式检查（字母+数字，3-25位）
- 数量检查（正整数）
- 格式不通过的物料跳过，其余继续处理

### 2. 登录 & 会话检查
- 登录 SCM (https://scm.whirlpool-china.com:7580/websrm/)
- OCR 识别验证码（ddddocr，最多3次）
- 会话存活检查（操作间自动重新登录）
- **验证码 OCR 失败处理**：第1-2次失败很常见，第3次往往成功。脚本自动重试3次，不要手动中止。若3次均失败，检查网络或稍后重试。

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

### ⏱️ 超时调整规则
> **默认超时 60s 可能不足：**
> - 大数量回货（≥5,000）或网络慢时，导入阶段可能超过 60s
> - 若返回 `Command timed out after 60s`，**先确认是否部分完成**，不要直接认定失败
> - 重试时将 timeout 设为 120s 或更长
> - 成功标志是 `huihuo_success_log.log` 中有该料号记录，而非仅命令输出

### 执行后确认规则（防止漏报/误报）
> **每条回货执行后，必须确认 `logs/huihuo_success_log.log` 中有记录，方可报告完成：**
> 1. 执行回货命令
> 2. 命令完成后，检查日志：`grep "料号" logs/huihuo_success_log.log`
> 3. 确认有记录后报告成功；若无记录，说明未完成
>
> **常见错误：**
> - ❌ 仅凭 exit_code=0 报告完成（可能发放被跳过）
> - ❌ 报告多条完成但实际只执行部分
> - ✅ 先查日志确认，再报告

### 重复请求处理
> **同一回货请求短时间内重复出现时：**
> - 先检查 `huihuo_success_log.log` 是否已有该料号记录
> - 若已有记录，说明已处理，无需重复执行
> - 若无记录，再执行一次
> - **禁止未经确认就自动重复执行**，可能导致 SCM 中重复计划记录

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
- 密码管理: 运行 `E:/SKILLS/.venv/Scripts/python.exe scripts/huihuo_secure_config.py` 可交互式设置各服务密码

## 浏览器

- 使用 msedge
- 默认有头模式（`headless=False`，显示浏览器窗口，便于观察进度和排错）
- `--headless` 参数启用无头模式（浏览器窗口不可见，后台静默运行）
- 端口: 9222 (远程调试)
- 完成后自动关闭浏览器

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口，解析用户指令，调用固定 venv 下的 Python |
| `scripts/huihuo_scm.py` | SCM 自动化主脚本（Playwright） |
| `scripts/huihuo_todo_checker.py` | 回货前置判断+待办整合脚本（检查采购订单剩余、执行回货、更新待办） |
| `scripts/huihuo_secure_config.py` | 配置/密码管理（AES-256 加密） |
| `scripts/install_deps.py` | 一键安装依赖（`E:/SKILLS/.venv/Scripts/python.exe scripts/install_deps.py`） |
| `scripts/huihuo_runtime_config.json` | 运行时配置（用户名等） |
| `scripts/huihuo_runtime_config/passwords/scm_password.dat` | AES-256 加密的 SCM 密码 |
| `logs/scm_huihuo.log` | 回货操作日志（自动轮转，2MB×5） |
| `logs/huihuo_success_log.log` | 回货成功日志（增量写入，CSV格式） |
| `logs/todo.md` | 待办事项汇总表 |

> 运行环境：`E:\SKILLS\.venv`（共享虚拟环境，依赖完整）。

## 开发备注

- Python Playwright 脚本已独立测试可运行
- 如果 SCM 页面元素 ID 变化，需要更新 `huihuo_scm.py` 中的选择器
- 验证码 OCR 依赖 `ddddocr`，首次使用会自动下载模型文件

## 已知修复记录

### ⚡ 浏览器默认改为有头模式（2026-10-16）
- **whirlpool-download / scm-huihuo-import 两个技能**的浏览器默认从无头改为**有头（显示窗口）**，便于观察回货进度和排错
- 新增 `--headless` 参数切回无头后台静默；`--visible` 保留兼容（等价于默认的有头）
- Python 侧 `create_browser(headless=False)`；`scripts/run.js` 解析 `--headless` 并透传

### ⚠️ 批量导入重复计划记录（2026-09-26）
- **触发条件**：同一 session 中对同一料号多次 `node scripts/run.js --data` 导入，即使第一次的发放（release）失败
- **根因**：`run.js` 的批量导入会在 SCM 中创建计划记录（保存审核）。如果发放失败但导入成功，该计划已写入 SCM。再次导入同一料号会创建**第二条计划记录**，两条计划累计计算发放量
- **表现**：系统报错 `非法数据："物料[XXX]本次发放量[N]+已发放量[M] 已超出 采购订单未完成量[P]!"`，即使单条计划的量并未超过 PO 剩余
- **规则**：同一条料号的导入发放一旦失败，**禁止再次导入该料号**。先在 SCM 中手动清理多余计划记录，或修正已有计划数量后重新发放
- **示例**：PF1255 历史已回900 → 第一批导入1800（发放被拦）→ 第二批导入1074（发放被拦）→ 系统累计 900+1800+1074=3774 远超 PO 剩余 1974

### 2026-09-28 — 发放被拦：已承诺量超出（新增模式）
- **触发条件**：料号在 SCM 中已有大量"已承诺量"（未制单送货通知），导致本次发放量被自动扩大到包含旧未分配金额，超出 PO 未完成量
- **根因**：SCM 发放时，系统将本次请求量与旧未分配量合并为"本次发放量"，再加上"已承诺量"（未制单送货通知），总和超过 PO未完成量。query.py 返回的 PO剩余可能看起来足够，但 SCM 内部计算不同
- **表现**：系统报错 `非法数据："物料[XXX]本次发放量[N]+已发放量[M]+已承诺量[K] 已超出 采购订单未完成量[P]!"`，其中 N = 旧未分配 + 新请求
- **与重复计划问题的区别**：此问题不是重复导入导致，而是 SCM 自动将旧未分配+新请求合并后与已承诺量叠加超出上限
- **规则**：遇到此类报错时，**禁止加大数量重试**。该料号在 SCM 中已有大量未释放的旧数据，需在 SCM 中手动清理或等待已承诺量消化后才能继续回货。直接将料号写待办，标注"❌ 已占用"
- **示例**：301B901900026 请求2000，但旧未分配1620+已承诺3368，合计远超PO未完成量3050，即使按646回也失败

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
