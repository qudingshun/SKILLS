#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw Skill Installer — Bionic 技能安装工具
========================================================

用法:
    pip install openai-cli  # 如果还没安装的话
    
    # 从 curated skills 安装（推荐）
    python tools/install_skill.py --path "openai/skills/.curated" --name "reporting-tools"
    
    # 从 GitHub repo 安装（包含私有仓库）
    python tools/install_skill.py --repo openai/skills --path "skills/.curated/reporting-tools"
    
    # 本地目录
    python tools/install_skill.py --path ./E:/SKILLS/tools/skills
    
    # 安装单个技能（只复制配置和入口，不复制整个 skills 文件夹）
    python tools/install_skill.py --name reporting-tools

示例:
    # 一次性安装所有 4 个技能（从本地目录）
    python tools/install_skill.py --path ./E:/SKILLS/tools/skills
    
    # 安装单个：产销存报表
    python tools/install_skill.py --name "reporting-tools"
    
    # 安装单个：惠而浦物料查询
    python tools/install_skill.py --name "material-inventory-check"
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path


def find_skills_in_dir(skill_dir: str, target_name: Optional[str] = None) -> list[dict]:
    """从目录中读取所有 openclaw.json 并返回技能列表。"""
    skills = []
    
    for root, _, files in os.walk(skill_dir):
        json_file = os.path.join(root, "openclaw.json")
        if not os.path.exists(json_file):
            continue
        
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        name = data.get("name", "").lower().replace("-", " ").strip()
        
        # 如果指定了 target_name，只返回匹配的
        if target_name and not (target_name.lower() == name or 
                                any(target_name.lower() in s["triggers"] for s in data.get("skills", {}).values())):
            continue
        
        skills.append(data)
    
    return skills


def install_skill(skill_data: dict, dest_dir: str = "C:/Users/qudin/.codex/skills") -> bool:
    """安装单个技能到 $HOME/.codex/skills。"""
    name = skill_data["name"]
    version = skill_data.get("version", "0.1.0")

    # 安装目录
    dest_path = os.path.join(dest_dir, name)
    
    # 检查是否已存在（不允许覆盖）
    if os.path.exists(dest_path):
        print(f"[跳过] 技能 {name} 已存在于 {dest_path}")
        return True
    
    # 创建目录
    os.makedirs(dest_path, exist_ok=True)

    # ── 1. 复制 openclaw.json（技能元数据）──
    src_json = os.path.join(os.path.dirname(skill_data["entry_point"]), "openclaw.json")
    
    if not os.path.exists(src_json):
        print(f"[警告] openclaw.json 不存在，使用默认配置")
        
        # 创建最小化配置
        skill = skill_data.copy()
        skill.setdefault("description", f"{name} 技能")
        skill.setdefault("version", "0.1.0")
        skill["author"] = ""
        skill["entry_point"] = skill.get("entry_point", "main.py")
        
        # 自动推断 entry_point
        if name == "reporting-tools":
            skill["entry_point"] = "scripts/transpiled_inventory.py"
            dest_json_path = os.path.join(dest_path, "openclaw.json")
        elif name == "material-inventory-check":
            skill["entry_point"] = "scripts/query.py"
            dest_json_path = os.path.join(dest_path, "openclaw.json")
        elif name == "WHP-scm-huihuo-import":
            skill["entry_point"] = "scripts/run.js"
            dest_json_path = os.path.join(dest_path, "openclaw.json")
        else:
            dest_json_path = os.path.join(dest_path, "openclaw.json")

    with open(src_json, 'w', encoding='utf-8') as f:
        json.dump(skill, f, ensure_ascii=False, indent=2)
    
    if dest_json_path != src_json:
        shutil.copy(src_json, dest_path + "/openclaw.json")
        
        # 确保 entry_point 指向正确的脚本
        dest_script = os.path.join(dest_path, skill["entry_point"])
        dest_dir_base = os.path.dirname(dest_script)
        if not os.path.exists(dest_script):
            shutil.copy(src_json, dest_dir_base + "/openclaw.json")

    # ── 2. 复制 scripts 目录（如果需要）──
    src_scripts = os.path.join(os.path.dirname(skill_data["entry_point"]), "scripts")
    if os.path.exists(src_scripts) and not os.path.exists(dest_path + "/scripts"):
        shutil.copytree(src_scripts, dest_path + "/scripts", dirs_exist_ok=True)

    # ── 3. 复制 .openclaw/workspace/skills/{skill_name} 目录（如果有）──
    src_dir = os.path.join("E:/SKILLS/.openclaw/workspace/skills/", name.replace("-", "_"))
    if os.path.exists(src_dir):
        shutil.copytree(src_dir, dest_path + "/workspace/skills", dirs_exist_ok=True)

    print(f"  ✓ 安装完成：{name}")


