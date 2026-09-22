# 📋 成品库存日报生成工具 (inventory_daily.py)

> **版本：v1.0.2** ｜ **更新日期：2026-09-07**

## 📖 简介

`inventory_daily.py` 是一个自动化脚本，用于生成**成品库存日报**。它自动打开 Excel、执行 VBA 宏刷新数据与透视表，从"汇总" Sheet 提取关键指标，并最终输出格式化的日报摘要。

> 说明：本脚本为精简版主程序，执行 **VBA 宏 + 读取汇总 + 另存** 全流程；邮件下载功能在旧版 `inventory_daily_report.py`（含 DownMail 模块）中提供。

---

## 🎯 核心功能

| # | 模块 | 说明 |
|---|------|------|
| 1️⃣ | VBA 宏执行 | 运行 `产量出货更新` 宏，刷新数据 |
| 2️⃣ | 透视表刷新 | `RefreshAll()` + 等待异步查询完成 |
| 3️⃣ | Excel COM 读取 | 从"汇总" Sheet 提取关键指标 |
| 4️⃣ | 文件另存 | 自动生成带日期的新文件（防冲突，自动加序号） |
| 5️⃣ | 文本输出 | 格式化输出日报摘要 |

---

## 📂 项目结构

```text
E:\getBOM\Inventory Daily Report\
├── inventory_daily.py          ← 主程序入口（本工具）
├── inventory_daily.md          ← 本文件
├── inventory_daily_report.py   ← 旧版脚本（含邮件下载，保留备份）
├── openclaw_skill.py           ← OpenClaw 技能入口
├── openclaw.json               ← OpenClaw 技能配置
├── README.md / SKILL.md        ← 技能与项目说明
└── DownMail/                   ← IMAP 邮件下载模块（旧版使用）
```

---

## ⚙️ 依赖环境

| 模块 | 安装命令 | 用途 |
|------|----------|------|
| `pywin32` | `pip install pywin32` | Excel COM 自动化（必需，含 win32com） |

> 🔒 **不会干扰你正在运行的 Excel**：脚本使用 `DispatchEx("Excel.Application")` 创建**独立**的 Excel 实例，绝不附加/复用你已打开的 Excel，也不会隐藏或关闭你的窗口和工作簿。

---

## 🚀 快速开始

### 1. 安装依赖

```powershell
pip install pywin32
```

### 2. 准备 Excel 文件

确保以下文件存在且权限正确：

| 文件名 | 路径 | 说明 |
|--------|------|------|
| `成品库存.xlsx` | `E:\OneDrive\桌面\生产情况日报\` | 含"汇总" Sheet 与数据源表 |
| `代码库.xlam` | `E:\OneDrive\工作\9、VBA程序\回货引用文件\代码库\` | VBA 加载项（含"产量出货更新"宏） |

> ⚠️ 注意：加载项路径为 `9、VBA程序`（**无空格**）。

### 3. 手动执行测试

```powershell
cd "E:\getBOM\Inventory Daily Report"
py inventory_daily.py
```

**预期输出（本次实测）：**

```text
==================================================
inventory_daily.py -- 成品库存日报生成工具
   版本：v1.0.1 (2026-09-07)
   日期：2026-09-07

[Step 1] 打开成品库存.xlsx，执行 VBA 宏...
   [1a] 加载加载项：代码库.xlam ...
   [1b] 打开主文件：成品库存.xlsx ...
   [1c] 执行宏：产量出货更新 ...
   [1d] 刷新透视表 (RefreshAll) ...
   [OK] VBA 宏执行完成，透视表已刷新

[Step 2] 读取'汇总' Sheet 数据...
   本月计划=51406 | 已完成下线=9976 | 完成占比=19.4%
   期初库存=32086 | 装柜=21927台(141柜) | 当前库存=20135

[Step 3] 另存为新文件...
   [OK] 已保存：E:\OneDrive\桌面\生产情况日报\成品库存2026-09-07.xlsx

