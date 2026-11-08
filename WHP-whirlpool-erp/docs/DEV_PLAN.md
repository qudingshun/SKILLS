# WHP-whirlpool-erp 开发计划（界面元素自动识别 + 业务动作封装）

> 目标：触发词命中 → IE11 登录 EBS → 进入职责/功能 → **自动识别 Oracle Forms 界面上的按钮位置
> （与屏幕分辨率、窗口大小、窗口位置无关）** → 执行具体业务动作 → 产出结果。

---

## 〇、进度快照（2026-10-21 更新）

| 阶段 | 状态 | 结论 |
|---|---|---|
| P0 Bug 修复 + smoke | ✅ 完成 | 修 3 个 Bug；`smoke_erp.py` 离线自检全绿 |
| P1 坐标基座 | ✅ 完成 | `erp_ui.py`：置前截图、相对坐标、屏幕坐标实时换算、DPI 感知 |
| P2 图像识别引擎 | ✅ 完成 | 多尺度模板匹配（16 档）+ ROI + 中文路径读写；**真机 4/4 命中，置信度 1.000** |
| P3 模板库 / 自学习 | 🟡 部分 | `erp_tpl.py`（裁剪/列出/verify/probe）已具备；交互式 GUI 标注工具未做 |
| P4 Java Access Bridge | ⏸ 待定 | 图像路线已够用；需要控件级读取时再做（32/64 位冲突待解） |
| P5 业务动作封装 | ⏳ 下一步 | `erp_flows.py`（选组织→开表单→查询→取数→导出） |
| P6 输出交付 | ⏳ 下一步 | outputs 目录 + CSV/XLSX + MEDIA 推送 |
| P7 CLI/触发词 | ✅ 部分 | `ui-probe` / `ui-click` 已接入，SKILL.md 触发词已扩 |
| P8 稳定性 | 🟡 部分 | 三个 IE 崩溃坑已定位并规避；仍需人工兜底提示 |
| **P0' 登录通道改造** | ✅ **完成 2026-11-04** | 三次复核后确认 **IE11 COM 完全可用**（前两轮「Win11 停用 IE11」是 360 抢占 IE 内核 COM 注册导致的误判）；IE11 恢复为主路径，纯 HTTP 保留备用，见第七节 7.8 |

### P2 真机验证结果（2026-10-21）
```
[导航] 职责「PO,SANYO合肥三洋物料计划员」已展开，直接读取到 16 个功能（无需点击）
[OK] Oracle Forms 窗口已拉起: hwnd=331348 title='Oracle Applications - 惠而浦（中国）ERP系统'
  取消: 相对(278,580,55,45) 置信度=1.000
  打开O: 相对(700,748,90,45) 置信度=1.000
  查找: 相对(140,580,55,45) 置信度=1.000
  确定: 相对(225,580,55,45) 置信度=1.000
[UI] 点击「查找」屏幕坐标 (167, 602) = 窗口(0,0) + 相对(140,580)
```
离线回归（缩放 0.75/0.9/1.1/1.25、平移、亮度、对比度、JPEG q70）：**44/44 = 100%**。

### 本轮定位到的 3 个根因（已修复，写进 SKILL.md 第 8.1 节）
1. **同一 IE 实例第二次 Navigate → IE 崩溃**（RPC 服务器不可用）。
   → 一个实例只导航一次，换入口就重建实例。
2. **点击职责 <A> → IE 崩溃**。
   → 不点职责；EBS 菜单树按会话保持展开，直接读该 <LI> 下的 launchForm 链接。
3. **功能链接 window.open 被默认浏览器 360 接管** → applet 起不来。
   → 不点功能；只读 URL，自己新开 IE 窗口导航过去。

---

## 一、现状盘点（2026-10-21 实测日志/截图复核）

