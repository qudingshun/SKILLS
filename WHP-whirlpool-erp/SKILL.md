---
name: WHP-whirlpool-erp
description: >
  惠而浦 EBS（Oracle ERP）操作工具 - 自动登录 erp.whirlpool-china.com:4446 的
  OA Framework 首页，并支持启动/操作 Oracle Forms（Java 应用）。

  密码采用 AES-256 加密存储（与 WHP-whirlpool-download 同源机制），明文绝不落盘。
  该服务器只认老 TLS/加密套件，Chromium 系（Edge/Playwright）握手必败。
  登录有两条独立路径：IE11（COM 自动化，走 Windows SCHANNEL，须彻底退出 360 安全卫士）
  与纯 HTTP + javaws 无 COM（主入口 `erp.py --http`，360 运行时也能用，推荐日常使用）。
  该服务器只认老 TLS/加密套件，Chromium 系（Edge/Playwright）握手必败。
  密码采用 AES-256 加密存储，明文绝不落盘。

  Trigger keywords: ERP登录, 登录ERP, 打开ERP, 惠而浦ERP, EBS操作, Oracle操作,
  打开ORACLE, ERP报表, ERP职责, ERP表单, 操作甲骨文, whirlpool erp,
  MRP工作台, MRP计划员, 点确定, 点查找, 识别界面按钮, ERP界面元素,
  ERP登录失败, 登录通道诊断, IE11停用, Edge IE模式, 登录报错

  Usage examples:
  - "登录惠而浦ERP"（走 erp.py login）
  - "帮我打开ERP"
  - "操作ERP里的XX职责"（erp.py open-forms <职责> <功能>）
  - "ERP 又登录不上，帮我查一下"（先跑 erp.py check / 退出 360）
  - "识别MRP工作台界面上确定按钮的位置"
---

# 惠而浦 EBS（Oracle ERP）操作工具

## 一、这个系统是什么 / 怎么操作

惠而浦 ERP 是 **Oracle E-Business Suite（EBS）**。它有两层界面：

1. **OA Framework 网页（OAF）**：纯网页，登录后像普通网站一样操作。
   用 Playwright 驱动浏览器即可。
2. **Oracle Forms（Java 应用）**：很多“职责 / 功能”不是网页，而是一个独立的
   **Java 程序**窗口（Oracle Forms）。2026-10-20 实测确认其架构：

   > 点击功能 → `javascript:launchForm('...RF.jsp?function_id=...')` → 新 IE 窗口
   > 加载 `/forms/frmservlet` → 返回 `appsbase.htm`（**JInitiator 架构的 Java Applet**
   > 页，不是 JNLP）→ 本机 Java 8 插件（jre1.8.0_191 32 位）运行 `FormsLauncher`
   > applet → 弹出独立 Java 窗口（class=`SunAwtFrame`，标题
   > 「Oracle Applications - 惠而浦（中国）ERP系统」）

   ⚠️ 上面是 2026-10 的旧结论，**2026-11-04 复核后仍然成立**：IE11 + Java 插件承载
   applet 这条链路**完全可用**（彻底退出 360 安全卫士后 `login-ie11`、`open-forms`
   实测退出码 0，Forms 窗口 `SunAwtFrame` 正常拉起）。此外新增**纯 HTTP + javaws
   无 COM 路径**（`erp.py ... --http`）：360 运行时也能登录并拉起真实 Forms 界面，
   详见第二节与第三节 3a。

## 二、登录通道选型（2026-11-04 最终定论）

> ✅ **2026-11-04 最终结论**：存在**两条互相独立**的可用路径，按 360 是否在跑选：
> 1. **IE11 COM 自动化**（全链路：登录→职责→功能→拉 Forms）——**前提：彻底退出
>    360 安全卫士**（见下根因）。退出后 `login-ie11 --no-fallback` / `open-forms`
>    实测退出码 0、全链路成功。
> 2. **纯 HTTP + javaws 无 COM**（主入口 `erp.py ... --http`）——**360 运行时也能用**，
>    不碰 `iexplore.exe`。`erp_jws.login()`（urllib+老TLS）登录稳定；
>    `open-forms ... --http` 经本地 JNLP + `javaws` 拉起 `SunAwtFrame` 并渲染真实
>    业务界面（MRP 工作台，已截图证实）。这是「360 不退出也能登录/操作 ERP」的官方解法。

### 通道实测对照（本机 2026-11-04 最终）

