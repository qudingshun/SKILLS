---
name: WHP-whirlpool-email-reports
description: >
  Download Whirlpool China production reports from corporate email (qiye.163.com).
  Triggers when user mentions: 下载邮件，邮件下载
  Reports: 装配车间产量报表 (wenjie_shen), 波轮出口日常报表 (qingyu_zhou),
  惠而浦出口成品仓库日报明细表 (songming_ye).

  Handles IMAP via raw socket to imap.qiye.163.com:143. Handles GB2312/GBK via iconv-lite.
---

# 惠而浦邮件报表下载

## 前置条件
- npm packages: `imap`, `mailparser`, `iconv-lite`, `xlsx`
- IMAP: imap.qiye.163.com:143, dingshun_qu@whirlpool-china.com（授权码登录）
- 目标目录：`E:\OneDrive\桌面\生产情况日报\`

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
    "command": "node E:/SKILLS/WHP-whirlpool-email-reports/scripts/download-reports.cjs",
    "workdir": "E:/SKILLS/WHP-whirlpool-email-reports",
    "timeout": 120
  }
}
```

### "下载邮件" / "邮件下载"
```bash
node E:/SKILLS/WHP-whirlpool-email-reports/scripts/download-reports.cjs
```
- 移旧 → 下载三份最新报表 → 保存附件到对应目录

### "查看邮件详情 #序号"
提取单封邮件的正文和附件信息。

## 自动化

### 定时任务配置
- **邮件下载**: 每天 08:50 (Cron: `50 8 * * *`, Asia/Shanghai)
- **产销存日报**: 每天 09:00 (Cron: `0 9 * * *`, Asia/Shanghai)

### 智能时间过滤机制
- ✅ 自动记录上次搜索时间戳（环境变量：`EMAIL_LAST_SEARCH_TIME`）
- ✅ 下次搜索仅扫描指定时间范围内的邮件（默认昨天 + 今天）
- ✅ 避免重复下载同一份报表，提高效率
- ✅ 定时任务每次执行后自动更新时间戳

### 链式任务执行流程（每日 09:00）
1. `node skills/WHP-whirlpool-email-reports/scripts/download-reports.cjs` — 下载三份邮件报表
2. `E:/SKILLS/.venv/Scripts/python.exe E:\whirlpool-china\inventory_daily_report.py` — 更新产销存日报

## 技术要点
- 网易企业邮 IMAP **不支持**中文 SEARCH FROM/SUBJECT
  → 改用 `SEARCH SINCE` + 批量扫描头部做本地匹配
- 文件夹名使用 IMAP Modified UTF-7 编码（预解码对照表见脚本）
- 发件人/主题使用 iconv-lite 解码 GB2312/GBK 编码
- Excel 生成使用 xlsx 库

## 凭证管理
- 邮箱主机/端口/用户名在脚本内写死
- **密码**仅读取环境变量 `MAIL_PASS`（脚本内无硬编码密码，未设置则无法登录）
- 如需改密码：`[Environment]::SetEnvironmentVariable('MAIL_PASS', '新密码', 'User')` + 重启 Gateway

## 脚本列表
| 脚本 | 功能 |
|------|------|
| `scripts/download-reports.cjs` | **下载三份标准报表** + 智能时间过滤（仅扫描指定日期范围） |
| `scripts/email-briefing.js` | (旧) 纯文本简报输出（已废弃，已移至 `_backup/`） |
| `scripts/rebuild-orders-excel.js` | 提取订单信息 → 独立 Excel（订单.xlsx） |
| `scripts/expand-emails.js` | 提取单封邮件正文详情 |
| `scripts/fetch-order-emails.js` | 抓取订单相关邮件 |
| `scripts/export-session-to-obsidian.cjs` | **导出会话到 Obsidian** — 将当前会话增量导出为 Markdown 到 `D:\Raw\openclaw-sessions\{日期}\` |

## ⚠️ 重要经验教训：邮箱清理后的序号重置机制

### 问题场景
- 用户手动删除/移动邮件后，邮箱总数量会减少
- 上次保存的搜索序号（如 #11144）可能**大于当前邮箱总数**（如 7822）
- 脚本会误判"无新邮件"，导致无法下载最新报表

### 自动检测与重置逻辑
```javascript
// 在 download-reports.cjs 中
for (const [folder, lastIdx] of Object.entries(state)) {
  const total = folder.length; // 邮箱总数
  if (lastIdx > total) {
    console.log(`⚠️ ${folder}: 上次序号${lastIdx} > 总数${total}，检测到邮件清理`);
    state[folder] = Math.floor(total / 2); // 重置为中间值（保守策略）
  }
}
```

### 用户触发词包含"重置"或"重新获取"时
- 自动将三个邮箱的起始序号统一设置为 **4000**
- 确保能扫描到最近 30% 的邮件范围，提高命中率

### 最佳实践建议
1. **定期清理前**: 先运行一次下载脚本保存最新状态
2. **清理后**: 等待几小时让新邮件到达，再重新搜索
3. **发现序号异常**: 如果日志显示 `lastIdx > total`，说明已自动重置

## 自动产出文件
| 文件 | 生成时间 | 说明 |
|------|:--------:|------|
| `桌面/YYYY-MM-DD_HH 时订单信息.xlsx` | 9/13/17 点 | 四笔订单独立 Sheet（台湾/拉美/Kogan/配件） |
| `生产情况日报/产量/*` | **08:50** (定时任务) | 装配车间产量报表（仅下载指定日期范围） |
| `生产情况日报/发货/*` | **08:50** (定时任务) | 波轮出口日报 + 仓库日报（仅下载指定日期范围） |
| `D:\Raw\openclaw-sessions\...` | **23:00** (定时任务) | 会话记录导出到 Obsidian 目录 |


