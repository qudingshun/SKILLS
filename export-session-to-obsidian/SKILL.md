---
name: "export-session-to-obsidian"
description: "将 OpenClaw 当前（或全部）会话导出为 Obsidian Markdown + 提取知识点卡片，触发词：导出对话"
---

# 导出会话到 Obsidian

## 前置条件
- Node.js（无需额外依赖）
- 目标目录：`D:\Raw\openclaw-sessions\`
  - `D:\Raw\openclaw-sessions\{YYYY-MM-DD}\{标题}.md` — 对话记录
  - `D:\Raw\openclaw-sessions\_knowledge\{keyword}.md` — 知识点卡片
  - `D:\Raw\openclaw-sessions\_knowledge\_index.md` — 知识索引
- 脚本文件：`WHP-whirlpool-email-reports/scripts/export-session-to-obsidian.cjs`

## 触发指令

### "导出对话" / "导出会话" [--update-knowledge]
```bash
node scripts/export-session-to-obsidian.cjs
```

**执行步骤（自动执行，不得跳过）：**

1. **读取当前会话 JSONL** —— 用脚本解析增量导出
   ```
   node scripts/export-session-to-obsidian.cjs
   ```
   workdir: `C:\Users\qudin\.openclaw\workspace\skills\WHP-whirlpool-email-reports`
   超时: 120s

2. **读取新增内容** —— 从对话记录文件中读取新追加的内容，即 `## 对话` 后面的部分

3. **分析知识点** —— 读取新增的用户提问和你的回答，识别有价值的知识点（配置参数、路径规则、业务逻辑等），对每个知识点：
   - 提炼标题（简练、概括性强）
   - 写入知识点卡片：`D:\Raw\openclaw-sessions\_knowledge\{kebab-name}.md`
   - 格式：
     ```markdown
     ---
     title: "xxx"
     date: YYYY-MM-DD
     tags:
       - knowledge
     source: "来自会话: [[日期_标题]]"
     ---

     # xxx

     > 关键结论/知识描述

     详细内容...

     ## 来源
     - [[日期_标题]]
     ```
   - 若知识点卡片已存在，追加反向链接即可

4. **更新对话记录** —— 回到对话记录文件，在 frontmatter 中添加已提取的知识点 wikilinks（`links:` 或 `aliases:`）

### "导出全部会话" [--update-knowledge]
```bash
node scripts/export-session-to-obsidian.cjs --all
```
同上，但扫描所有活跃会话。

## 跨模型执行规则
1. workdir 固定：`C:\Users\qudin\.openclaw\workspace\skills\WHP-whirlpool-email-reports`
2. 命令：`node scripts/export-session-to-obsidian.cjs`（默认当前会话）
3. 超时 120s
4. 启动后必须用 `process(poll)` 等待完成，获取日志
5. 日志输出后，**必须**读取导出文件分析新增内容中的知识点，写入 `_knowledge/`
6. **知识点由分析而来，不得跳过**：读取文件后，识别配置参数、技能触发词、脚本路径等可复用的信息

## 输出示例

### 对话记录文件
`D:\Raw\openclaw-sessions\2026-07-21\2026-07-21_检查WHP-whirlpool-email-reports技能.md`
```
---
title: "检查WHP-whirlpool-email-reports技能"
date: 2026-07-21
total_messages: 432
new_messages: 8
exported_at: "2026-07-21 22:53:21"
knowledge_points: 2
tags:
  - openclaw-session
  - ai-chat
  - 2026-07-21
links:
  - "[[WHP-whirlpool-email-reports-技能|WHP-whirlpool-email-reports 技能]]"
  - "[[download-reports-cjs|download-reports.cjs 搜索逻辑]]"
---

# 检查WHP-whirlpool-email-reports技能

> 2026-07-21 | 消息: 432 (+8) | 🧠 知识: 2
...
```

### 知识点卡片
`D:\Raw\openclaw-sessions\_knowledge\WHP-whirlpool-email-reports-技能.md`
```markdown
---
title: "WHP-whirlpool-email-reports 技能"
date: 2026-07-21
tags:
  - knowledge
source: "来自会话: [[2026-07-21_检查WHP-whirlpool-email-reports技能]]"
---

# WHP-whirlpool-email-reports 技能

> 下载惠而浦企业邮箱的三份标准报表（产量、波轮出口、仓库日报）

- 脚本: `download-reports.cjs`
- IMAP: imap.qiye.163.com:143
- 密码: 环境变量 `MAIL_PASS`
- 定时: 每天 08:50

## 来源
- [[2026-07-21_检查WHP-whirlpool-email-reports技能]]
```

## 知识点提取规则指南

### 什么是"知识点"？
能从对话中提炼出的、**可独立复用**的信息：

| 类别 | 示例 |
|------|------|
| 技能触发词和功能 | "触发词：回货、下载邮件、报表下载" |
| 配置参数 | "IMAP: imap.qiye.163.com:143, 密码环境变量 MAIL_PASS" |
| 脚本路径和功能 | "download-reports.cjs 增量搜索，状态文件 .download-state.json" |
| 业务流程 | "每日08:50下载邮件，移旧→搜索→下载→保存→记录状态" |
| 文件/目录路径 | "E:\OneDrive\桌面\生产情况日报\" |
| 定时任务信息 | "23:00 定时导出会话到 Obsidian" |
| 技术原理 | "IMAP 不支持中文搜索，改用序号范围增量搜索" |
| 工具使用 | "exec workdir 参数传工作目录，不用 cd" |

### 知识点写法要求
- **标题前加 tag**：每个知识点文件都写 `tags: [knowledge]`
- **简明扼要**：不是复述对话，是提炼核心结论
- **双向链接**：知识点卡片开头写 `source: "来自会话: [[xxx]]"`，对话记录 frontmatter 加 `links: ["[[xxx]]"]`
- **不重复**：知识点卡片已存在 → 只追加反向链接，不覆盖

### 执行时机
- ✅ 每次"导出对话"后必须执行知识点分析
- ✅ 小知识合并到知识点卡片，不单独建
- ✅ 知识点应该越来越少重复，越来越多关联

## 技术要点
- JSONL 逐行解析：`session/message/model_change/custom` 等条目
- 增量机制：通过 `.export-state.json` 状态文件记录最后导出的消息 ID
- 标题提取：使用第一条用户消息的前 40 字作为文件名
- 知识点卡片按 `kebab-case` 命名，放入 `_knowledge/` 目录
- `_knowledge/_index.md` 自动维护索引

## 输出目录结构
```
D:\Raw\openclaw-sessions\
├── 2026-07-21\
│   ├── 2026-07-21_检查WHP-whirlpool-email-reports技能.md
│   └── ...
├── 2026-07-22\
│   └── ...
├── _knowledge\                    ← 知识点卡片（独立于日期）
│   ├── _index.md                  ← 索引
│   ├── WHP-whirlpool-email-reports-技能.md
│   ├── download-reports-cjs.md
│   └── ...
└── ...
```

## 已废弃功能（已移除）
- 邮件简报（briefing-to-excel.js）
- 回货数据源空壳（huihuo-reports.js）