| 通道 | 结论 | 证据 / 条件 |
|---|---|---|
| **IE11 COM** | ✅ 主路径（仅限 360 安全卫士完全退出时） | `Dispatch` 成功拿 HWND；`open-forms` 退出码 0，Forms `SunAwtFrame` 拉起 |
| **纯 HTTP + javaws**（`erp.py --http`） | ✅ **360 运行时首选** | 登录 1.x s、`open-forms --http` 拉起真实 Forms 界面；零 IE/COM 依赖 |
| Edge 普通模式 / Playwright | ❌ TLS 握手失败 | `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`（Chromium 删了老套件） |
| Edge IE 模式 | ❌ 不作为登录形式 | 无企业策略、无 COM DOM、不加载 Java 插件 |
| 360 浏览器 | ⛔ 不用 | 用户日常开 360；360 安全卫士内核驱动会拦 IE（见下） |

### ⚠️ 关键根因：360 安全卫士内核驱动拦截 IE（务必记住，此前误判已修正）

`Dispatch("InternetExplorer.Application")` 报 `E_NOINTERFACE` / 直接 `iexplore.exe`
启动即返回码 1 退出，**真正根因不是 360 浏览器，而是 360 安全卫士的「防劫持」**
**内核驱动 `360AntiHijack64.sys`**（同驻 `360AntiAttack64`/`360AntiSteal64`/
`360Box64`/`360netmon64`/`360qpesv64`）在**内核态静默拦截 `iexplore.exe` 启动**。

> 之前（11-04 早些时候）误判为「360 浏览器的 `360chromeie.exe` 抢占 IE COM 注册，
> 360 退出即恢复」——**该结论已被 18:xx 的决定性诊断推翻**。铁证：注册表
> （ProgID/CLSID/LocalServer32/AppID/TreatAs/AppInit_DLLs/IFEO）全干净；Python
> 进程无 360 注入 DLL；`iexplore.exe` 与 `ShellExecute('iexplore.exe')` 均静默失败、
> 无崩溃日志；4 种 COM 创建方式全 E_NOINTERFACE。该驱动**独立于 360 浏览器/安全卫士
> 用户态进程常驻内核**，所以「退出 360 浏览器」没用——须**彻底退出 360 安全卫士**
> （托盘退出 + 确认防护驱动卸载）才能恢复 IE11 COM。

**排查 IE11 COM 报 E_NOINTERFACE 时的正确顺序**：
1. 先看 360 安全卫士是否在跑（托盘 `360Tray`/`360Safe` 或 `360se.exe`）——须彻底退出；
2. 再看 `HKCU\...\Zones\3\2500=3`（保护模式已关）与
   `SecureProtocols` 含 TLS 1.0/1.1（本机 10912 已含）；
3. 都不想折腾 360 时，直接走 `erp.py login --http` / `open-forms ... --http` 无 COM 路径。

### Edge IE 模式的三条证伪证据（仍不采用）

1. **无策略、时灵时不灵**：`HKLM/HKCU\SOFTWARE\Policies\Microsoft\Edge` 均不存在。
2. **不提供 COM DOM**：IE 模式标签页不是 `IWebBrowser2`，无法 `.value/.click()`。
3. **不加载 Java 插件**：打开 RF.jsp 等 180s 仍是 `applet=[]`。

一句话：Edge IE 模式只解决「老 TLS 渲染」，不解决「自动化填表」和「拉起 Forms」。
完整记录见 `docs/DEV_PLAN.md` 第七节。

### 纯 HTTP 为什么可行

`erp_jws._opener()` 用 `ssl.SSLContext` 显式放开旧协议/套件：
`minimum_version=TLSv1` + `set_ciphers("DEFAULT@SECLEVEL=0")` +
`options |= 0x40000`，配 `CookieJar` 与 IE11 UA，绕开浏览器直接 POST
`AppsLogin` 表单（含 `_FORM_SUBMIT_BUTTON` 令牌）拿到 EBS 会话。
`erp_session.login()` 会再 GET 一次主页，实读「登录身份 HSA697」与
title「Oracle Applications 主页」做校验，避免「URL 到了、其实没登录」。

### 语言切换（简体中文）

HTTP 登录页默认已是中文（服务端返回 `lang="zh-CN-ORACLE9I"`）。
旧 IE11 路径用的中文入口仍保留：
`https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin?langCode=ZHS`。

## 三、前置条件 / 依赖

- 统一使用仓库虚拟环境 `E:\SKILLS\.venv`（依赖随 `E:\SKILLS\requirements.txt` 安装）
- 补齐依赖：
  ```bash
  E:/SKILLS/.venv/Scripts/python.exe -m pip install -r E:/SKILLS/requirements.txt
  ```
