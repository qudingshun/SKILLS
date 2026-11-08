---
name: WHP-whirlpool-download
description: >
  Whirlpool China 统一报表下载工具 - 直接执行（不管上次下载时间），一次性下载 SCM+OA+帆软全量报表
  按 SCM→OA→帆软顺序执行全部报表下载任务。
  
  SCM模块使用优化版逻辑（ExtJS API导航 + 齐射收网 + 网格直提），
  OA模块抓取生产计划生成计划.xlsx，帆软模块下载 report1/2/stock + BOM循环查询。
  
  所有密码 AES-256 加密存储，Cookie 持久化免重复登录。
  
  Trigger keywords: 报表下载, 下载报表, whirlpool下载, SCM下载, 帆软下载,
  OA下载, 统一下载, 下载工具, 帮我下载报表, 下载送货通知, 下载PO未结量
  
  Usage examples:
  - "帮我下载报表"
  - "下载SCM送货通知"
  - "运行报表下载工具"
  - "下载全部报表"
  - "只下载SCM报表"
---

# Whirlpool China 统一报表下载工具

## 前置条件

- 统一使用仓库虚拟环境 E:\SKILLS\.venv（依赖已随 E:\SKILLS
equirements.txt 安装）
- **关键依赖检查**：执行前必须确认以下模块可用，缺失时自动安装：
  ```bash
  # 检查 pandas（帆软报表解析必需）
  E:/SKILLS/.venv/Scripts/python.exe -c "import pandas; print('pandas OK')" || \
    E:/SKILLS/.venv/Scripts/python.exe -m pip install pandas --index-url https://pypi.tuna.tsinghua.edu.cn/simple
  
  # 检查 openpyxl（xlsx 解析必需）
  E:/SKILLS/.venv/Scripts/python.exe -c "import openpyxl; print('openpyxl OK')" || \
    E:/SKILLS/.venv/Scripts/python.exe -m pip install openpyxl --index-url https://pypi.tuna.tsinghua.edu.cn/simple
  
  # 检查 lxml（HTML/XML 解析必需）
  E:/SKILLS/.venv/Scripts/python.exe -c "import lxml; print('lxml OK')" || \
    E:/SKILLS/.venv/Scripts/python.exe -m pip install lxml --index-url https://pypi.tuna.tsinghua.edu.cn/simple
  
  # 检查 playwright（浏览器自动化必需）
  E:/SKILLS/.venv/Scripts/python.exe -c "from playwright.sync_api import sync_playwright; print('playwright OK')" || \
    E:/SKILLS/.venv/Scripts/python.exe -m pip install playwright --index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    E:/SKILLS/.venv/Scripts/python.exe -m playwright install msedge
  ```
- Edge 浏览器已安装（版本 80+）
- 首次运行需先设置加密密码:
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe scripts/download_secure_config.py
  ```

## 执行前依赖验证

**铁律**：在调用 unified_report_downloader.py 之前，必须先执行上述依赖检查。如果任何关键模块缺失，必须安装后再重试。**禁止跳过此步骤直接运行脚本**。

> **Pitfall**：帆软报表导出为 xlsx 格式，需要 pandas+openpyxl 解析；SCM/OA 页面交互需要 playwright。任一缺失都会导致 ModuleNotFoundError，且错误信息不清晰（只报第一个缺失的模块）。必须按顺序检查并安装所有依赖。
## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，必须通过 exec 的 `workdir` 参数传递工作目录。
> **命令中统一用仓库虚拟环境 `E:/SKILLS/.venv/Scripts/python.exe` 调用 Python 脚本**，禁止使用全局 `py` / `python`（版本可能不一致）。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js",
    "workdir": "E:\\SKILLS\\WHP-whirlpool-download",
    "timeout": 2400
  }
}
```

### "帮我下载报表" / "下载全部报表"
```bash
node scripts/run.js
```

### "只下载SCM报表"
```bash
node scripts/run.js --module scm
```

### "只下载OA计划"
```bash
node scripts/run.js --module oa
```

### "只下载帆软报表"
```bash
node scripts/run.js --module fanruan
```

