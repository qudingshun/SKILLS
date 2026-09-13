# Reporting Tools Skill (reporting-tools)

## 核心功能描述
本技能负责执行业务端的两个自动化任务：生成产销存日报和跑回货工具。不处理原始数据拉取（OA/SCM/帆软），只执行业务流程层面的 Excel 宏操作和报表生成。

## 功能模块

### 1. 产销存报表
- 打开 `E:\OneDrive\桌面\生产情况日报\成品库存.xlsx`
- 加载 `代码库.xlam` 加载项
- 执行"产量出货更新"宏（后台不可见）
- 另存为 `成品库存yyyy-mm-dd.xlsx`
- 读取"汇总"Sheet，输出格式化产销存数据

### 2. 跑回货工具
- 打开 `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货工具.xlsm`
- 后台执行 `model1.yijian` 宏
- 另存为 `回货工具yy.m.d.xlsm`

## 触发词
| 触发词 | 功能 |
|--------|------|
| 跑回货工具 | 运行回货工具宏，另存新文件 |
| 产销存报表 | 更新产销存日报，输出汇总数据 |

## 执行策略
1. **优先**尝试转译版脚本（`transpiled_inventory.py` / `transpiled_run_excel.py`）
2. **失败回退**到外部原始脚本（`E:\whirlpool-china\inventory_daily_report.py` / `run_excel.py`）

## 依赖
- Windows Excel + VBA 宏
- `win32com` / `openpyxl` / `pythoncom` Python 包
- 源文件路径：
  - `E:\OneDrive\桌面\生产情况日报\成品库存.xlsx`
  - `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货工具.xlsm`
  - `E:\OneDrive\工作\9、VBA程序\回货引用文件\代码库\代码库.xlam`

## 💾 操作经验总结 (Memory Integration)

### 功能及触发词
| 触发词 | 功能 |
|--------|------|
| 产销存报表 | 打开成品库存.xlsx，执行宏更新数据，输出格式化产销存数据 |
| 跑回货工具 | 打开回货工具.xlsm，执行 model1.yijian 宏，另存新文件 |

### 执行策略
1. **优先**执行转译版脚本（`transpiled_inventory.py` / `transpiled_run_excel.py`）
2. 失败则回退到外部原始脚本（`E:\whirlpool-china\inventory_daily_report.py` / `run_excel.py`）

### 依赖文件
- `E:\OneDrive\桌面\生产情况日报\成品库存.xlsx`
- `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货工具.xlsm`
- `E:\OneDrive\工作\9、VBA程序\回货引用文件\代码库\代码库.xlam`

### Excel 实例管理（重要）
- 脚本启动前需用 `GetActiveObject` 检测 Excel 是否已在运行
- **已运行** → 只关自己打开的 workbook，不调 `Quit()`
- **未运行** → 正常 `Quit()` 关闭
- 必须加 `pythoncom.CoInitialize()` 确保 COM 线程安全
- 此策略避免跑宏时误关用户正在用的 Excel 窗口

### 已知修复记录
- **2026-05-25**：`inventory_daily_report.py` / `run_excel.py` 不再强制关闭已有 Excel 实例。加 `GetActiveObject` 检测 + `pythoncom.CoInitialize()`