- 已装：playwright、cryptography、pywin32、pywinauto、pandas、rapidocr 等
- **两条登录路径**：① IE11（COM 自动化，须彻底退出 360 安全卫士）；② 纯 HTTP + javaws
  无 COM（`erp.py --http`，360 运行时也能用，**日常推荐**）。详见第二节
- **Java 8（jre1.8.0_191 32 位）** → 方式 A（`--http`）经 `javaws` 拉起 Forms 需要；
  IE11 方式另需 Java 插件（IE 承载 applet）
- 首次运行必须先设置加密密码（见下）

### ⚠️ 360 安全卫士会拦截 IE（详见第二节）
本技能日常推荐走 `erp.py --http` 无 COM 路径，与 360 完全无关；若要走 IE11 COM 路径，
须**彻底退出 360 安全卫士**（其内核驱动 `360AntiHijack64.sys` 会在内核态静默拦
`iexplore.exe` 启动）。用户日常开 360 时一律用 `--http` 即可，无需退出 360。

已知陷阱：`launchForm` 的新窗口若没落在 IE11 内，会被**系统默认浏览器（360）接管**——
360 是双核（兼容模式=IE 内核），真能把 applet 跑起来。触发条件是 **IE 进程被强制结束后状态损坏**。
对策：
1. 不要强杀 IE（open-forms 默认保留 IE 就是为此）；
2. `erp_navigator.detect_hijacked_windows()` **只记录提示，不干预其它浏览器的进程**。

## 四、铁律（跨模型，绝不可违反）

> **PowerShell 不支持 `&&` / `||`！** 命令体禁止写 `cd ... && python ...`，
> 必须用 Bash 工具的 `workdir` 参数传工作目录；且统一用
> `E:/SKILLS/.venv/Scripts/python.exe` 调脚本，禁止全局 `py` / `python`。

> **任何技能源文件（.py/.json/.md）禁止写入明文密码。** 密码只经 `erp_secure_config.py`
> 加密落盘为 `erp_runtime_config/passwords/erp_password.dat`（AES-256 密文）。
> 主密钥由 `USERNAME|COMPUTERNAME|WPOOL_ERP_V1` 派生，**仅本机本用户可解密**。

## 五、触发指令

> ### ✅ 单文件入口 `scripts/erp.py`（2026-11-04 新增，推荐）
> 打开 ERP + 打开 Forms 的核心链路已整合到 **一个文件** `scripts/erp.py`，
> 与测试/探测/旧代码分离（废弃脚本已归档到 `scripts/legacy/`）。
> 日常操作优先用它，避免与其它脚本混淆：
> ```bash
> E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login            # 登录
> E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py open-forms "职责" "功能"   # 登录+拉 Forms
> E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py list-funcs "职责"          # 列功能
> E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py logout           # 注销+关 IE
> E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py check            # 校验密码
> ```
> `erp.py` 内置：密码加密读取、IE11 登录、职责导航、launchForm 拉 Forms、
> FormsApp 驱动类，以及**360 运行检测**（检测到 360 会明确提示先退出，不给 traceback）。
> 旧的 `erp_ops.py`（含 doctor / login-http / ui-probe 等扩展命令）仍可用，互为兼容。

### 统一执行规则（跨模型）
```json
{
  "tool": "exec",
  "params": {
    "command": "E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login",
    "workdir": "E:\\SKILLS\\WHP-whirlpool-erp",
    "timeout": 180
  }
}
```

### 0) 自检（推荐先跑一次）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py doctor     # 登录通道诊断（连真 ERP，约 2s）
E:/SKILLS/.venv/Scripts/python.exe scripts/smoke_erp.py          # 离线自检（不连 ERP）
E:/SKILLS/.venv/Scripts/python.exe scripts/smoke_erp.py --live   # 连真 ERP 跑 Forms 全链路
```
`doctor` 一次性给出 IE11 COM / Edge IE 模式 / 纯 HTTP 三条通道的真实状态与选路结论，
**登录不顺时先跑它**。离线自检另含：依赖可导入 → 密码可解密 → 模板库 → 模板回归命中率。

### 1) 首次设置加密密码（必须，且只需一次）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_secure_config.py
# 交互输入 ERP 密码（输入不可见，明文不落盘）
```
> 当前账号 `hsa697` 的密码已由初始化脚本加密写入 `erp_password.dat`，一般无需重设。
> 若需重设，跑上面命令重新输入即可。