### 已跑通 ✅
| 环节 | 状态 | 证据 |
|---|---|---|
| IE11 COM 启动 + 中文登录页 + 登录 | ✅ | `logs/erp.log` "已填写账号密码，点击登录" → "已登录 EBS 主页" |
| 主页识别 / 会话复用（免登录） | ✅ | "已处于登录态（IE 会话有效）" |
| 点职责展开功能树（22→41 链接） | ✅ | "职责已展开（链接 22 -> 41）" |
| 点功能 `launchForm(...)` | ✅ | function_id=1908 / resp_id=51318 |
| IE 新窗口承载 applet + Java 8 插件 | ✅ | hwnd=8850966 |
| Forms 窗口出现（class=SunAwtFrame） | ✅ | 标题「Oracle Applications - 惠而浦（中国）ERP系统」 |
| pywinauto 按 hwnd 连接（win32 backend） | ✅ | `FormsApp.connect_by_hwnd` |
| 截图（唯一可靠的"读屏"手段） | ✅ | `logs/forms_window.png`（含「查找/确定/取消」「打开(O)」「组织 MO1~MO5」「常用表单 申请汇总/申请」） |

### 未做 ❌（本次要补）
1. **界面按钮位置自动识别**——目前只能截图 + 人工看，无法按名字点「确定」「打开」「查找」。
2. 控件级读取（读表格内容、读输入框值）。
3. 业务动作封装（选组织 → 开表单 → 查询 → 取数 → 导出）。
4. 结果输出与凭证（Excel/CSV + MEDIA 推送）。

### 已发现的 3 个 Bug（先修，否则会污染识别层）
- `erp_navigator.detect_hijacked_windows()` **误报**：Forms 窗口标题也含 "Oracle Applications"，
  而它的 class 是 `SunAwtFrame`（非 IEFrame），被判成"被其它浏览器接管"。
  → 修法：排除 `SunAwtFrame`，只对 `IEFrame` 之外的**浏览器**类名报警。
- **会话有效但职责找不到**（日志末尾连续 2 次 `[FAIL] 主页未找到职责链接`）：
  `ensure_homepage()` 用 `_has_resp_links()` 判定，但职责列表是延迟渲染的，判定过早。
  → 修法：`_has_resp_links` 加轮询等待（复用 `_wait_for_resp`），主页识别改为"等职责链接出现"或"等主页特征文本"。
- 强杀 IE 后首屏 `title=''`、`RPC 服务器不可用` → 已有重试，建议加**指数退避 + 重建 IE 实例**。

---

## 二、技术路线选型：如何"自动识别按钮位置"

Forms 窗口是 **Java AWT（SunAwtFrame）自绘控件**，UIA backend 只暴露 TitleBar，
因此三条可选通道，按优先级：

### 路线 A：Java Access Bridge（控件级，最精确）— 推荐作为增强项
- 原理：`jabswitch -enable` 打开 JAB，pywinauto 的 `java` backend（依赖 `pyjab`）可枚举
  Swing/AWT 组件树，直接拿到每个按钮的 **name + 矩形**（组件内坐标，与屏幕分辨率无关）。
- 代价：① 需管理员执行 `jabswitch -enable`；② 本机 JRE 是 32 位（jre1.8.0_191），
  而仓库 Python 是 64 位 → 32 位 JAB 的 `WindowsAccessBridge.dll` 无法被 64 位进程加载。
  → 需要**额外装 64 位 JDK8**（仅用于 JAB，不动 applet 用的 32 位 JRE），或用 32 位 Python 跑辅助进程
  （注意：仓库铁律要求用 `.venv`，如走 32 位辅助进程需在技能内说明并单独登记依赖）。
- 收益：真正控件级、可读文本、可点击，**完全满足"位置自动识别"且不受窗口位置/大小影响**。

### 路线 B：图像识别（模板匹配 + OCR）— **主力方案，今天就能做**
- 原理：`capture_as_image()` 拿到 Forms 客户区位图 → OpenCV 模板匹配定位按钮 →
  返回**相对窗口客户区的归一化坐标** → 点击时换算成屏幕坐标（`window.rectangle() + 相对坐标`）。
  → 与屏幕分辨率、窗口大小、窗口位置、显示器数量全部解耦。