### "设置密码"
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/download_secure_config.py
```

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-whirlpool-download`
3. 命令体中禁止写 `cd ... && ...` 格式
4. 禁止在 command 中使用全局 `py` / `python`，必须用 `E:/SKILLS/.venv/Scripts/python.exe`
5. 默认超时 2400s（40分钟），因 SCM+OA+帆软全流程较慢（SCM 单阶段就可能 15+ 分钟）
6. 启动后必须用 `process(poll)` 等待完成后，读取 `scripts/logs/report_downloader.log` 获取执行结果再汇报（单文件，每次执行覆盖）

## 执行流程

### 全量模式（默认）：SCM → OA → 帆软

1. **Phase 1: SCM 系统任务**（约5-15分钟）
   - 登录 SCM（验证码 OCR 自动识别，3次失败手动输入）
   - Cookie恢复/保存机制
   - 齐射收网：Phase1 提交全部查询(skip_wait) → Phase2 逐个收集结果
   - 5个任务：
     - 送货通知查询 → scm_task1 目录
     - 送货单查询 → scm_task2 目录
     - PO未结量汇总 → scm_task3 目录
     - 回货计划发放 → scm_task4 目录
     - 请购单查询 → scm_task5 目录

2. **Phase 2: OA 系统任务**（约2-5分钟）
   - 登录 OA
   - 抓取当前月和次月生产计划
   - 生成 计划.xlsx → oa_plan 目录
   - ⚠️ 每次执行都**强制重新抓取**：不校验 `计划.xlsx` 的时间新鲜度（哪怕 1 分钟前刚下载过也重新下载）

3. **Phase 3: 帆软报表任务**（约10-30分钟）
   - 登录帆软报表系统
   - 下载4类报表：
     - 已发放工单推式料发料明细 → report1 目录
     - SCM转订单无效清单 → report2 目录
     - 库存报表 → stock 目录
     - BOM循环查询 → `D:\360安全浏览器下载`（需 OA 计划.xlsx 物料编码）

### 单模块模式（`--module scm|oa|fanruan`）
- 只运行指定模块，跳过其他两个
- 适合只需某一系统数据的场景

## 配置文件

### download_runtime_config.json（首次运行自动创建）
位置：`E:\SKILLS\WHP-whirlpool-download\scripts\download_runtime_config.json`