### 2) 校验密码能否解密（不打印明文）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py check
```

### 3) 登录 ERP（✅ 日常推荐：纯 HTTP 无 COM，360 运行时也能用）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login --http
```
- 纯 HTTP（urllib + 老 TLS），不碰 `iexplore.exe` / 不用 COM；**360 安全卫士在跑也稳定**；
  实测退出码 0，主页 `OA.jsp?OAFunc=OAHOMEPAGE`。`--keep` 保留会话（默认注销）。

### 3a) 主路径（IE11 COM，仅限彻底退出 360 安全卫士时）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login
```
- 退出码 0：IE11 → 中文登录页 → 填表 → 主页「Oracle Applications 主页」「登录身份 HSA697」
- 自动切简体中文（`--en` 保持英文）；`--keep` 保留 IE 窗口（默认关闭）
- 若报 E_NOINTERFACE：是 360 安全卫士内核驱动在拦（见第二节），彻底退出 360 安全卫士再试，
  或直接改用上一条 `login --http` 无 COM 路径。

### 3b) 备用路径（Playwright / Edge）
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py login
```
- 仅适用于服务器未来升级 TLS 的场景；当前老 TLS 下必然握手失败

### 4) 打开职责 / 拉起 Oracle Forms

**方式 A（✅ 日常推荐，360 运行时也能用：纯 HTTP + javaws 无 COM）**
```bash
# 拉起指定功能的 Forms 窗口（HTTP 登录 → 抓 applet → 本地 JNLP → javaws）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py open-forms "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台" --http --keep
```
流程：纯 HTTP 登录 → `fetch_applet` 抓 RF.jsp 参数（26 参数/9 jar）→ 本地生成 JNLP
→ `javaws`(JRE 1.8.0_191) 拉起 `SunAwtFrame` → **自动脱离父进程**（DETACHED，脚本退出后
窗口独立存活）→ 渲染真实业务界面。实测 10s 拉起、截图证实显示「MRP 计划员工作台」+ 工厂列表。
`--keep` 保留会话/窗口（默认注销）。

**方式 B（仅限彻底退出 360 安全卫士：IE11 COM）**
```bash
E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py open-forms "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台"
```
流程：IE11 登录 → 主页找职责 `<LI>` → **直接读其下的 javascript:launchForm(...) 链接**
（**不点职责**——实测会点崩 IE）→ 读出 launchForm URL → **自开 IE 窗口加载该 URL**
（**不点功能**——实测 window.open 会被系统默认浏览器 360 接管）→ Java applet 弹
`SunAwtFrame` Forms 窗口 → `pywinauto` 按 hwnd 连接（win32 backend）→ 界面元素识别。

**已验证实例**：「PO,SANYO合肥三洋物料计划员」→「MRP计划员工作台」
（function_id=1908, resp_id=51318, form=MRPFPPWB-394），弹出窗口
「Oracle Applications - 惠而浦（中国）ERP系统」，
子窗口「切换职责 - PO, SANYO合肥三洋物料计划员」，组织列表 MO1~MO6。

注意事项：
- **Forms 服务器网络约束（环境，非 360/代码）**：applet 经 `connectMode=servlet` 由 Web
  服务器 `erp:4446` 代理 Forms（`/forms/lservlet` HTTP 200）；`erp2.whirlpool-china.com`
  本机 DNS 解析不到属正常误导项。窗口能渲染真实业务界面，但**服务端 Forms 代理链路在
  本机偶发掉线**会导致 applet 连上后退窗——换时段或重试 `--http` 即可，纯 HTTP 登录不受影响。
- 若桌面已有旧 Forms 窗口，方式 B 默认**复用**它（同一 JRE 起第二个 applet 会失败）。
- Java 加载可能较慢（首次下载 jar），方式 B 默认等 150s，方式 A 等 180s。

### 5) IE 实例生命周期管理（免堆积，实测有效）
脚本开启的 IE 窗口 hwnd 登记在 `.cache/ie_instances.json`：
- **启动前**：自动关闭上一次遗留的实例（只关登记过的，**不碰用户自己开的 IE**）
- **结束后**：默认自动关闭（`login-ie11`、列功能场景）；`open-forms` 因 Forms 依赖
  默认保留，加 `--close-ie` 可一并关闭
- 关闭手段逐级升级并确认真的关掉：`COM Quit()` → `WM_CLOSE` → 强制结束进程
  （承载 Java applet 的 IE 会拒绝前两种温和方式，只能强杀）
- 需要保留窗口时加 `--keep`（仅 login-ie11 支持）

⚠️ 强杀 IE 会让下一次运行的 IE 状态异常（首屏空白、新窗口被 360 接管）。
若遇到登录失败且 `title=''`，稍等或重跑一次即可恢复；根本对策是**不要频繁强杀**
（open-forms 默认保留正是为此）。

