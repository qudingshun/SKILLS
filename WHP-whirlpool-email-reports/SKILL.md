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
- npm packages: `mailparser`, `xlsxwriter`（iconv-lite 可选，脚本使用 Node.js 内置 Buffer 编码）
- IMAP: imap.qiye.163.com:143, dingshun_qu@whirlpool-china.com（授权码登录）
- 目标目录：`E:\OneDrive\桌面\生产情况日报\`

## Python 依赖安装
```bash
# 使用国内镜像源（iconv-lite 可能不可用，脚本已改用内置 Buffer）
E:/SKILLS/.venv/Scripts/python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple mailparser xlsxwriter
```

## 技术要点
- 网易企业邮 IMAP **不支持**中文 SEARCH FROM/SUBJECT → 改用 `SEARCH SINCE` + 批量扫描头部做本地匹配
- **波轮出口日常报表 (qingyu_zhou)**：主题常被改动（如「10.15」），因此配置 `attachmentOnly: true` → 只按「发件人 + 附件名含"波轮出口日常报表"」命中，主题不作条件；发件人命中后拉全文验附件，未命中最多回溯 30 封候选
- **编码处理**：脚本使用 Node.js 内置 Buffer（UTF-8→GBK）替代 iconv-lite，避免依赖缺失问题
- Excel 生成使用 xlsxwriter 库

## ⚠️ 包名陷阱（必读）
- `mailparser`（无下划线），不是 `mail_parser`。PyPI 上只有 `mailparser` 包。
- `iconv-lite` 在国内镜像源可能不可用，脚本已改用纯 Node.js Buffer 编码，无需安装该依赖。

## 🐞 2026-10-29 三处 bug 修复（脚本已改，勿回退）

当天实际运行只成功 1/3（只有「波轮出口日常报表」下来），排查出三个独立缺陷：

**① 主题解码被改成空操作（回归，最严重）**
`decodeSubject()` 曾被替换成 `Buffer.from(s,'utf-8').toString('utf-8')` 这种往返操作——**等于不解码**，
返回值仍是 `=?UTF-8?B?...?=` 原始编码串，于是 `subject.includes('装配车间产量报表')` 永远为假。
表现：报表 1（产量）和报表 3（仓库日报）恒报「未在最近500封中找到匹配邮件」，而报表 2 因为走 `attachmentOnly` 不校验主题，照常成功。
**修复**：恢复 RFC2047 解码，但不再依赖 `iconv-lite`，改用 Node 内置 `new TextDecoder('gbk')`
（Node 24 带 full-ICU，实测可用）；并处理相邻 encoded-word 之间的折行空白，避免把空格塞进主题中间。

**② IMAP literal 用字符数切、按字节数标记（解析器错位）**
IMAP 的 literal 头 `{1877xxx}` 是**字节数**，旧代码却从 `d.toString()` 得到的**字符串**里按这个数字 `slice`。
UTF-8 中文一个字符占 3 字节 → 实际消费的字节数远少于标记值 → 解析器错位，
**下载完一封 1.8MB 大邮件后，后续所有命令都收不到响应**。
**修复**：接收缓冲改 `Buffer`，literal 全程按 `buf.subarray(n)` 切；`fetchFullEmail` 直接返回 `Buffer`
（顺带让 `simpleParser` 能按 charset 正确解码）。

**③ 超时抛字符串 `'TO'`，把超时伪装成服务器错误**
`send()` 的 30s 超时写成 `rej('TO')`，`main().catch(e=>console.error('❌', e.message||e))` 打出来就是 `❌ TO`，
看起来像 IMAP 服务器应答，实际是本地超时（bug ② 的后果）。
**修复**：改成 `rej(new Error('IMAP 命令超时(60s): '+cmd))`，超时从 30s 提到 60s，成功后 `clearTimeout`。

**附带修复**：`findHeader()` 原先用字符串 `':\s*(.+)'` 拼正则（`\s` 在单引号里退化成字母 `s`，靠 `trim()` 侥幸工作）；
且折行头会截断 From 里的收件人地址 → 现在展开续行（以空格/Tab 开头）后再匹配。

**回退点**：改坏前的版本已备份为 `scripts\download-reports.cjs.bak-20261029`。

**修复后实测（2026-10-29 18:07）三份全中**：
| 报表 | 邮件 | 落盘 |
|---|---|---|
| 装配车间产量报表 | #7875 10-29 08:18 | `产量\波轮工厂2026年10月装配车间产量报表.xlsx` 1,277,609 B |
| 波轮出口日常报表 | #4353 10-29 09:07（主题只有「10.28」） | `发货\2026年10月份波轮出口日常报表(k-984南岗一期库).xlsx` 226,479 B |
| 出口成品仓库日报明细表 | #4351 10-28 08:11 | `发货\10月份惠而浦出口成品仓库日报明细表(K-991 南岗日本库)10.27.xls` 361,472 B |

> 注意：仓库日报当天只拿到 **10.27 数据**，因为 `songming_ye` 最新一封就是 10-28 08:11 那封（10-29 未发），
> **属发件方缺失，不是脚本问题**。排查方法：直接查该文件夹最新几封的 From/Subject（见下）。
> 另外产量报表的**文件名**是 `波轮工厂2026年10月装配车间产量报表.xlsx`，
> 含「装配车间产量报表」的是**主题**不是附件名，别按文件名反推。

**排查「某份报表没下来」的标准动作**：先确认邮件在不在，再怀疑脚本。用 imaplib 直接看该文件夹最新几封
（比在 node 脚本里加日志快，且不受 IMAP 协议解析 bug 影响）：

```python
# E:/SKILLS/.venv/Scripts/python.exe 运行；MAIL_PASS 需已在用户环境变量里
import imaplib, os, email
from email.header import decode_header, make_header
M = imaplib.IMAP4('imap.qiye.163.com', 143)
M.login('dingshun_qu@whirlpool-china.com', os.environ['MAIL_PASS'])
M.select('"&YhBUwVPRjSc-"')          # 发货类；产量类用 "&TqeRz2KliGg-"
ids = M.search(None, 'ALL')[1][0].split()
for i in ids[-8:]:
    raw = b''.join(x[1] for x in M.fetch(i, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')[1] if isinstance(x, tuple))
    m = email.message_from_bytes(raw)
    print(i.decode(), m.get('Date','')[:31], str(make_header(decode_header(m.get('Subject','')))), m.get('From',''))
M.logout()
```

## 凭证管理
- 邮箱主机/端口/用户名在脚本内写死
- **密码**仅读取环境变量 `MAIL_PASS`（脚本内无硬编码密码，未设置则无法登录）
- 如需改密码：`[Environment]::SetEnvironmentVariable('MAIL_PASS', '新密码', 'User')` + 重启 Gateway

## 脚本列表
| 脚本 | 功能 |
|------|------|
| `scripts/download-reports.cjs` | **下载三份标准报表** + 智能时间过滤（仅扫描指定日期范围） |
| `scripts/rebuild-orders-excel.js` | 提取订单信息 → 独立 Excel（订单.xlsx） |
| `scripts/expand-emails.js` | 提取单封邮件正文详情 |
| `scripts/fetch-order-emails.js` | 抓取订单相关邮件 |
| `scripts/export-session-to-obsidian.cjs` | **导出会话到 Obsidian** — 将当前会话增量导出为 Markdown 到 `D:\Raw\openclaw-sessions\{日期}\` |

## ⚠️ 目录清理陷阱

### 旧副本残留
- ~~`E:\WHP-whirlpool-email-reports\scripts\`（无 `SKILLS/` 前缀）是历史残留副本~~ —— **2026-10-29 复查：该目录已不存在，清理完成**。
- 另有旧树 `E:\whirlpool-china\`（2026-09 之前的原项目）同样不可再引用，已标注废弃。
- **铁律**：只认 `E:\SKILLS\WHP-whirlpool-email-reports\scripts\` 下的文件。旧副本里的 `download-reports.js`、`email-briefing.js`、`briefing-to-excel.js`、`check-attachment.cjs`、`huihuo-reports.js` 及 `.log` 文件均为无用文件，若再次出现直接删除。
- 如果发现邮箱目录下同时存在两个 `scripts/` 子目录，优先清理非 `E:\SKILLS\` 路径下的副本。

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