- 组件：
  - 多尺度模板匹配（应对 Forms 字体随 DPI 缩放）
  - 垂直/水平梯度 + 边缘检测做"按钮候选框"预筛（ORB 特征点 + 匹配）
  - OCR 兜底识别按钮文字（中文）：`ddddocr` 已装但对 UI 字体一般，建议加 `rapidocr-onnxruntime`（纯 CPU、无需 torch）
- 代价：需要为每个目标表单准备模板图（可**首次人工标注 + 自动裁剪落盘**，之后复用）。

### 路线 C：键盘导航（兜底）
- Forms 支持 Tab 焦点遍历 / F7 查询 / Ctrl+F11 执行查询。
- 无识别能力，但作为"识别失败时的降级通道"保留（SKILL.md 第七节已记录）。

### 决策
**先 B（零外部依赖、当天可验证），再 A（提精度），C 常驻兜底。**
对外统一抽象为一个接口，切换通道对上层业务代码透明：

```python
# 新增 scripts/erp_ui.py
locate(app, "确定") -> Rect | None      # 返回客户区相对矩形
click(app, "确定")  -> bool             # 定位 + 换算 + 点击
read_text(app, ...) -> str              # OCR 或 JAB 读取
```

---

## 三、分阶段开发计划

### P0 基线固化与 Bug 修复（0.5 天）
1. 修 `detect_hijacked_windows` 误报（排除 `SunAwtFrame`）。
2. 修主页判定（延迟渲染）→ 职责链接轮询 + 失败自动回主页重试。
3. IE 首屏空白/`RPC 服务器不可用` → 退避重试 + 必要时重建实例。
4. 产出可复现脚本：`scripts/smoke_erp.py`（登录→职责→功能→Forms 截图→退出码）。

**验收**：`open-forms` 连续 3 次成功，logs 无误报。

### P1 窗口定位与坐标基座（0.5 天）
- 新增 `scripts/erp_ui.py`：
  - `FormsApp` 扩展：客户区矩形、窗口位置、DPI 感知（`SetProcessDpiAwareness`）
  - 统一坐标系：**相对客户区归一化坐标**（0~1）+ 屏幕绝对坐标互转
  - 多显示器 / 负坐标 / 窗口被遮挡 → 用 `PrintWindow` 或置前后台截图兜底
- **验收**：不同分辨率、不同窗口位置下截图与坐标换算正确。

### P2 图像识别引擎（1.5 天）
- 模板库目录：`assets/templates/<form_id>/<elem>.png` + `meta.json`（记录语义名、参考分辨率、缩放系数）
- 匹配器：多尺度模板匹配（TM_CCOEFF_NORMED）+ ORB 特征匹配兜底；置信度阈值与 top-k 输出
- OCR：安装 `rapidocr-onnxruntime`（登记进 `E:\SKILLS\requirements.txt`），用于读按钮/字段文字
- 点击器：`locate → 置信度校验 → 换算屏幕坐标 → move+click`（用 `pywinauto.mouse`）
- **验收**：在 1920x1080 与 125% 缩放下，「确定/取消/查找」定位成功率 ≥ 95%（20 次采样）

### P3 模板生产与自学习（1 天）
- 交互式标注工具 `scripts/erp_label.py`：
  打开 Forms 截图 → 鼠标框选控件 → 输入语义名 → 自动裁剪并写入模板库
- 批量预置：MRP计划员工作台（查找/确定/取消/打开/组织列表/常用表单）
- 校验器 `scripts/erp_tpl_check.py`：对 `logs/*.png` 全量回归，输出命中率报告
- **验收**：新增表单标注耗时 < 2 分钟/表单

### P4 Java Access Bridge 通道（可选，1 天）
- `jabswitch -enable`（管理员）+ 安装 64 位 JDK8（若采用）
- `pywinauto` java backend / `pyjab` 枚举控件树：`控件名 + 组件矩形`
- 通道探测：启动时探测 JAB 可用 → 可用则优先用 JAB（可读文本、可直接点），不可用自动回落图像识别
- **验收**：JAB 可用时能列出「切换职责」对话框全部按钮名