### 6) 采购申请全流程（N 行/单 + 多单批量）

主脚本：`scripts/erp_flow_requisition_full.py`
一条命令跑完：登录 → 逐张开单 → 逐行录入 → **校验** → 保存 → 提交审批 → 退出。

**物料编码与数量每次由调用方传入，脚本内不写死。**

```bash
# A. 一张单里 N 个物料（--req 出现一次 = 一张单）
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-whirlpool-erp/scripts/erp_flow_requisition_full.py \
    --req "零头补录入库|3012324101140:1,3000000000000:2"

# B. 多张单，各自说明（每张可 1 行或 N 行）
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-whirlpool-erp/scripts/erp_flow_requisition_full.py \
    --req "零头补录入库|3012324101140:1" \
    --req "备用件补库|3000000000001:3,3000000000002:1"

# C. JSON 计划（每行可单独价格/日期）
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-whirlpool-erp/scripts/erp_flow_requisition_full.py --plan plan.json

# D. 单行简写（兼容旧用法）
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/WHP-whirlpool-erp/scripts/erp_flow_requisition_full.py --item 3012324101140 --qty 1

# E. 只解析计划，不连 ERP（排错/确认写法）
... --req "说明|物料:数量" --dry-run

# F. 离线校验 verify 逻辑（用历史截图，不产生单据）
... --self-test
```

- 简写行语法：`物料[:数量[:价格[:需要日期]]]`，行之间用 `,`，说明与行之间用 `|`
- 行位置不写死：**行高由截图里的网格横线实时测量**（本轮实测 36px），第 2..N 行直接按实测坐标点进去录
- 校验口径：数量/价格用「单元格像素 + 连通域位数」（Forms 的 `1` 被 OCR 读成 `T`，不能只靠 OCR）；
  说明/日期/组织/地点/子库存用 OCR；物料以 EBS 自动带出的行说明为证据
- 校验不过 → 自动补填 3 轮 → 仍缺则**整单不保存**，退出码 7，保留现场
- 多单：每张跑完关掉该 applet 窗口再开下一张；某张失败即停，不再继续
- 退出码：0 成功；2 登录失败；7 校验未过；10 有单据未完成
- 成功才自动注销+关 IE；任何失败/中断都保留现场（`--keep-ie` 可强制保留）
- 演练：`--stop-before-save` 只录第一张并校验，不保存

## 六、脚本清单

> ### 目录结构（2026-11-04 整理）
> - **核心（推荐直接使用）**：`scripts/erp.py` —— 打开 ERP + 打开 Forms 全链路单文件。
> - **旧模块（保留兼容）**：`erp_ie11.py` / `erp_navigator.py` / `erp_forms.py` /
>   `erp_common.py` / `erp_secure_config.py` 等，`erp.py` 是其整合后的等价实现。
> - **废弃归档**：`scripts/legacy/` —— 37 个探测/临时脚本（`_probe_*`、`_tmp_*`、
>   `diag*`），仅作历史留档，不再使用。

