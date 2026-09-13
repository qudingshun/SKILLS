---
name: WHP-system-data-query
description: >
  Whirlpool China 系统数据查询与展示工具 — 自动登录 帆软 / SCM 两大系统，
  按料号查询并展示关键系统数据，不下载文件，直接输出表格与汇总指标。

  帆软(库存报表): 按 料号(必填) + 可选 组织/工厂 + 可选 货位，查询 库存现有量。
  SCM: 按 料号 查询 5 类数据并汇总：
    - 回货计划发放（可下发送货通知 = 是 / 否 两个数量）
    - 送货通知单的 未制单数量
    - 送货单的 未接收已报检 / 未接受未报检 数量
    - 采购订单未结量物料汇总的 剩余可发布送货通知总量
    - 请购单中 行状态=下达 的请购单总数量

  所有密码 AES-256 加密存储，Cookie 持久化免重复登录。

  Trigger keywords: 查询库存, 料号查询, 查询料号, 库存现有量, 查询系统数据,
  系统数据查询, 查询回货计划, 查询送货通知, 查询PO未结量, 查询请购单, SCM查询,
  帆软库存查询, 查库存报表

  Usage examples:
  - "查询料号 70C012345 的库存"
  - "查询料号 70C012345 的回货计划和送货通知"
  - "查询料号 123456 的库存现有量，组织 M03，货位 A01"
  - "查 SCM 里 70A01234 的请购单和PO未结量"
---

# Whirlpool China 系统数据查询与展示工具

## 前置条件

- Python 3.11+（系统使用 `py` 命令，不是 `python`）
- Python 依赖:
  ```bash
  pip install playwright ddddocr cryptography
  playwright install msedge
  ```
- Edge 浏览器已安装（版本 80+）
- 首次运行需先设置加密密码:
  ```bash
  py scripts/secure_config.py
  ```

## 触发指令

### ❗ 铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` 和 `||`！**
> 命令体中**绝对禁止**写 `cd ... && node ...` 格式，必须通过 exec 的 `workdir` 参数传递工作目录。
> **禁止在 command 中使用 `python`**，必须用 `py`（系统只有 `py.exe`）。

### ✅ 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "node scripts/run.js --material 70C012345",
    "workdir": "C:\\Users\\qudin\\.openclaw\\workspace\\skills\\WHP-system-data-query",
    "timeout": 1200
  }
}
```

### "查询料号 70C012345 的库存"
```bash
node scripts/run.js --material 70C012345 --module fanruan
```

### "查询料号 70C012345 的 SCM 数据"
```bash
node scripts/run.js --material 70C012345 --module scm
```

### "查询料号 70C012345 的全部(帆软+SCM)"
```bash
node scripts/run.js --material 70C012345
```

### "带组织与货位查询库存"
```bash
node scripts/run.js --material 70C012345 --org M03 --bin A01-01
```

### "设置密码"
```bash
py scripts/secure_config.py
```

### 跨模型执行规则（不可违反）
1. 收到用户指令后，**当前轮必须立即输出 `exec` 工具调用**，不允许纯文字占位
2. workdir 固定：`C:\Users\qudin\.openclaw\workspace\skills\WHP-system-data-query`
3. 命令体中禁止写 `cd ... && ...` 格式
4. 禁止在 command 中使用 `python`，必须用 `py`
5. 默认超时 1200s（20分钟），SCM+OCR 全流程较慢
6. 启动后必须用 `process(poll)` 等待完成并执行 `process(log)` 获取完整日志再汇报

## 执行流程

### 帆软 库存报表（--module fanruan）
1. 登录帆软报表系统（Cookie 恢复 / API 登录兜底）
2. 打开 库存报表（entry-573）
3. 写入 料号（P_ITEMID），可选 组织/工厂、货位
4. 点击查询，等待网格就绪
5. 提取网格 → 汇总 **库存现有量** 并逐行/制表展示

### SCM 系统（--module scm）
对指定料号，依次导航到 5 个查询页，设置料号过滤后查询并汇总：
1. **送货通知查询** → 送货通知单 未制单数量
2. **送货单查询** → 未接收已报检 / 未接受未报检 数量
3. **采购订单未结量物料汇总查询** → 剩余可发布送货通知总量
4. **回货计划/发放** → 可下发送货通知 = 是 / 否 两个数量
5. **请购单查询** → 行状态=下达 的请购单总数量

### 单模块 / 全量
- 默认 `--module all`：帆软 + SCM 都查
- 可指定 `--module fanruan` 或 `--module scm` 只查一个系统

## 配置文件 / 凭证

- 密码加密存储：`scripts/runtime_config/passwords/`（scm / fanruan）
- Cookie 持久化：`scripts/scm_storage_state.json`、`scripts/fanruan_storage_state.json`（12小时内有效）
- 组织代码默认取自配置 `scm.org_code`（默认 M03），可用 `--org` 覆盖
- 首次运行参考：`py scripts/secure_config.py`

## 浏览器

- 使用 msedge（可见模式；`--headless` 可切无头）
- 帆软与 SCM 共享同一浏览器实例
- Cookie 持久化，下次运行无需重新登录
- 完成后自动关闭浏览器
- 结果同时输出到控制台，并写入 `scripts/fanruan_query_result.md` / `scripts/scm_query_result.md`

## 脚本列表

| 文件 | 说明 |
|------|------|
| `scripts/run.js` | Node.js 入口，解析参数并调用 Python |
| `scripts/system_data_query.py` | Python 主程序（帆软+SCM 查询展示） |
| `scripts/whirlpool_common.py` | 公共模块（浏览器、Cookie、密码编解码） |
| `scripts/secure_config.py` | 安全配置（AES-256 加密密码设置/管理） |

## 说明与假设

- 料号过滤字段在各 SCM 查询页使用候选名自动匹配（item_code / sap_item_code / material_code 等），若某页面字段名不同会在日志中提示未过滤。
- 帆软库存报表的 料号/货位 控件名按 P_ITEMID / P_BIN 等候选名尝试，命中后才写入。
- 各汇总指标按列名关键字匹配（如"未制单""可下发送货通知""剩余可发布""库存现有量"等），若实际列名差异较大，会在日志中提示并展示原始表格供人工核对。
- 若页面元素变化，需更新 `scripts/system_data_query.py` 中的选择器 / 控件名。

## 开发备注

- 复用 WHP-whirlpool-download 的 `whirlpool_common.py` / `secure_config.py` 与 ExtJS 导航/查询/网格提取逻辑
- 技能路径：`C:\Users\qudin\.openclaw\workspace\skills\WHP-system-data-query\`
