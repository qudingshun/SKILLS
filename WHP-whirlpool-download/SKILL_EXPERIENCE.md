---
name: WHP-whirlpool-download
description: >
  Whirlpool China 统一报表下载工具 - 自动登录 SCM/OA/帆软三大系统，
  按 SCM→OA→帆软顺序执行全部报表下载任务。
  ...
  所有密码 AES-256 加密存储，Cookie 持久化免重复登录。
  Trigger keywords: 报表下载, 下载报表, whirlpool下载, SCM下载, 帆软下载,
  OA下载, 统一下载, 下载工具, 帮我下载报表, 下载送货通知, 下载PO未结量
  ...
---

# Whirlpool China 统一报表下载工具

## 经验教训 (2026-10-06)

### 踩坑总结

1. **JS解释器问题**：
   - 错误做法：用 Python 解释器运行 `.js` 文件
   - 正确做法：用 Node.js 命令运行 `node scripts/run.js`
   - 错误原因：Python 不能解析 JS 语法，会报 `SyntaxError: invalid character`

2. **Unicode字符问题**：
   - 问题字符：全角括号 `（）`、冒号 `：`、箭头 `→`
   - 解决方案：替换为 ASCII 字符 `:`, `()`, `->`
   - **重要**：修改代码前必须获得用户确认

3. **headed mode 用法**：
   - 默认：浏览器**有头模式**（显示窗口）
   - 无头模式：添加 `--headless` 参数（后台静默）

4. **超时处理**：
   - 全量下载 5-10 分钟
   - 超时自动转为后台任务