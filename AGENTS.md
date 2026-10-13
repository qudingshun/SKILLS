# AGENTS.md — E:\SKILLS 仓库开发约定

opencode / Claude Code 等 AI 在本仓库开发代码时**必须**遵守以下约定。

## 铁律 1：统一使用仓库虚拟环境

所有 Python 脚本**一律**用这个解释器执行：

```
E:\SKILLS\.venv\Scripts\python.exe
```

**禁止**使用全局 `py`、`python`、`python3`，也禁止 `pip install` 装到全局环境。

原因：全局 Python（`AppData\Local\Programs\Python\Python311`）与 `.venv` 的依赖版本不一致，
会出现"我这儿能跑、那边 ImportError"的随机故障。

### 正确写法

```bash
# 绝对路径脚本
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/<skill>/scripts/<script>.py

# 相对路径脚本（workdir 设为该技能目录）
E:/SKILLS/.venv/Scripts/python.exe scripts/<script>.py

# 装依赖
E:/SKILLS/.venv/Scripts/python.exe -m pip install <包名>
```

### 新增技能时的硬性要求

1. 技能目录下必须有 `SKILL.md`，写清触发词、执行命令、输出路径、异常处理
2. `SKILL.md` 里的执行命令**只能**写 `.venv` 解释器路径
3. 脚本内不要写死解释器路径，但**输出文件路径**要写死绝对路径（如 `E:\SKILLS\<skill>\images\`）
4. 新依赖**必须**同时登记到 `E:\SKILLS\requirements.txt`
5. 产物类输出（图片、报表）最后一行打印 `MEDIA:<绝对路径>`，供微信/桌面端推送

## 铁律 2：共享依赖集中维护

`E:\SKILLS\requirements.txt` 是**唯一**的依赖清单。所有技能共用 `.venv`，不搞技能私有 venv。

新增依赖后必须执行：

```bash
E:/SKILLS/.venv/Scripts/python.exe -m pip install -r E:/SKILLS/requirements.txt
```

## 铁律 3：验证后再交付

改动脚本后必须用 `.venv` 解释器**实际跑一次**，确认输出正常（含文件大小、尺寸等），
不能只看代码就汇报"完成"。

## 常用命令速查

```bash
# 看某技能实际用了什么包
E:/SKILLS/.venv/Scripts/python.exe -c "import cv2, mss, PIL; print('ok')"

# 列出全部已装依赖
E:/SKILLS/.venv/Scripts/python.exe -m pip list

# 截图
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/screen-capture/scripts/screen_capture.py

# 摄像头拍照
E:/SKILLS/.venv/Scripts/python.exe E:/SKILLS/camera-capture/scripts/camera_capture.py
```

## Windows 注意事项

- 调 `bash` 工具时用 `workdir` 参数切目录，**不要**在命令体里写 `cd ... && ...`
- PowerShell 是 5.1，**不支持 `&&`**，用 `;` 或 `if ($?) { }`
- 跑 Python 前设 `$env:PYTHONIOENCODING='utf-8'`，否则中文输出在控制台显示为乱码（文件内容本身没问题）
- 中文路径在 PowerShell 里要加引号

## 仓库现状备忘

- `screen-capture/` 目录里有**两个** `screen_capture.py`：
  - `scripts\screen_capture.py` — mss 版，**SKILL.md 指向的就是这个，能用**
  - 根目录 `screen_capture.py` — cv2 版，**孤儿文件，SKILL.md 未引用，代码有 bug，不要调用**
- `screen-capture/` 与 `camera-capture/` 尚未纳入 git 跟踪
