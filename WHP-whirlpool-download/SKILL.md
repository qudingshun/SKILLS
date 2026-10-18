---
name: WHP-whirlpool-download
description: >
  Whirlpool China 统一报表下载工具 - 自动登录 SCM/OA/帆软三大系统，
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

- 统一使用仓库虚拟环境 `E:\SKILLS\.venv`（依赖已随 `E:\SKILLS\requirements.txt` 安装）
- 依赖安装/补齐:
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe -m pip install -r E:/SKILLS/requirements.txt
  E:/SKILLS/.venv/Scripts/python.exe -m playwright install msedge
  ```
- Edge 浏览器已安装（版本 80+）
- 首次运行需先设置加密密码:
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe scripts/download_secure_config.py
  ```

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
E:/SKILLS/.venv/Scripts/python.exe scripts/download_secure_config.py
```

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`E:\SKILLS\WHP-whirlpool-download`
3. 命令体中禁止写 `cd ... && ...` 格式
4. 禁止在 command 中使用全局 `py` / `python`，必须用 `E:/SKILLS/.venv/Scripts/python.exe`
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
| `fanruan.dir_bom` | `D:\360安全浏览器下载` | BOM 循环查询目录（103 个料号 xlsx 直接落在此目录，无 `\bom` 子目录） |
| `fanruan.dir_report1/2/stock` | `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` | 帆软报表目录（3 项指向同一目录） |
| `oa.plan_dir` | `E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件` | OA 计划.xlsx 目录 |

> 说明：`D:\360安全浏览器下载` 是 `download_secure_config.py` / `config_example.py` 里的默认值，现有运行时配置也用它，未加 `\bom` 子目录。

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
- Cookie 过期时自动重新登录
- 验证码：**整轮登录最多重试 3 次**（识别 → 填码 → 提交 → 校验是否真的登录成功），
  每次失败会自动关闭"验证码错误"弹窗并点击验证码图刷新，再试下一次；
  3 次均失败才提示手动输入——且**仅在交互终端**下提示，后台/管道运行没有 stdin，
  会直接判定失败退出（不会卡在 `input()`），并保存 `debug_scm_login.png` 现场截图。
- 所有异常记录到日志文件
- 日志位置：`scripts/logs/report_downloader.log`（单文件，每次执行覆盖，仅保留最近一次）

## 开发备注

- SCM模块已改用优化版逻辑（ExtJS API导航 + 齐射收网 + 网格直提）
- 原项目路径：`e:\whirlpool-china\`
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
