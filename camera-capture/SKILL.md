---
name: camera-capture
description: >
  摄像头拍照 — 打开电脑摄像头拍摄一张照片并保存。
  Triggers: 拍照, 摄像头拍照, 拍照片, 摄像头.
---

# 摄像头拍照

## 铁律
- **拍照请求必须调用此技能**，禁止用 `screen-capture` 的截图脚本代替（那是截屏，不是摄像头）
- **拍照完成后必须把照片推送给用户**，即在最终回复里输出 `MEDIA:<绝对路径>`
- **脚本输出中的 `MEDIA:` 行不能直接送达微信** — bash 工具不在 Hermes 的自动补挂白名单里（`run.py` 的 `_AUTO_APPEND_MEDIA_TOOL_NAMES` 只含 `text_to_speech` / `image_generate`）
- **必须由模型（你）亲手把那行写进最终回复** — Hermes 网关 `extract_media()` 扫描「模型最终回复的文本」

## ⚠️ 推送机制（必读，不照做照片发不出去）

照片不是由脚本直接推送的。**bash 工具不在 Hermes 的自动补挂白名单里**
（`run.py` 的 `_AUTO_APPEND_MEDIA_TOOL_NAMES` 只含 `text_to_speech` / `image_generate`），
所以脚本 stdout 里那行 `MEDIA:` **不会**被自动送到微信。
真正干活的是 **Hermes 网关 `extract_media()` 扫描「模型最终回复的文本」**——
也就是必须由模型（你）亲手把那行写进回复里。

回复格式要求（`MEDIA_TAG_CLEANUP_RE` 实测结果）：

| 写法 | 结果 |
|------|------|
| 独立成行，行首无任何字符 | ✅ 送达 |
| 包在 ` ``` ` 代码块内 | ❌ **丢弃**（网关屏蔽代码块） |
| 前面加 `>` / `>>>` 引用符 | ❌ **丢弃** |
| 包在行内反引号 `MEDIA:`...`` | ✅ 送达 |
| 加 `**` 强调 / 放在列表项里 | ✅ 送达 |

**正确写法**——`MEDIA:` 顶格单独成行，前后不要有任何字符：

拍照完成，尺寸 640x480，大小 62.0 KB。
MEDIA:E:\SKILLS\camera-capture\images\camera_20260930_225435_0.jpg

**错误写法**（照片丢失，用户只看到一坨代码块）：

```
拍照完成
MEDIA:E:\SKILLS\camera-capture\images\camera_20260930_225435_0.jpg
```

路径必须是**绝对路径**且带**已知扩展名**（png/jpg/mp4/pdf/xlsx…），
`E:\...` 开头合法，裸文件名不合法。

## 触发指令

### "拍照" / "拍张照" / "摄像头拍照" / "打开摄像头拍一张"
```bash
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/camera-capture/scripts/camera_capture.py
```

### 倒计时 3 秒后拍（需要用户调整姿势/入镜时）
```bash
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/camera-capture/scripts/camera_capture.py --delay 3
```

### 水平翻转（前置摄像头文字镜像时使用）
```bash
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/camera-capture/scripts/camera_capture.py --mirror
```

## 参数
| 参数 | 说明 | 默认 |
|------|------|------|
| `--index N` | 摄像头索引（0 = 系统默认摄像头） | `0` |
| `--delay N` | 拍摄前等待 N 秒（倒计时） | `0` |
| `--warmup N` | 曝光预热秒数 | `1.5` |
| `--mirror` | 水平翻转画面 | 关闭 |
| `--format jpg\|png` | 图片格式 | `jpg` |
| `--width N` / `--height N` | 强制分辨率 | 摄像头默认 |
| `--list` | 列出可用摄像头后退出 | — |

## 输出
- 文件保存至 `E:\SKILLS\camera-capture\images\camera_YYYYMMDD_HHMMSS_<index>.jpg`
- 脚本最后一行输出 `MEDIA:<路径>`，前面两行是 `[DELIVER]` 提示
- **你必须把最后那行 `MEDIA:` 顶格单独写进最终回复**（格式要求见上方「推送机制」）
- 正确响应示例（注意 `MEDIA:` 那一行不在代码块里）：

拍照完成：640x480，62.0 KB
MEDIA:E:\SKILLS\camera-capture\images\camera_20260930_225435_0.jpg

## 依赖
- Python 3.11+（统一使用 `E:\SKILLS\.venv` 虚拟环境）
- `opencv-python` 库（`.venv` 已安装）
- 摄像头设备 + Windows 隐私设置允许桌面应用访问摄像头

## 环境
```bash
# 依赖安装/升级统一走 E:\SKILLS\.venv
E:/SKILLS/.venv/Scripts/python.exe -m pip install opencv-python
```
**禁止使用全局 `py` 执行本技能脚本** —— 全局解释器与 `.venv` 的依赖版本可能不一致。

## 工作原理
1. 用 `cv2.VideoCapture(index, CAP_DSHOW)` 打开摄像头，失败时回退 `CAP_ANY`
2. 丢弃预热期帧，等待自动曝光收敛
3. 持续读取直到 `std > 3`，**过滤摄像头冷启动返回的纯色空帧**（灰度全屏）
4. 按需水平翻转（前置摄像头自拍用），保存为 JPG/PNG

## 文件结构
```
E:\SKILLS\camera-capture\
├── SKILL.md                  ← 技能定义
├── scripts\
│   └── camera_capture.py     ← 拍照脚本
└── images\                   ← 照片输出目录
    └── camera_*.jpg
```

## 异常处理
- **无法打开摄像头**：先跑 `--list` 看可用索引，再用 `--index` 指定；仍失败则提示检查设备连接与 Windows「允许桌面应用访问摄像头」
- **画面纯色（std 接近 0）**：摄像头冷启动或被其他程序（微信/钉钉/Teams 视频）占用，关闭占用程序后重试
- **画面过暗**：加 `--warmup 3` 给摄像头更长预热时间
- **拍照前需要准备时间**：加 `--delay N`
- **自拍左右反了**：加 `--mirror`
- 脚本用完即 `release()`，不会遗留摄像头占用

## 注意事项
- 前置摄像头画面默认是左右镜像的，看文字反了就加 `--mirror`
- 拍照时需要用户在场，建议配合 `--delay` 留出调整时间
- 每次拍照生成一个新文件，不覆盖历史照片
- 一次只拍一张，需要多张请重复调用
