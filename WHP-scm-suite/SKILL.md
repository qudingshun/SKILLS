---
name: WHP-scm-suite
description: >-
  WHP 惠而浦系业务技能统一套件 —— 4 个模块的业务代码与配置中心。
  Trigger keywords: 回货, 已接收入库, 报表下载, 系统数据查询
metadata:
  openclaw:
    os: ["win32"]
    requires:
      bins: ["node", "msedge"]
---

# WHP-scm-suite（业务套件 / config 中心）

本套件收纳原 4 个独立业务技能的全部代码与配置：

| 模块   | 原技能                      | 主脚本                                   |
|--------|-----------------------------|------------------------------------------|
| huihuo | WHP-scm-huihuo-import       | `scripts/huihuo/huihuo_scm.py`          |
| received | WHP-scm-received-inbound  | `scripts/received/scm_received_inbound.py` |
| download | WHP-whirlpool-download    | `scripts/download/unified_report_downloader.py` |
| query  | WHP-system-data-query       | `scripts/query/system_data_query.py`     |

各外部技能（opencode / openclaw 薄封装）统一通过本套件入口调用：

```
node E:/SKILLS/WHP-scm-suite/scripts/run.js <模块> [参数]
```

## 模块用法

- **huihuo（回货导入 & 发放）**
  `node run.js huihuo --material 料号 --qty 数量 [--date 日期] [--remarks 备注] [--headless]`
  或 `node run.js huihuo --data "70C11099 2, ABC 3 紧急补货" [--headless]`
- **received（已接收入库导出）**
  `node run.js received [--headless]`
- **download（SCM/OA/帆软统一报表下载）**
  `node run.js download [--module scm|oa|fanruan] [--headless]`
- **query（系统数据查询：帆软库存 + SCM 五类）**
  `node run.js query --material 料号 [--module fanruan|scm|all] [--org 组织] [--bin 货位] [--headless]`

## 配置与密码（唯一来源）

- `runtime_config.json`（套件根）：`scm` / `oa` / `fanruan` 段的用户名、org_code、
  audit_date、shipment_date_start、导出目录 dir_task1-5 / dir_export / dir_bom / plan_dir 等。
- `runtime_config/passwords/*.dat`：AES-256 加密密码库（SCM/OA/帆软）。
  `SecurePasswordManager` 由配置路径自动推导密码目录，`wh_core/secure_config.py` 为唯一实现。
- 共享虚拟环境：`E:\SKILLS\.venv\Scripts\python.exe`（run.js 自动定位）。

## 共享核心（scripts/wh_core）

- `wh_core/secure_config.py`：`ConfigManager` + `SecurePasswordManager`（4 模块共用）
- `wh_core/whirlpool_common.py`：`create_browser`/`safe_print`/`Stopwatch`/状态存储/
  `is_headless`/`decode_local_password`/`check_dependencies`
- 各主脚本自带引导块：`SUITE_DIR` 计算 → 把套件 `scripts` 目录加入 `sys.path` →
  `from wh_core.* import ...` → `ConfigManager(CONFIG_PATH)`。

## 维护注意

- 改代码后必须跑 `compileall` 并回归对应模块。
- 密码新增服务：在套件根运行 `python scripts/wh_core/secure_config.py`。
- 版本号：随功能更新同步提升（当前 1.0.0）。