| 文件 | 说明 |
|------|------|
| `scripts/erp.py` | **✅ 单文件主入口（2026-11-04 新增，推荐）**：整合「IE11 登录 + 职责导航 + launchForm 拉 Forms + FormsApp 驱动 + 密码读取」，内置 360 运行检测；CLI 含 login/open-forms/list-funcs/logout/setup/check |
| `scripts/erp_session.py` | **纯 HTTP 登录 + 通道诊断**：`doctor` 评估 IE11 COM / Edge IE 模式 / 纯 HTTP；`login(verify=True)` 做 HTTP 登录并实读主页校验，返回可复用的 opener（**备用通道，不承载 Forms**） |
| `scripts/erp_jws.py` | **Forms 侧备用链路**：纯 HTTP 登录 + 抓 RF.jsp applet 参数 + 生成本地 JNLP + `javaws` 启动 + Java 安全警告自动确认 + 旧 TLS 覆盖 |
| `scripts/erp_secure_config.py` | AES-256 密码管理 + 设置/校验工具（明文不落盘；`erp.py` 已内置等价实现） |
| `scripts/erp_common.py` | 浏览器创建（msedge / 360 CDP 附加）、storage 状态、安全输出、读密码 |
| `scripts/erp_login.py` | Playwright 登录 EBS（备用，老 TLS 下失败） |
| `scripts/erp_ie11.py` | **IE11（COM）登录主路径**：老 TLS 兼容 + 简体中文登录页 + 经典 OAF 表单填写；`open_and_login()` 返回 ie 对象供导航复用（**单实例单次导航**，坏了自动重建） |
| `scripts/erp_navigator.py` | **职责导航 + Forms 拉起**：读职责下的功能链接（不点崩 IE）、读 launchForm URL、**自开 IE 窗口加载 Forms**、等 SunAwtFrame 新窗口、按 hwnd 连接 |
| `scripts/erp_forms.py` | `FormsApp` 驱动封装（`connect_by_hwnd` win32 后端 + 键盘/菜单/截图）；`launch_jnlp` 保留作备用 |
| `scripts/erp_ui.py` | **界面元素识别引擎**：置前截图、多尺度模板匹配、相对坐标换算、点击、OCR 钩子 |
| `scripts/erp_tpl.py` | 模板库管理：裁剪模板 / 列出 / 查看 / 离线 verify / OCR probe |
| `scripts/erp_ui_test.py` | 模板多变体回归测试（缩放/平移/亮度/JPEG） |
| `scripts/smoke_erp.py` | 自检脚本（离线自检 + `--live` 真机全链路） |
| `scripts/erp_ops.py` | CLI 编排入口（**login-ie11 主路径** / login-http 备用 / login / open-forms / list-funcs / ui-probe / ui-click / logout / cleanup / doctor） |
| `scripts/erp_flow_requisition_full.py` | **采购申请全流程**：登录→开单→N 行录入→校验→保存→提交审批→退出；支持多单批量（`--req` 可重复 / `--plan`），`--self-test` 离线校验 |
| `scripts/config_example.py` | 配置模板（**不含明文密码**，首次运行自动生成 `erp_runtime_config.json`） |
| `scripts/legacy/` | **废弃归档目录**：37 个探测/临时脚本（`_probe_*`、`_tmp_*`、`diag*`），历史留档 |
| `assets/templates/<form_id>/` | 界面元素模板库（`*.png` + `meta.json`） |
| `docs/DEV_PLAN.md` | 开发计划与进度（P0~P8 阶段、风险、里程碑） |

## 七、操作 Oracle Forms 的二次开发指引

**关键限制（实测）**：Forms 窗口是 Java AWT（`SunAwtFrame`），对 UIA backend
只暴露 TitleBar，内部全是自绘控件，**无法按控件名枚举/点击**。驱动方式：
键盘（`type_keys`）、菜单（`menu_select`）、坐标点击、截图核对。

### 7.1 界面元素自动识别（图像模板法，已实测跑通）

需求「按屏幕大小/位置不同自动识别按钮位置」的实现方式：

1. 截图：`app.window.capture_as_image()`（**必须先把窗口置前**，否则会截到
   遮挡窗口的内容——实测被 Excel 挡住时截出来是 Excel）。
2. 定位：OpenCV 多尺度模板匹配（16 档 0.60~1.40，TM_CCOEFF_NORMED），
   模板存 `assets/templates/<form_id>/<语义名>.png`，`meta.json` 记参考矩形
   与基准图尺寸（同尺寸时只在 ROI 内搜，既快又不易误命中）。
3. 点击：定位结果表达为**相对窗口图像的矩形**，点击时用 `window.rectangle()`
   实时换算屏幕坐标 → 窗口移动/分辨率变化/多显示器都不影响。

```python
import erp_navigator, erp_ui

app = erp_navigator.open_function("PO,SANYO合肥三洋物料计划员", "MRP计划员工作台")
form = erp_ui.form_id("PO,SANYO合肥三洋物料计划员", "MRP计划员工作台")

erp_ui.click(app, "确定", form)      # 定位 + 点击（定位失败自动置前重试）
found = erp_ui.locate_all(app, form)  # 一次截图识别全部元素
for name, r in found.items():
    print(name, r.x, r.y, r.w, r.h, r.score)   # 相对坐标 + 置信度
```

实测结果（2026-10-21）：「查找 / 确定 / 取消 / 打开(O)」四个元素置信度均 **1.000**，
离线回归（缩放/平移/亮度/JPEG 变体）命中率 **100%**。

### 7.2 模板库维护
```bash
# 从截图裁一个模板（自动去白边，并记录参考矩形）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py crop logs/forms_window.png "PO,SANYO合肥三洋物料计划员__MRP计划员工作台" 查找 140 580 55 45
# 列出全部模板库 / 查看某库
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py list
# 离线回归（在某张截图上匹配全部模板）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py verify logs/forms_window.png "<form_id>"
# 多变体回归（缩放/平移/亮度/JPEG）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ui_test.py logs/forms_window.png "<form_id>"
```
> `<form_id>` = `erp_ui.form_id(职责名, 功能名)`，即「职责__功能」。
> 新表单首次适配：截图 → 裁 3~5 个关键控件 → 跑回归 → 即可。