### P5 业务动作封装（2 天，按业务量可迭代）
- 新增 `scripts/erp_flows.py`，每个流程 = 一串 `locate/click/type/read` 步骤：
  1. `switch_org`：选组织（MO1~MO5）→ 确定
  2. `open_form`：常用表单（申请汇总 / 申请）→ 打开(O)
  3. `run_query`：F7 / Ctrl+F11 触发查询，等表格刷新
  4. `read_grid`：OCR + 表格线检测 → 提取行列（低置信度时人工复核截图）
  5. `export`：走 Oracle 标准导出（EBS 常见"导出为电子表格"菜单），落 CSV/XLSX
- 每个流程输出：结果表 + 截图凭证 + 结构化 JSON

### P6 输出与交付（0.5 天）
- 结果写入 `outputs/<时间戳>_<流程名>/`，含 `result.csv/xlsx`、`evidence_*.png`、`run.json`
- 最后一行打印 `MEDIA:<绝对路径>`（仓库铁律）
- 大表导出：优先"复制到剪贴板/导出"，避免全靠 OCR

### P7 CLI 与触发词接入（0.5 天）
- `erp_ops.py` 新增子命令：
  - `erp_ops.py ui-probe "<职责>" "<功能>"` → 列出识别到的控件（调试用）
  - `erp_ops.py label "<职责>" "<功能>"` → 打开标注工具
  - `erp_ops.py run <flow_name> [--org MO1] [--params k=v]` → 执行业务流程
- SKILL.md 更新：触发词扩充（如「跑MRP」「查申请汇总」「导出ERP数据」）、典型用法、异常处理
- 依赖登记：`rapidocr-onnxruntime`（如采用）写入 `E:\SKILLS\requirements.txt` 并在 `.venv` 安装

### P8 稳定性与容错（1 天）
- 超时/重试矩阵：识别失败重试 3 次（换尺度/换策略）→ 仍失败则**明确提示人工接管**并保留截图
- 窗口尺寸/位置/最大化/多显示器 全场景回归
- 统一日志：`logs/erp.log` 增加 `[UI]` 段落（置信度、命中模板、耗时）
- 安全：不误关用户自己的 IE / 360（现有约定保持）；凭据仍只走 `erp_secure_config.py`

---

## 四、里程碑与工作量

| 阶段 | 内容 | 估时 | 里程碑 |
|---|---|---|---|
| P0 | Bug 修复 + smoke 脚本 | 0.5d | 链路稳定可复现 |
| P1 | 坐标基座 | 0.5d | 位置无关的坐标体系 |
| P2 | 图像识别引擎 | 1.5d | **能按名字点按钮** |
| P3 | 模板生产/自学习 | 1d | 新表单 2 分钟适配 |
| P4 | JAB 通道（可选） | 1d | 控件级读取 |
| P5 | 业务流程封装 | 2d+ | 首个业务闭环 |
| P6 | 输出交付 | 0.5d | 报表 + 凭证 |
| P7 | CLI/触发词 | 0.5d | 自然语言触发 |
| P8 | 稳定性 | 1d | 容错 + 人工兜底 |

**最小可用闭环**：P0 + P1 + P2 + P3 + P7 ≈ **4 天**，即可实现
「触发词 → 登录 → 进职责 → 打开 MRP 工作台 → 点『查找』/『确定』→ 出结果截图」。

---

## 五、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Java AWT 自绘，图像识别受主题/字体/缩放影响 | 高 | 多尺度+特征匹配；模板库可按缩放分组；降级到键盘 |
| 32 位 JRE 与 64 位 Python 的 JAB 位数冲突 | 中 | P4 用 64 位 JDK8 解决；失败则纯图像路线 |
| 表单结构随 EBS 升级变化 | 中 | 模板库 + meta 版本号 + 回归检测脚本 |
| OCR 中文识别率 | 中 | rapidocr + 只 OCR 局部区域 + 置信度门槛 |
| 表格数据读取 | 高 | 优先走 EBS 自带导出/剪贴板，OCR 仅作兜底 |
| 强杀 IE 导致状态损坏 | 中 | 不强杀；退避重试；实例登记机制保留 |
| 仓库要求统一 .venv（64 位） | 中 | 优先纯 Python 方案，避免引入 32 位解释器 |