### 密码加密存储
位置：`E:\SKILLS\WHP-whirlpool-download\scripts\download_runtime_config\passwords\`
- `scm_password.dat` - SCM 密码（AES-256 加密）
- `oa_password.dat` - OA 密码（AES-256 加密）
- `fanruan_password.dat` - 帆软密码（AES-256 加密）

### 下载目录配置
当前实际值（来自 `scripts/download_runtime_config.json`）：

| 配置项 | 实际路径 | 说明 |
|---------|---------|------|
| `scm.dir_task1-5` | `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` | SCM 5 个任务的导出目录（5 项指向同一目录） |
| `fanruan.dir_bom` | `D:\360安全浏览器下载` | BOM 循环查询目录（100+ 个料号 xlsx 直接落在此目录，无 `\bom` 子目录；数量随 BOM 清单变化） |
| `fanruan.dir_report1/2/stock` | `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` | 帆软报表目录（3 项指向同一目录） |
| `oa.plan_dir` | `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` | OA 计划.xlsx 目录 |

> 说明：`D:\360安全浏览器下载` 是 `download_secure_config.py` / `config_example.py` 里的默认值，现有运行时配置也用它，未加 `\bom` 子目录。

### ⚠️ 路径漂移踩坑（2026-10-23）

`download_runtime_config.json` 被外部改动过（18:26:48），把 `scm.dir_*` / `fanruan.dir_*` / `oa.plan_dir` 指到 `桌面\PMC 小工具`、`dir_bom` 指到 `D:\360 安全浏览器下载`，与其余工具不一致，形成两棵各自独立的目录树。

**根因**：本技能是报表下载的唯一写入方，但读方分散在多个技能，路径各自硬编码：

| 路径使用方 | 读写 |
|---|---|
| WHP-whirlpool-download（SCM 5 份 / 帆软 3 份 / 计划.xlsx / BOM 106 个） | **写** |
| WHP-scm-huihuo-import（回货）/ material-inventory-check（查料号）/ WHP-scm-received-inbound（已入库）/ bom-compare | **读** |

读方一律用 `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` 和 `D:\360安全浏览器下载`（无空格）。

**后果**：报表下载写进新树后，查料号 / 回货前置判断读到的是旧树里几小时前的 PO 剩余与已回货未分配，会算错「实际可用」。

**预防**：改动本技能任一目录配置前，先确认与上表读方一致；每次下载后核对文件落地目录是否等于 `download_runtime_config.json` 的值，而不是只看「成功 N」。

### ✅ 路径统一复查（2026-10-29）

10-27 13:23 该配置再次被改，6 处指向 `桌面前期文件`（`scm.dir_task3` / `scm.dir_task5` /
`fanruan.dir_report1` / `dir_report2` / `dir_stock` / `oa.plan_dir`），
而 `scm.dir_task1/2/4` 仍在 `桌面临时文件`，形成「3 份落临时、6 份落前期」的劈叉。
下游读方（15 处硬编码）与本技能 `download_secure_config.py`、`config_example.py` 的模板**全部**指向 `桌面临时文件`。
已于 2026-10-29 全部改回 `桌面临时文件`，配置文件与上表恢复一致。

**验证方法**：改完配置必须用 `ConfigManager` 真加载一次，不要肉眼看 JSON：

```bash
# workdir = E:/SKILLS/WHP-whirlpool-download/scripts
E:/SKILLS/.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'.');from download_secure_config import ConfigManager;print(ConfigManager().configs)"
```

`workdir` 必须是 `scripts`：`run.js` 以 `cwd=scripts/` 启动 Python，`ConfigManager()` 收的是**相对路径**
`download_runtime_config.json`，解析到 `scripts/download_runtime_config.json`。

**同名空配置陷阱**：技能根目录曾有一个同名 `download_runtime_config.json`（内容为空，仅 3 字节 UTF-8 BOM），
不被任何代码读取，纯属误导性残留，2026-10-29 已删除。

**下载后验活别用 openpyxl read_only（2026-10-26）**：帆软导出的 xlsx（report1/report2/stock/BOM）`sheet dimension` 元数据可能是坏的——`read_only=True` 下 `calculate_dimension()` 返回 `A1:A1`、`max_row=1`、逐行迭代也只吐 1 行，但文件有 1-2.6MB、实际 2 万+ 行。**必须用 `load_workbook()`（不加 read_only）** 再读 `ws.dimensions` / 非空行数，否则会误判成「下载到空文件」而白重跑一轮。SCM 5 份与 OA 计划.xlsx 的维度元数据正常，不受影响。

### ⚠️ 单次执行硬超时（2026-10-29 修复）

**原值 20 分钟会中途杀进程**：`scripts/run.js` 的 `execSync` 原本是 `timeout: 1200000` ms（20 分钟），
而 SCM 单阶段就可能 15+ 分钟，SCM→OA→帆软三阶段串行经常超过 20 分钟。
超时后 Node 对 Python 发 SIGTERM，**`finally` 块不执行**，表现为：

- 日志只写到 `OA: 成功` 就断，**没有** `帆软: 成功N, 失败M` 和 `全部完成` 行
- `D:\360安全浏览器下载` 只多出前 1~2 个料号，其余仍是上一轮的文件
- 但帆软 3 份报表（report1/report2/stock）其实已经落盘

**已改**：`timeout` 提到 `2400000` ms（40 分钟），控制台超时提示同步改为「脚本超时 (40分钟)」；
SKILL.md 里的 exec 调用也统一用 `"timeout": 2400`。

**判据**：日志末行时间 **早于** 产物文件最后修改时间，且缺 `全部完成` → 判定为超时/被杀中断，不是下载失败。

**未迁移的历史数据（2026-10-29 决定）**：当天落在 `桌面前期文件` 的 6 个文件（请购单查询、采购订单未结量、计划.xlsx、
库存报表、已发放工单推式料发料明细、SCM-转订单无效清单）**保留不迁移**，等下一次全量重跑自然覆盖到正确目录。
在此之前，读方查 `桌面临时文件` 会缺这 6 份（或读到更旧的版本），不要误判成下载失败。
`D:\360安全浏览器下载` 当时也是混批（104 个 12:22–12:24 的旧文件 + 1 个 12:33:56 的新文件），同样等重跑刷新。

## 登录凭证

- SCM: https://scm.whirlpool-china.com:7580/websrm/ - 账号 hsa697，密码加密存储
- OA: https://oa.whirlpool-china.com - 账号 hsa697，密码加密存储
- 帆软: https://rpt.whirlpool-china.com:7027/decision - 账号 HSA697，密码加密存储

## 浏览器

- 使用 msedge（**默认有头模式，显示浏览器窗口**；后台静默运行时加 `--headless`）
- 每个系统共享同一浏览器实例
- Cookie 持久化，下次运行无需重新登录（12小时内有效）
- 完成后自动关闭浏览器

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口，解析用户指令并调用 Python |
| `scripts/unified_report_downloader.py` | Python 主程序（SCM+OA+帆软统一下载） |
| `scripts/whirlpool_common.py` | 公共模块（浏览器创建、日志、密码编解码） |
| `scripts/download_secure_config.py` | 安全配置（AES-256加密密码设置/管理） |
| `scripts/config_example.py` | 配置模板（首次运行参考） |
| `scripts/test_login_retry.py` | SCM 登录重试逻辑的离线桩测试（不联网，退出码 0=通过） |

## 异常处理

- **退出码语义（2026-10-10 修复）**：
  - 全流程成功 → 退出码 `0`，日志写「全部完成，总用时：…」
  - 任一模块/任务失败、或异常中止 → 退出码 `1`，控制台打印 `[FAIL] 执行失败，未完成：<原因>`，日志写「执行失败（未完成）：<原因>，总用时：…」
  - ⚠️ **禁止只凭退出码判定成功**（早期版本整体失败也返回 0）：必须核对日志中 `SCM: 成功N, 失败M` / `OA: …` / `帆软: 成功N, 失败M` 三行摘要
- 断点续传：单个任务失败不影响后续任务
- **网格等待判据（2026-10-22 修复）**：`_tab_wait_grid()` 不再"10 秒没数据就放弃"。
  只要页面仍处于读取状态（存在可见 `x-mask` 蒙层，或页面文本含 `读取中`/`加载中`），
  就会一直等到该页签的 timeout（请购单 180s、其余 120s）。
  根因：请购单查询偶发服务端长查询，页面显示"读取中…"，原逻辑 10 秒即判 `网格无有效数据` 并跳过导出，
  导致 `请购单查询.xlsx` 连续多轮下载失败（文件停留在上一轮）。
- **DOM 兜底只取活动页签（2026-10-22 修复）**：`EXTRACT_GRID` 的 DOM 兜底原先用
  `document.querySelector('.x-grid-view')`，会抓到其他页签/组织弹窗的空网格（返回 2 行 2 列的假数据）。
  改为优先在当前活动页签的 DOM 内查找，找不到才退回整页。
- Cookie 过期时自动重新登录
- 验证码：**整轮登录最多重试 3 次**（识别 → 填码 → 提交 → 校验是否真的登录成功），
  每次失败会自动关闭"验证码错误"弹窗并点击验证码图刷新，再试下一次；
  3 次均失败才提示手动输入——且**仅在交互终端**下提示，后台/管道运行没有 stdin，
  会直接判定失败退出（不会卡在 `input()`），并保存 `debug_scm_login.png` 现场截图。
- 所有异常记录到日志文件
- 日志位置：`scripts/logs/report_downloader.log`（单文件，每次执行覆盖，仅保留最近一次）

## 开发备注

- SCM模块已改用优化版逻辑（ExtJS API导航 + 齐射收网 + 网格直提）
- 原项目路径：`e:\whirlpool-china\`（**已废弃，勿再引用**，见 `E:\whirlpool-china\DEPRECATED.md`）
- 技能路径：`E:\SKILLS\WHP-whirlpool-download\`
- 如果 SCM/OA/帆软页面元素变化，需更新 `unified_report_downloader.py` 中的选择器
- **各页签的"组织"字段名不一致（易踩坑，2026-10-15 修复）**：
  - 送货通知查询 / 请购单查询 → `sap_org_code`
  - 送货单查询 / PO未结量汇总查询 → `organization_code`
  - `_tab_org_search()` 接受**候选列表**并按顺序探测第一个存在的字段：把该页签真实字段名放首位；
    顺序放错不会导致功能失败（会自动回退到下一个候选），只是多一次无效探测。
    仅当**全部候选都不中**时才打印一条 `[FAIL] 未找到组织字段（候选: ...）`，
    回退命中时会打印 `[OK] 组织字段回退命中: <name>` 作为页面变更预警。
    旧实现在候选循环里逐个打印 `[FAIL] 触发 xxx 搜索失败`，会误报成"筛选器失效"，已移除。