### 7.3 常用命令
```bash
# 拉起 Forms 并识别界面元素（打印相对坐标 + 置信度）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py ui-probe "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台"
# 拉起 Forms 并按名字点击某个元素（闭环验证）
E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py ui-click "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台" 查找
```

### 7.4 键盘/菜单驱动（控件级识别不可用时的兜底）
```python
app.screenshot("forms.png")     # 截图核对当前界面（最可靠的“读屏”手段）
app.window.set_focus()
app.type_keys("{F7}")           # Oracle Forms 常用: F7 查询进入/ Ctrl+F11 执行查询
app.select_menu("文件->打开")    # 选菜单
```
> 更细粒度的控件级自动化需启用 **Java Access Bridge**：
> 以管理员运行 `jabswitch /enable` 后 pywinauto 才能通过 java backend 识别 Swing 控件。
> 当前 32 位 Java + 64 位 Python 组合会有 UserWarning，基础操作（焦点/键盘/截图）不受影响。

## 八、异常处理 / 已知坑

### 8.1 ⚠️ IE11 的三个"崩溃坑"（2026-10-21 定位到根因，务必遵守）
1. **同一 IE 实例内第二次 Navigate → IE 进程崩溃**，之后所有 COM 调用报
   `RPC 服务器不可用`。
   → 对策：**一个实例只导航一次**；要换入口（尤其切中文登录页）就
   **重建 IE 实例**。`erp_ie11.open_and_login()` 已按此实现。
2. **对职责 <A> 调用 click() → IE 崩溃**。
   → 对策：**不点职责**。EBS 的职责菜单树按会话保持展开状态，
   直接读该职责 <LI> 下的 `javascript:launchForm(...)` 链接即可
   （`erp_navigator.expand_responsibility()` 已改为「先读、点不动才点」）。
3. **功能链接的 `window.open` 被系统默认浏览器（360）接管**，applet 起不来。
   → 对策：**不点功能链接**，只读出 launchForm URL，然后
   **自己新开一个 IE 窗口导航到该 URL**，applet 必定跑在 IE11 的 Java 插件里
   （`erp_navigator.open_forms_window()`）。

### 8.2 其它已知坑
- **`com_error(-2147467262, "不支持此接口")` / E_NOINTERFACE（最常见，根因已定位）**：
  **根因是 360 安全卫士的「防劫持」内核驱动 `360AntiHijack64.sys` 在内核态静默拦截
  `iexplore.exe` 启动**（注册表/COM 注册本身完好，非「Win11 停用 IE11」）。
  该驱动独立于 360 浏览器常驻，**须彻底退出 360 安全卫士**才能恢复 IE11 COM
  （2026-11-04 18:xx 决定性诊断；此前「360chromeie 抢占 COM、360 退出即恢复」为误判）。
  → **先彻底退出 360 安全卫士**；不想折腾就直接走 `erp.py login --http` /
  `open-forms ... --http` 无 COM 路径（360 运行时也能用，且承载 Forms）。
- **⚠️ Forms 窗口被误关（2026-11-04 事故，已修复）**：`cleanup_automation_leftovers()`
  曾用「窗口坐标 < -20000」判僵尸，但**最小化窗口的坐标同样是 -32000**，
  结果把用户正在使用的 Forms 会话误关。
  现已改为 `dry_run=True` 默认**只报告**、Forms 窗口**一律不自动关闭**、
  且不再强杀宿主进程；只有 `erp_ops.py cleanup --force` 才关 360 承接窗口。
- **TLS 握手失败（`ERR_SSL_VERSION_OR_CIPHER_MISMATCH`）**：服务器只认老 TLS，
  Edge / Playwright / 普通 Chromium 必然失败。IE11 走 SCHANNEL 能过；
  纯 HTTP 通道用 `DEFAULT@SECLEVEL=0` + `options |= 0x40000` 解决，无需改系统注册表。
- **IE COM 属性全部报错（Document/HWND/Busy 均失败）**：IE「Internet 区域」
  保护模式没关 → 设 `Zones\3` 的 `2500=3`；或 360 安全卫士在跑（见上一条 E_NOINTERFACE）。
- **IE `window.eval` 报 0x80020101**：该页面 eval 不可用（IE11 COM 怪癖），
  已改用纯 COM DOM 操作（getElementById + .value + .click()），勿改回 eval。
- **登录后无主页特征**：EBS 页面结构可能变化，需更新登录脚本的选择器。
- **找不到职责/功能**：职责名是主页 `<LI>` 里的链接文字；功能项在职责节点下
  才出现（`javascript:launchForm(...)`）。名字必须与界面文字一致。