---

## 六、下一步（建议即刻开工）

1. 修 P0 三个 Bug，跑 `smoke_erp.py` 验证。
2. 实现 `erp_ui.py` 坐标基座 + 模板匹配原型，
   在现有 `logs/forms_window.png` 上先离线验证「查找/确定/取消/打开」能否命中（不碰真实 ERP）。
3. 用真实 Forms 窗口跑一次在线验证，产出第一版模板库。
4. 再封装 `switch_org / open_form / run_query` 三个动作，接入 `erp_ops.py run`。

---

## 七、2026-11-04 登录通道复核与改造（本轮）

### 7.1 问题

用户反馈「登录环节不太顺利」，并提问「是否按 EDGE 的 IE 登录形式进行处理」。
排查发现 SKILL.md 的旧结论（IE11 COM 唯一可行 / JNLP 勿再尝试）是 2026-10 的，
**与当前环境已不符**，会误导后续模型反复在失效路径上空转。

### 7.2 实测证据（本机 11-04 第一轮，⚠️ 第 1 行的「Win11 停用 IE11」已被 7.8 推翻，真因是 360 抢占 COM）

| # | 检查项 | 结果 |
|---|---|---|
| 1 | `Dispatch("InternetExplorer.Application")` | ❌ 当时报 `com_error(-2147467262, "不支持此接口")` = **E_NOINTERFACE**（⚠️ 当时 360 在跑；360 退出后恢复正常，见 7.8） |
| 2 | `HKLM/HKCU\SOFTWARE\Policies\Microsoft\Edge` | 均 **NOT FOUND** → 未配置 IE 模式企业站点列表 |
| 3 | `HKCU\...\Zones\3\2500` | `=3`（保护模式已关）——说明**不是**旧文档写的注册表前置没配好 |
| 4 | `logs/probe_edge4.log` | 直接 `msedge.exe --new-window AppsLogin` → `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`（没进 IE 模式） |
| 5 | `logs/probe_edge.log` | 出现过「你正在使用 Internet Explorer 模式」→ IE 模式**时灵时不灵** |
| 6 | `logs/probe_edge3.log` | OCR 定位 `user label None pwd label None`（无 COM DOM，输入框都找不到）→ 登录未提交 → RF.jsp 被重定向 `resp_id=-1`；等 180s `applet=[]`（不加载 Java 插件） |
| 7 | `erp_jws.login()` 纯 HTTP | ✅ **1.1s** 成功，`prod` + `JSESSIONID`，落到 `OA.jsp?OAFunc=OAHOMEPAGE` |
| 8 | 登录后再 GET 主页 | ✅ title「Oracle Applications 主页」、`登录身份 HSA697`、无 `usernameField`，28903 字节，中文界面 |

### 7.3 结论：Edge 的 IE 模式**不作为登录形式**

它只解决「老 TLS 能渲染页面」（走 IE 的 SCHANNEL），但：
- 不提供 `IWebBrowser2` COM DOM → 现有 `erp_ie11.py` 整套 `.value/.click()` 作废，
  退化到 OCR + 坐标点击后连输入框都定位不到；
- 不加载 Java 插件 → 即使登录进去，Forms 的 applet 也起不来，业务全断；
- 依赖企业站点列表策略，本机未配置，实测时灵时不灵。

**登录主路径改为纯 HTTP**：`urllib + CookieJar + SSLContext(DEFAULT@SECLEVEL=0,
options|=0x40000)`，绕开浏览器、COM、Java、企业策略，1 秒级完成。

### 7.4 本轮改动

| 文件 | 改动 |
|---|---|
| `scripts/erp_session.py` | **新增**。通道诊断 `probe_ie11_com / probe_edge_ie_mode / probe_http`、登录校验 `login(verify=True)`、会话信息 `describe()`、`doctor()`；可独立 CLI 运行 |
| `scripts/erp_ops.py` | 新增 `doctor`、`login-http`（别名 `login-session`）；`login-ie11` 改为**先探测 COM，不可用则明确诊断并自动降级到 HTTP**（`--no-fallback` 强制原路径） |
| `SKILL.md` | 第二节整段重写（通道对照 + Edge IE 模式三条证伪证据）；触发指令主路径改 `login-http`；前置条件 / 脚本清单 / 异常处理 / 开发备注同步；修正「JNLP 勿再尝试」的过时说法 |
| `docs/DEV_PLAN.md` | 进度快照加 P0'，新增本节 |