def install_all_from_local(skill_dir: str) -> int:
    """从本地目录批量安装所有技能。"""
    skills = find_skills_in_dir(skill_dir)
    
    if not skills:
        print("未找到任何 openclaw.json 配置文件")
        return 1
    
    for skill in skills:
        try:
            install_skill(skill, dest_dir="C:/Users/qudin/.codex/skills")
        except Exception as e:
            print(f"[错误] 安装 {skill['name']} 失败：{e}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw Skill Installer",
        epilog="""
示例:
  # 从 curated skills 安装
  python tools/install_skill.py --path openai/skills/.curated --name reporting-tools
  
  # 从 GitHub repo 安装（含私有库）
  python tools/install_skill.py --repo openai/skills --path "skills/.curated/reporting-tools"
  
  # 本地目录批量安装
  python tools/install_skill.py --path ./E:/SKILLS/tools/skills
  
  # 单个技能
  python tools/install_skill.py --name reporting-tools
""")

    parser.add_argument("--path", "-p", type=str, help="本地或远程路径（文件/URL/GitHub path）")
    parser.add_argument("--repo", "-r", type=str, help="GitHub repo: owner/repo")
    parser.add_argument("--name", "-n", type=str, help="技能名称（如 reporting-tools）")
    parser.add_argument("--force", "-f", action="store_true", help="覆盖已存在的技能目录")

    args = parser.parse_args()

    if not args.name and not args.path:
        print("用法:")
        print(f"  {parser.prog} --name <skill-name>          # 安装单个技能")
        print(f"  {parser.prog} --path <local/path>           # 从本地目录安装所有")
        print(f"  {parser.prog} --repo <owner/repo>            # 从 GitHub 安装")
        sys.exit(1)

    if args.name:
        # ── 单个技能模式 ───────────────────────
        skill_data = find_skills_in_dir("E:/SKILLS/openclaw.json", target_name=args.name)[0]
        
        if not skill_data:
            print(f"[错误] 未找到技能：{args.name}")
            print("可用技能:")
            for s in find_skills_in_dir("E:/SKILLS/openclaw.json"):
                print(f"  - {s['name']}: {s.get('display_name', '')[:50]}")
            sys.exit(1)

        install_skill(skill_data, dest_dir="C:/Users/qudin/.codex/skills", force=args.force)

    elif args.path:
        # ── 本地目录批量模式 ───────────────────
        path = Path(args.path).expanduser().resolve()
        
        if not path.exists():
            print(f"[错误] 路径不存在：{path}")
            sys.exit(1)

        install_all_from_local(str(path))

    elif args.repo:
        # ── GitHub repo 模式 ───────────────────
        import subprocess
        
        cmd = f'pipx run openai-cli skills install {args.repo} --path "{args.path}"'
        
        print(f"[提示] 安装技能 '{args.repo}' ...")
        print("正在运行:")
        print(f"  {cmd}")

        try:
            result = subprocess.run(
                cmd, shell=True, check=False, timeout=600
            )
            
            if result.returncode == 0:
                print("\n✅ GitHub skill install 成功")
                sys.exit(0)
            else:
                print(f"\n❌ GitHub skill install 失败 (exit code {result.returncode})")
                print("请检查:")
                print("  1. 网络连接是否正常？")
                print("  2. GitHub repo 是否公开（非 private）？")
                sys.exit(1)

        except subprocess.TimeoutExpired:
            print("\n⚠️ 安装超时，请手动重试。")
            sys.exit(1)


if __name__ == "__main__":
    main()