- **等不到 Forms 窗口**：查 IE 是否弹了 Java 安全/证书提示框（需人工点一次信任）；
  或 Java 插件被禁用；调大 timeout。
- **Forms 窗口起不来第二个**：同一 JRE 里再起一个 applet 会失败 →
  `open_function()` 默认 `reuse_existing=True`，直接复用已打开的 Forms 窗口。
- **截图像素不对（明明界面在，模板却匹配不上）**：窗口被别的窗口遮挡，
  BitBlt 截到的是遮挡者。`erp_ui.capture()` 已强制先置前窗口。
- **Forms 窗口 UIA 枚举不到控件**：正常现象（SunAwtFrame 自绘），用 win32 backend
  的键盘/菜单/截图驱动；要控件级识别需装 Java Access Bridge。
- 退出码：登录成功 `0`；IE11 登录失败 `2`；密码未设置 `1`；导航/拉起失败 `3/4`；
  模板库缺失 `5`；界面元素未识别 `6`。

## 九、开发备注

- **2026-11-04 登录通道最终结论（两次复核 + 决定性内核态诊断）**：
  ① IE11 COM 在**彻底退出 360 安全卫士**后完全可用（`open-forms` 实测退出码 0 全链路）；
  ② **纯 HTTP + javaws 无 COM 路径**（`erp.py --http`）在 360 运行时也能登录并拉起
  真实 Forms 界面，是日常推荐路径。根因是 360 安全卫士内核驱动拦截 `iexplore.exe`
  （非「360chromeie 抢占 COM」的旧误判）。详见第二节。
  Edge IE 模式仍证伪；纯 HTTP（`erp_session.py` / `login-http`）保留为备用。
  详见第二节与 `docs/DEV_PLAN.md` 第七节。
- 主密钥 salt：`WPOOL_ERP_V1`（与 download 技能的 `WPOOL_REPORT_V1` 区分，互不通用）
- 密码文件：`erp_runtime_config/passwords/erp_password.dat`（仅密文，32 字节 = 16 IV + 16 密文）
- EBS 服务器 IP：192.6.200.136（公网 TCP 可达，但只认老 TLS）
- 关键 URL：
  - 登录页（英文）：`/OA_HTML/OA.jsp?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG...`
  - 登录页（简体中文）：`/OA_HTML/AppsLogin?langCode=ZHS`
  - 注销：`/OA_HTML/OALogout.jsp`
- 经典 OAF 登录页字段：`usernameField` / `passwordField` / `SubmitButton`（中英文界面 id 相同）
- 360 浏览器版本：17.1.1118.64（Chrome/148 内核）；**不用 360**（运行时干扰 IE11 COM）
- Playwright 路径（Edge）仅作备用；老 TLS 下主路径是 IE11（SCHANNEL），备用是纯 HTTP
- **Forms 技术档案（appsbase.htm 实测提取）**：
  - applet：`oracle/apps/fnd/formsClient/FormsLauncher.class`，codebase `/OA_JAVA/`，
    jars：fndforms/fndformsi18n/fndewt/fndswing/fndbalishare/fndaol/fndctx/fndlist
  - 连接：`serverHost=erp2.whirlpool-china.com serverPort=9001 connectMode=servlet`
  - serverArgs：`module=/app01/erpprod_app/apps/apps_st/appl/fnd/12.0.0/forms/US/FNDSCSGN fndnam=APPS`
  - 功能选择经 serverURL 的 gp/gv 传递：resp=SANYO_PO_PLANER、function=MRPFPPWB-394、
    dbc=prod、icx_ticket=<登录会话票据>
  - Java 客户端：JRE 1.8.0_191（32 位）`C:\Program Files (x86)\Java\jre1.8.0_191`；
    本机无 JDK（无 appletviewer）；javaws 在 `C:\Program Files (x86)\Common Files\Oracle\Java\javapath\`
  - 服务器所有 frmservlet URL 变体均返回 JInitiator HTML（不返回 JNLP），
    `appsweb.cfg` 404 —— **服务端不直出 JNLP**。但 2026-11-03 已验证可
    **本地生成 JNLP**（`erp_jws.build_jnlp()`）再用 `javaws` 拉起 applet 窗口
    （`logs/jws_start4.log`，12s 拿到 hwnd）。旧结论「JNLP 勿再尝试」仅指服务端直出；
    本地生成路线可用，但 Forms 连接层尚未闭环（停在 ORACLE 启动图，
    `logs/probe_console.log`），仍在排查
