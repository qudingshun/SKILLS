---
name: bom-compare
description: >
  BOM核对 — 打开 Excel 运行核对BOM2宏，读取 Sheet1 (2) 结果，并过滤掉 C 列=无差异 的行。
  Trigger keywords: BOM核对, 核对BOM
---

# BOM Compare Skill (bom-compare)

## 核心功能描述
本技能用于 BOM 核对自动化。打开 `E:\OneDrive\桌面\桌面临时文件\PMC小工具\BOM核对.xlsm`，
后台运行宏 `核对BOM2`，保存后读取 `Sheet1 (2)` 前 7 列结果，并过滤掉 C 列为 `无差异` 的行。
不会关闭用户已打开的其他 Excel 文件。

## 触发词
| 触发词 | 功能 |
|--------|------|
| BOM核对 | 打开 BOM核对.xlsm，执行宏，返回差异结果 |
| 核对BOM | 同上 |

## 执行策略
1. **启动前**通过 `GetActiveObject` 检测 Excel 是否已在运行
   - **已运行** → 只关闭本次脚本打开的 workbook，不调 `Quit()`，不影响用户其他 Excel 文件
   - **未运行** → 正常 `Quit()` 关闭，避免遗留 Excel 进程
2. **进程清理**：异常时也通过统一清理函数关闭 workbook / quit Excel / release COM 引用 / `CoUninitialize`
3. **只输出差异行**：C 列值为 `无差异` 的行直接过滤，其余全部输出
4. **单次执行**：失败直接报错退出，不重试，避免数据部分写入后重复执行造成不一致

## 依赖
- Windows Excel + VBA 宏
- `win32com` / `pythoncom` Python 包
- 源文件路径：`E:\OneDrive\桌面\桌面临时文件\PMC小工具\BOM核对.xlsm`

## 脚本列表
| 文件 | 说明 |
|------|------|
| `scripts/run_bom_compare.py` | BOM 核对核心脚本（win32com 控制 Excel） |
| `openclaw_skill.py` | OpenClaw 技能入口 |
| `openclaw.json` | 技能注册配置 |

## 执行方式
```bash
python openclaw_skill.py
# 或带参数显示 Excel 窗口
python openclaw_skill.py --visible
```

## 异常处理
- **Excel COM 初始化失败**：提示 Excel 是否安装且用户可正常启动
- **错误 429 / 创建实例失败**：提示 32 位 Python 与 64 位 Excel 不兼容，或 Excel 未正确安装
- **0x800A03EC**：文件被占用或路径不可访问
- **宏执行超时**：提示超时并建议检查宏是否卡死
- **已有 Excel 实例被影响**：本技能已通过实例级管理避免关闭用户其他打开文件

## 💾 操作经验总结 (Memory Integration)
### 功能及触发词
| 触发词 | 功能 |
|--------|------|
| BOM核对 | 打开 BOM核对.xlsm，执行核对BOM2宏，返回差异结果 |
| 核对BOM | 同上 |

### Excel 实例管理（重要）
- 脚本启动前检测 Excel 是否已在运行
- **已运行** → 只关自己打开的 workbook，不调 `Quit()`
- **未运行** → 正常 `Quit()` 关闭
- 加 `pythoncom.CoInitialize()` / `CoUninitialize()` 确保 COM 线程安全
- 异常时统一清理，避免遗留 Excel 进程

### 输出规则
- 只输出 C 列不是 `无差异` 的行
- 其余内容全部输出，不做进一步截断，最多打印前 20 行预览

### 已知修复记录
- **2026-07-23**：改为过滤 C 列=无差异 的行；增加 Excel 实例隔离管理；增加常见环境错误提示与异常清理逻辑
