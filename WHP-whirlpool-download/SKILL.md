---
name: WHP-whirlpool-download
description: >
  Whirlpool China 统一报表下载工具 — 自动登录 SCM/OA/帆软三大系统，
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

- Python 3.11+（命令统一用 `py` 启动器，当前环境 `py` 与 `python` 均可用）
- Python 依赖:
  ```bash
  pip install playwright pandas openpyxl ddddocr cryptography lxml
  playwright install msedge
  ```
- Edge 浏览器已安装（版本 80+）
- 首次运行需先设置加密密码:
  ```bash
  py scripts/download_secure_config.py
  ```

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，必须通过 exec 的 `workdir` 参数传递工作目录。
> **命令中统一用 `py` 调用 Python 脚本**（当前环境 `py` 与 `python` 均可用，统一用启动器 `py`），禁止直接写 `python`。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js",
    "workdir": "E:\\SKILLS\\WHP-whirlpool-download",
    "timeout": 1200
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
py scripts/download_secure_config.py
```

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-whirlpool-download`
3. 命令体中禁止写 `cd ... && ...` 格式
4. 禁止在 command 中使用 `python`，必须用 `py`
5. 默认超时 1200s（20分钟），因 SCM+OA+帆软全流程较慢
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

3. **Phase 3: 帆软报表任务**（约10-30分钟）
   - 登录帆软报表系统
   - 下载4类报表：
     - 已发放工单推式料发料明细 → report1 目录
     - SCM转订单无效清单 → report2 目录
     - 库存报表 → stock 目录
     - BOM循环查询 → bom 目录（需 OA 计划.xlsx 物料编码）

### 单模块模式（`--module scm|oa|fanruan`）
- 只运行指定模块，跳过其他两个
- 适合只需某一系统数据的场景

## 配置文件

### download_runtime_config.json（首次运行自动创建）
位置：`E:\SKILLS\WHP-whirlpool-download\scripts\download_runtime_config.json`

### 密码加密存储
位置：`E:\SKILLS\WHP-whirlpool-download\scripts\download_runtime_config\passwords\`
- `scm_password.dat` — SCM 密码（AES-256 加密）
- `oa_password.dat` — OA 密码（AES-256 加密）
- `fanruan_password.dat` — 帆软密码（AES-256 加密）

### 下载目录配置
| 配置项 | 默认路径 | 说明 |
|---------|---------|------|
| `scm.dir_task1-5` | `E:\...\scm_task{1-5}` | SCM 各任务下载目录 |
| `fanruan.dir_bom` | `D:\360安全浏览器下载\bom` | BOM 循环查询目录 |
| `fanruan.dir_report1/2/stock` | `E:\...\report1/2/stock` | 帆软报表目录 |
| `oa.plan_dir` | `E:\...\oa_plan` | OA 计划文件目录 |

## 登录凭证

- SCM: https://scm.whirlpool-china.com:7580/websrm/ — 账号 hsa697，密码加密存储
- OA: https://oa.whirlpool-china.com — 账号 hsa697，密码加密存储
- 帆软: https://rpt.whirlpool-china.com:7027/decision — 账号 HSA697，密码加密存储

## 浏览器

- 使用 msedge（无头模式，默认不显示浏览器窗口；调试或手动输验证码时加 `--visible`）
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

## 异常处理

- 断点续传：单个任务失败不影响后续任务
- Cookie 过期时自动重新登录
- 验证码 OCR 3次失败后提示手动输入
- 所有异常记录到日志文件
- 日志位置：`scripts/logs/report_downloader.log`（单文件，每次执行覆盖，仅保留最近一次）

## 开发备注

- SCM模块已改用优化版逻辑（ExtJS API导航 + 齐射收网 + 网格直提）
- 原项目路径：`e:\whirlpool-china\`
- 技能路径：`E:\SKILLS\WHP-whirlpool-download\`
- 如果 SCM/OA/帆软页面元素变化，需更新 `unified_report_downloader.py` 中的选择器