### 7.5 范围边界与遗留（重要）

- **本轮只解决登录**。`erp_navigator.open_function()` / `open-forms` / `ui-probe` /
  `ui-click` 仍依赖 `erp_ie11.open_and_login()`，在当前环境下不可用，已在 SKILL.md 第 4 节标注。
- Forms 侧：`logs/jws_start4.log`、`jws_tls.log` 证明本地生成 JNLP + `javaws` **能拉起**
  `SunAwtFrame` 窗口（12s），但 `logs/probe_console.log` 显示 236s 一直停在
  「Oracle Applications | ORACLE | e-businesssuite」启动图，**Forms 连接层未闭环**。
  `scripts/_probe_av.py` 是本轮留下的诊断入口（用 `sun.applet.AppletViewer` 抓 JVM
  stdout/stderr），下一步应从它的输出定位 applet 连不上 forms servlet 的原因。
- 验证状态：`py_compile` + 模块导入 + `_parse_home()` 离线用例 + CLI 分支清单 全部通过；
  改动前已实测 HTTP 登录与主页抓取成功。**改动后的三个 CLI 端到端实跑命令因安全审批
  超时被拦截，本轮未能复跑**，需下次授权后补跑：
  `E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py doctor`（再依次 `login-http`、`login-ie11`）。

### 7.6 下一步建议

1. 补跑上述三个 CLI，确认退出码 0 与输出。
2. 用 `_probe_av.py` 的 JVM 日志定位 Forms 停在启动图的原因（疑似旧 TLS/套件或
   `icx_ticket` 会话票据传递问题）。
3. 把 `erp_navigator` 的职责/功能读取改成 HTTP 解析，彻底去掉对 IE11 COM 的依赖。

### 7.7 2026-11-04 二次复核（用户反馈「实际业务用 IE11」）

用户要求重测 IE11 流程。重新实测后**修正上一轮的过度概括**：

| 检查 | 结果 |
|---|---|
| 5 种 COM 创建方式（Dispatch / DispatchEx / EnsureDispatch / CoCreateInstance IDispatch / IWebBrowser2） | 全部 E_NOINTERFACE；CLSID 的 `LocalServer32` 注册表项完好，无 IE 退役策略 |
| 直接启动 `iexplore.exe <ERP 中文登录页>` | 进程立刻退出（poll=1），新开的是 `Chrome_WidgetWin_1` **Edge** 窗口，**无任何 IEFrame** |
| `ielowutil.exe -CLSID:{0002DF01-...} -Embedding` | 存在、无窗口 → COM 拿不到 `IWebBrowser2` 的直接来源 |
| `erp_ops.py login-ie11 --no-fallback` 完整实跑 | `open_and_login()` → `_new_ie()` → `Dispatch` 直接抛 E_NOINTERFACE，退出码 1 |
| 桌面实际 Forms 窗口 | `SunAwtFrame` / `jp2launcher.exe` pid 7416，父进程 `360chromeie.exe --type=plugin --plugin-path=...\jre1.8.0_191\bin\plugin2\npjp2.dll`，创建时间 13:20:37 → **360 兼容模式 IE 内核 + Java 插件**，链路是通的 |
| 360 主窗口 | 当前标签是 SRM（`srm.whirlpool-china.com:7600`），Chromium 内核；兼容模式标签由独立 `360chromeie.exe` 承载 |
| Edge | 开着 `edge://settings/search=兼容`（IE 模式设置），但注册表无企业策略 |