「截至2026-09-06日，本月当前计划数量 51,406 台，
已完成下线 9,976 台，完成占比 19.4%，
期初库存 32,086 台，装柜 21,927 台（141 柜），
当前库存 20,135 台。」
```

---

## 📊 报表格式说明

报告日期取**昨日**（`date.today() - 1`），例如 2026-09-07 运行则显示"截至2026-09-06日"。

| 字段 | 含义 | 示例 |
|------|------|------|
| 本月计划 | 本月计划产量（台） | 51,406 |
| 已完成下线 | 已完成下线数量（台） | 9,976 |
| 完成占比 | 已完成 / 本月计划 | 19.4% |
| 期初库存 | 期初库存（台） | 32,086 |
| 装柜 | 已装柜数量（台） | 21,927 台（141 柜） |
| 当前库存 | 当前库存（台） | 20,135 |

---

## 📍 数据坐标说明（重要）

数据来自 `成品库存.xlsx` 的 **"汇总"** Sheet（若无此名则回退到第 1 个工作表）。

> ⚠️ 旧文档曾误记为 A2~G2 单行格式，**实际结构不同**。合计数据位于 **第 22~24 行**：

| 单元格 | 含义 |
|--------|------|
| `E22` | 本月计划 |
| `F22` | 已完成下线 |
| `F23` | 完成占比（小数，如 0.194 = 19.4%） |
| `B23` | 期初库存 |
| `B24` | 装柜数量（台） |
| `C24` | 装柜数（柜） |
| `C22` | 当前库存 |

如需修改坐标，调整 `inventory_daily.py` 的 **Step 2 区块**：

```python
plan_qty      = get_cell_value(summary_sheet.Range("E22"))   # 本月计划
done          = get_cell_value(summary_sheet.Range("F22"))   # 已完成下线
begin_stock   = get_cell_value(summary_sheet.Range("B23"))   # 期初库存
con_qty       = get_cell_value(summary_sheet.Range("B24"))   # 装柜数量（台）
container_cnt = get_cell_value(summary_sheet.Range("C24"))   # 装柜数（柜）
cur_stock     = get_cell_value(summary_sheet.Range("C22"))   # 当前库存
ratio         = summary_sheet.Range("F23").Value             # 完成占比
```

---

## 🔍 VBA 宏要求（`产量出货更新`）

宏需在 `代码库.xlam` 加载项中，作用为：读取"生产计划表/发货记录表"数据 → 更新透视表 → 将合计写入"汇总" Sheet 的第 22~24 行单元格。

> 说明：旧文档中的 `刷新_数据(bool)` 仅为示意，实际调用无参数的 `产量出货更新` 宏。

---

## 🛠️ 故障排查

### ❌ `UnicodeEncodeError: 'gbk' codec can't encode`

```
原因：Windows 终端默认 GBK，脚本内 print 含 Unicode 字符
解决：脚本已内置 sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

### ❌ `AttributeError: module 'win32com.gen_py...' has no attribute 'CLSIDToClassMap'`

```
原因：win32com gen_py 缓存损坏（通常因 Excel 版本或中断导致）
解决：删除缓存目录后重试：
  Remove-Item -Recurse -Force "$env:TEMP\gen_py"
脚本使用 gencache.EnsureDispatch("Excel.Application") 自动重建
```

### ❌ Excel COM 找不到加载项 / 文件路径

```
原因：路径写错（如 "9、VBA 程序" 多了空格）
解决：确认加载项实际路径为 E:\OneDrive\工作\9、VBA程序\回货引用文件\代码库\代码库.xlam
```

### ❌ 读取汇总数据全为 0

```
原因：读取坐标与"汇总" Sheet 布局不符，或数据在第 22~24 行（非第 2 行）
解决：核对上表坐标；若 Excel 布局变动，调整 Step 2 的 Range 坐标
```

---

## 🧪 测试检查清单

| # | 检查项 | 预期结果 |
|---|--------|----------|
| 1️⃣ | `pip install pywin32` 是否成功？ | ✅ pip list 可见 `pywin32-xxx` |
| 2️⃣ | `py -c "import win32com.client; print('OK')"` | ✅ 输出 OK |
| 3️⃣ | Excel COM 能否正常创建？ | ✅ 不报错 |
| 4️⃣ | VBA 宏"产量出货更新"可被执行？ | ✅ 无红色错误 |
| 5️⃣ | "汇总" Sheet 第22~24行读取为数值？ | ✅ 计划/下线/库存均为非 0 |

---

## 📝 运行方式

### 方式 A：直接运行（本地测试）

```powershell
cd "E:\getBOM\Inventory Daily Report"
py inventory_daily.py
```

### 方式 B：OpenClaw 技能调用

通过 `openclaw_skill.py` 入口调用（参见 `SKILL.md`）。

---

## 📅 维护记录

| 日期 | 变更内容 | 版本 |
|------|----------|------|
| 2026-09-07 | 规避干扰：改用 `DispatchEx` 创建独立 Excel 实例，不复用/影响用户已运行的 Excel | v1.0.2 |
| 2026-09-07 | 修正坐标：改为"汇总"Sheet 第22~24行（E22/F22/F23/B23/B24/C24/C22） | v1.0.1 |
| 2026-09-07 | 初始版本，修复 win32com 导入与 GBK 编码错误 | v1.0.0 |

---

*文档生成时间：2026-09-07*  
*作者：OpenClaw Assistant*
