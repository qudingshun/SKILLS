---
name: screen-capture
description: >
  屏幕截图 — 检测所有显示器并截图合并为一张。
  Triggers: 截图, 屏幕截图.
---

# 屏幕截图

## 铁律
- **截图请求必须调用此技能**，禁止用 `browser_exec` 的 `capture_screenshot()` 替代
- **截图完成后必须将文件发送给用户**（`MEDIA:` 路径），不可只报告路径
- **脚本输出中的 `MEDIA:` 行不能直接送达微信** — bash 工具不在 Hermes 的自动补挂白名单里（`run.py` 的 `_AUTO_APPEND_MEDIA_TOOL_NAMES` 只含 `text_to_speech` / `image_generate`）
- **必须由模型（你）亲手把那行写进最终回复** — Hermes 网关 `extract_media()` 扫描「模型最终回复的文本」

## 触发指令

### "截图" / "屏幕截图" / "截屏"
```bash
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/screen-capture/scripts/screen_capture.py
```

## 输出
- 文件保存至 E:\SKILLS\screen-capture\images\screenshot_YYYYMMDD_HHMMSS.png
- 分辨率：2560x1600（双屏合并）
- 使用后通过 MEDIA: 路径将文件发送给用户（微信/桌面端）

## 依赖
- Python 3.11+（统一使用 `E:\SKILLS\.venv` 虚拟环境）
- `mss` 库（`.venv` 已安装）
- `Pillow` 库（`.venv` 已安装）

## 工作原理
1. 使用 `mss.MSS()` 检测所有物理显示器
2. 自动获取虚拟屏幕尺寸（所有显示器拼接后的总区域）
3. 一次性截取整个虚拟屏幕
4. 保存为 PNG 图片到 `images/` 目录

## 文件结构
```
E:\SKILLS\screen-capture\
├── SKILL.md              ← 技能定义
└── scripts\
    └── screen_capture.py ← 截图脚本
└── images\               ← 截图输出目录
    └── screen_*.png
```

## 注意事项
- 双屏并排时，宽度 = 左屏宽度 + 右屏宽度
- 截图为全屏截图，不需要手动指定区域
- 发送格式：`MEDIA:E:\SKILLS\screen-capture\images\screen_YYYYMMDD_HHMMSS.png`