**结论修正**：**A（IE11 桌面程序 + COM）死、B（IE 内核承载 Applet）活、
C（Edge IE 模式）不用于自动化**。登录仍走纯 HTTP；Forms 侧应尊重/复用 B，
不要试图用 IE11 COM 导航替代。用户「不主动使用 360 / 不干预 360 进程」的约定
保持不变，脚本不启动 360。SKILL.md 第二节已加 A/B/C 澄清表。

**副作用事故与修复**：本次实跑 `login-ie11 --no-fallback` 时，
`open_and_login()` 开头的 `cleanup_automation_leftovers()` 把用户**最小化**的
Forms 窗口（`GetWindowRect = -32000` 被判为「屏幕外僵尸」）误关，
`jp2launcher.exe` pid 7416 消失、桌面 Forms 窗口数归零。
已修：`cleanup_automation_leftovers(dry_run=True)` 默认只报告，
**Forms 窗口一律不自动关闭**、不再强杀宿主进程；
`erp_ops.py cleanup` 需显式 `--force` 才关 360 承接窗口。
该 Forms 会话需用户在 360 兼容模式里重新点功能拉起，脚本不擅自重建。

### 7.8 2026-11-04 第三次复核（用户「改用 IE11」，**推翻前两轮误判**）

用户先解除 360 限制，后明确改为「不用 360，用 IE11」。据此重新实测，
**发现前两轮「Win11 停用 IE11 / IE11 已死」的结论全部是误判**：

| 检查 | 结果 |
|---|---|
| 用户手动退出 360 后 `Dispatch("InternetExplorer.Application")` | ✅ **成功**：HWND=1051704，Name="Internet Explorer" |
| IE11 导航到中文登录页 | ✅ title「登录」，`usernameField`/`passwordField` 均找到，body 显示中文表单 |
| IE11 填表登录 | ✅ 进入主页 title「Oracle Applications 主页」、`登录身份 HSA697` |
| `erp_ops.py login-ie11 --no-fallback` | ✅ 退出码 0，全流程：登录→切中文→填表→主页→截图→注销→关 IE |
| `erp_ops.py open-forms "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台"` | ✅ 退出码 0：登录→职责展开(16 功能)→launchForm→新 IE 窗口→**Forms 窗口拉起 hwnd=68954**→FormsApp 连接→截图→注销 |
| 360 带 `--remote-debugging-port` CDP | ⚠️ 端口启动后 1s 可用，随后不稳定（360 非标准 DevTools 服务器，Playwright connect_over_cdp 报 502） |
| 360 兼容模式标签页 | 由 `360chromeie.exe` 承载，不暴露 COM（Shell.Windows 看不到）、不在 CDP 内 |

**根因定位**：前两轮 `Dispatch` 报 `E_NOINTERFACE`，**不是 Win11 停用 IE11**，
而是 **360 安全浏览器的 `360chromeie.exe` 进程在运行时抢占了 IE 内核（Trident）
的 COM 注册**，把 `InternetExplorer.Application` 这个 ProgID 指向了自己的实现，
导致真正的 IE11 窗口拿不到。**360 完全退出后，IE11 COM 立即恢复**。

**最终结论**：
- **IE11 COM = 主登录路径**（`login-ie11`），完整业务闭环可用（含拉起 Forms）；
- **纯 HTTP（`erp_session.py` / `login-http`）= 备用**，1 秒级但**不承载 Forms**；
- **360 不用**（用户要求，且运行时反而干扰 IE11 COM）；
- Edge IE 模式仍证伪。

**本轮改动**：SKILL.md 第二/三/五/六/八/九节、erp_session.py、erp_ops.py、
erp_ie11.py 的「IE11 已死」表述全部改为「IE11 可用，360 干扰是误判根因」；
`doctor()` / `probe_ie11_com()` / `cmd_login_ie11()` 的诊断文案同步修正为
「先查 360 是否在跑」。

**用户核心要求（已满足）**：「对自己开启的网页负责，失败重开前关旧登录界面」——
`erp_ie11.open_and_login()` 的失败重试路径本就关闭旧 IE（`close_ie_hwnd` +
`taskkill` 残留）后重建，且 `close_previous_instances` / `close_our_instances`
只关脚本登记过的窗口，不碰用户自己开的浏览器。

