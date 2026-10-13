---
name: WHP-scm-received-inbound
description: >
  已接收入库导出工具 — 自动登录 SCM，打开送货单查询，设置查询条件
  （接收日期=当月1号~当月最后一天、接收状态=已接收、接收地址=M03、
  最大显示数=99999），导出「已入库.xlsx」。
  独立脚本，代码逻辑参考 WHP-whirlpool-download 技能的 unified_report_downloader.py。
  
  Trigger keywords: 已接收入库, 接收入库, 导出已入库, 跑已接收入库, 已接收送货单
  
  Usage examples:
  - "跑已接收入库"
  - "导出已接收送货单"
  - "下载已入库"
---

# 已接收入库导出

## 前置条件

- 统一使用仓库虚拟环境 `E:\SKILLS\.venv`（依赖已随 `E:\SKILLS\requirements.txt` 安装）
- 依赖验证：
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe -c "from playwright.sync_api import sync_playwright; print('ok')"
  ```
- Edge 浏览器已安装
- SCM 密码：沿用 `WHP-whirlpool-download` 技能的 `scm_password.dat`（AES-256 加密，无需重复设置）

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，必须通过 exec 的 `workdir` 参数传递工作目录。
> **Python 一律用仓库虚拟环境 `E:/SKILLS/.venv/Scripts/python.exe`**，禁止使用全局 `py` / `python`（版本可能不一致）。

### "跑已接收入库" / "导出已接收送货单" / "下载已入库"
```bash
node scripts/run.js            # 默认无头（后台静默），导出当月已接收送货单
node scripts/run.js --visible  # 可见模式（调试 / 手动输验证码）
node scripts/run.js --help     # 帮助
```
- workdir：`E:\SKILLS\WHP-scm-received-inbound`
- 超时：600s
- 验证码：OCR 自动识别（ddddocr），失败自动重试，不要手动中止

## 查询条件（脚本自动设置）

| 字段 | 值 |
|------|-----|
| incept_date_start / incept_date_end | 当月 1 号 ~ 当月最后一天 |
| received | 已接收 |
| organization_code | M03（`received_runtime_config.json` → `scm.org_code`） |
| maxsearchrltcmt | 99999 |

## 输出路径

- `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件\已入库.xlsx`
  （目录由 `scripts/received_runtime_config.json` → `scm.dir_export` 决定；文件名 `已入库.xlsx` 写死在 `scm_received_inbound.py`）

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口，固定调用共享 `.venv` 的 Python |
| `scripts/scm_received_inbound.py` | SCM 自动化主脚本（Playwright，默认无头） |
| `scripts/received_secure_config.py` | 配置 / 密码管理（AES-256 加密） |
| `scripts/install_deps.py` | 依赖安装与检查 |
| `scripts/received_runtime_config.json` | 运行时配置（用户名、组织、导出目录） |

## 异常处理

- 登录 / 查询 / 导出任一步失败即中止并打印原因；仅运行一次，不自动重试
- 若 SCM 弹出错误提示，脚本会把弹窗文本一并打印，便于定位失败原因
- 若 SCM 页面元素 ID 变化，需更新 `scripts/scm_received_inbound.py` 中的选择器
