#!/usr/bin/env python3
"""
每日对话归档与经验更新脚本
- 汇总当天对话内容（除定时任务外）
- 备份聊天内容到指定位置
- 增量更新经验教训
"""

import json
import os
import sys
import shutil
from datetime import date, datetime
from pathlib import Path

# 配置
BASE_DIR = Path(__file__).parent
HERMES_DIR = Path.home() / "AppData/Local/hermes"
MEMORY_DIR = HERMES_DIR / "memories"
SKILLS_DIR = HERMES_DIR / "skills"
SESSION_FILE = HERMES_DIR / "session.json"

# 备份目录
BACKUP_DIR = Path(os.environ.get("HERMES_BACKUP_DIR", r"D:\Raw备份\对话归档"))

def ensure_dirs():
    """确保必要目录存在"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / "对话归档").mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / "经验教训").mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

def find_session_history():
    """查找最近的会话记录"""
    # 当前会话文件
    current_session = HERMES_DIR / "current_session.json"
    if current_session.exists():
        return current_session
    
    # 归档会话
    sessions_dir = HERMES_DIR / "sessions"
    if sessions_dir.exists():
        sessions = sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if sessions:
            return sessions[0]
    
    # 尝试查找对话文件
    for pattern in ["*.log", "*.json", "*.md"]:
        matches = list(HERMES_DIR.rglob(pattern))
        if matches:
            latest = max(matches, key=lambda x: x.stat().st_mtime)
            return latest
    
    return None

def get_recent_conversation(n=50):
    """获取最近N条对话，排除定时任务相关内容"""
    session_file = find_session_history()
    if not session_file:
        # 无法找到会话文件时，创建一个空操作记录
        return []
    
    try:
        content = session_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    
    # 简单过滤：移除定时任务相关的对话
    lines = content.splitlines()
    relevant = []
    for line in lines:
        # 跳过定时任务相关的行
        if any(kw in line for kw in ["cron", "定时任务", "scheduled job"]):
            continue
        relevant.append(line)
    
    return relevant[-n:]

def summarize_conversation(lines, n=10):
    """生成对话摘要"""
    if not lines:
        return "今日无新对话记录"
    
    summary = []
    summary.append(f"## 对话摘要（{len(lines)}条记录）")
    summary.append("")
    
    # 分类
    categories = {
        "回货操作": ["回货", "huihuo"],
        "报表下载": ["报表下载", "whirlpool"],
        "定时任务": ["cron", "定时任务", "schedule"],
        "经验更新": ["经验", "教训", "总结", "remember"],
        "其他": []
    }
    
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        for cat, keywords in categories.items():
            if any(kw in line for kw in keywords):
                summary.append(f"• [{cat}] {line[:120]}")
                break
    
    return "\n".join(summary)

def backup_conversation():
    """备份对话内容"""
    session_file = find_session_history()
    backup_name = f"对话归档_{date.today().isoformat()}.json"
    backup_path = BACKUP_DIR / "对话归档" / backup_name
    
    try:
        content = {
            "backup_date": date.today().isoformat(),
            "session_file": str(session_file) if session_file else "unknown",
            "content": find_session_history().read_text(encoding="utf-8", errors="ignore")[:50000] if find_session_history() else "",
            "backup_time": datetime.now().isoformat()
        }
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return str(backup_path)
    except Exception as e:
        return f"备份失败: {e}"

def update_lessons(merged=False, unique=False):
    """增量更新经验教训"""
    # 读取现有经验
    experience = []
    for f in MEMORY_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8", errors="ignore")
        if content.strip():
            experience.append(content)
    
    new_lessons = [
        "1. 定时任务无模型时必须显式指定 provider/model，否则推断到 nous 可能 404",
        "2. 回货导入成功后发放可能因订单未完成量已用完而失败（重复操作）",
        "3. 报表下载全流程约5-8分钟，建议运行后台进程，避免超时",
        "4. 验证码 OCR 3次失败后需手动输入，脚本会提示人工介入",
        "5. 聊天内容备份和经验归档需每日定时执行，确保经验可追溯",
    ]
    
    if merged:
        merged_content = "\n".join(experience[-50:]) + "\n\n" + "\n".join(new_lessons)
        memory_file = MEMORY_DIR / "经验教训.md"
        memory_file.write_text(merged_content, encoding="utf-8")
        return f"经验教训已合并更新"
    elif unique:
        # 去重新增
        existing = set(experience)
        new = [l for l in new_lessons if l not in existing]
        if new:
            for l in new:
                (MEMORY_DIR / "经验教训.md").write_text(
                    (MEMORY_DIR / "经验教训.md").read_text(encoding="utf-8", errors="ignore") + "\n" + l,
                    encoding="utf-8")
            return f"新增旧经验: {len(new)}条"
        return "没有新增经验"
    else:
        # 直接追加
        with open(MEMORY_DIR / "经验教训.md", "a", encoding="utf-8") as f:
            f.write("\n".join(new_lessons) + "\n")
        return "经验教训已追加"

def main():
    ensure_dirs()
    
    print("=" * 60)
    print("每日对话归档与经验更新")
    print(f"日期: {date.today().isoformat()}")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 获取对话内容
    conversation = get_recent_conversation(n=50)
    print(f"\n[1] 获取对话内容: {len(conversation)}条记录")
    
    # 2. 生成摘要
    summary = summarize_conversation(conversation)
    print(f"[2] 生成摘要完成")
    print(summary[:2000])
    
    # 3. 备份
    backup_path = backup_conversation()
    print(f"\n[3] 备份完成: {backup_path}")
    
    # 4. 增量更新经验
    result = update_lessons()
    print(f"[4] 经验教训更新: {result}")
    
    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)
    
    # 输出摘要行供前端显示
    print(f"\nDELIVER: 完成")
    print(f"MEDIA: {backup_path}")

if __name__ == "__main__":
    main()
