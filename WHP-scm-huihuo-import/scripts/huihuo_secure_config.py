#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全配置管理模块
================
提取自 unified_report_downloader.py，供 config_example.py 和其他脚本共享使用。

包含：
  - ConfigManager：JSON 配置文件读写
  - SecurePasswordManager：AES-256 加密密码存储/读取
"""

import hashlib
import json
import os
import sys
from typing import Any, Dict, Optional


def load_scm_credentials(config_file: Optional[str] = None):
    """读取 SCM 账号密码，返回 (username, password)。

    账号取自 huihuo_runtime_config.json -> scm.username，
    密码优先从 AES-256 加密文件 (huihuo_runtime_config/passwords/scm_password.dat) 读取。
    凭据缺失/仍为占位符时打印指引并 sys.exit(1)。
    """
    if config_file is None:
        config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "huihuo_runtime_config.json")
    data = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    scm = data.get("scm", {})
    username = scm.get("username", "") or ""
    password = ""
    try:
        config_manager = ConfigManager(config_file)
        secure_manager = SecurePasswordManager(config_manager)
        password = secure_manager.load_password("scm") or ""
    except Exception:
        pass
    if not username or username == "your_username" or not password:
        print("[配置错误] SCM 账号/密码未配置，请运行：py huihuo_secure_config.py [--username <账号>] --set-password <密码>")
        sys.exit(1)
    return username, password


# ═══════════════════════════════════════════════════════
# 配置管理器
# ═══════════════════════════════════════════════════════

class ConfigManager:
    """配置管理器 - 支持明文和加密两种模式"""
    
    def __init__(self, config_file: str = "huihuo_runtime_config.json"):
        self.config_file = config_file
        self.configs: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.configs = json.load(f)
                print(f"[配置] 已加载 {self.config_file}")
            except Exception as e:
                print(f"[配置] 加载失败：{e}, 使用默认配置")
        else:
            self._create_default_config()
    
    def _create_default_config(self):
        """创建默认配置"""
        default = {
            "scm": {
                "username": "hsa697",
                "password": "",
                "audit_date": "2026-08-21",
                "shipment_date_start": "2026-09-01",
                "dir_task1": r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件",
                "dir_task2": r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件",
                "dir_task3": r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件",
                "dir_task4": r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件",
                "dir_task5": r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件",
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        print("[配置] 已创建默认配置文件")
    
    def get_sc_config(self, key: str, default=None):
        """获取 SCM 配置项"""
        return self.configs.get("scm", {}).get(key, default)
    
    def set_sc_config(self, key: str, value: Any):
        """设置 SCM 配置项"""
        if "scm" not in self.configs:
            self.configs["scm"] = {}
        self.configs["scm"][key] = value
        self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.configs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[配置] 保存失败：{e}")


# ═══════════════════════════════════════════════════════
# 安全密码管理器
# ═══════════════════════════════════════════════════════

class SecurePasswordManager:
    """安全密码管理器 - 使用 AES-256 加密"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._password_dir = os.path.join(
            config_manager.config_file.replace('.json', ''), 
            "passwords"
        )
        os.makedirs(self._password_dir, exist_ok=True)
    
    def _get_master_key(self) -> bytes:
        """生成主密钥（基于系统信息，不含时间，确保可重复生成相同密钥）"""
        seed = f"{os.getenv('USERNAME')}|{os.getenv('COMPUTERNAME')}|WPOOL_REPORT_V1"
        return hashlib.sha256(seed.encode("utf-8")).digest()
    
    def _aes_encrypt(self, plaintext: str) -> bytes:
        """AES-256 加密（CBC + PKCS7 填充）"""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend
        
        key = self._get_master_key()
        iv = os.urandom(16)
        
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encoder = cipher.encryptor()
        return iv + encoder.update(padded) + encoder.finalize()
    
    def _aes_decrypt(self, ciphertext: bytes) -> str:
        """AES-256 解密（CBC + PKCS7 填充去除）"""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend
        
        iv = ciphertext[:16]
        encrypted_data = ciphertext[16:]
        
        key = self._get_master_key()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decoder = cipher.decryptor()
        decrypted_padded = decoder.update(encrypted_data) + decoder.finalize()
        
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return decrypted.decode('utf-8')
    
    def save_password(self, service: str, username: str, password: str):
        """保存加密密码"""
        filename = f"{service}_password.dat"
        filepath = os.path.join(self._password_dir, filename)
        
        try:
            encrypted = self._aes_encrypt(password)
            with open(filepath, 'wb') as f:
                f.write(encrypted)
            print(f"[安全] {service} 密码已加密保存")
        except Exception as e:
            print(f"[安全] 保存失败：{e}")
    
    def load_password(self, service: str) -> Optional[str]:
        """加载加密密码"""
        filename = f"{service}_password.dat"
        filepath = os.path.join(self._password_dir, filename)
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'rb') as f:
                encrypted = f.read()
            return self._aes_decrypt(encrypted)
        except Exception as e:
            print(f"[安全] 加载失败：{e}")
            return None
    
    def clear_password(self, service: str):
        """清除密码（谨慎使用）"""
        filename = f"{service}_password.dat"
        filepath = os.path.join(self._password_dir, filename)
        
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"[安全] {service} 密码已清除")
            except Exception as e:
                print(f"[安全] 清除失败：{e}")


# ═══════════════════════════════════════════════════════
# 独立运行：SCM 配置 / 密码设置工具
#
# 用法（配置文件固定为本文件所在目录的 huihuo_runtime_config.json）：
#   py huihuo_secure_config.py                                    # 交互式配置用户名+密码
#   py huihuo_secure_config.py --username hsa697 --password xxxx  # 命令行配置（适合自动化）
#   py huihuo_secure_config.py --set-password xxxx                # 仅设置/修改密码
#   py huihuo_secure_config.py --clear-password                   # 清除已存密码
#   py huihuo_secure_config.py --verify                           # 校验配置是否完整可用
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # 配置文件固定锚定到脚本自身所在目录，
    # 保证无论从哪里运行都写入 scripts/huihuo_runtime_config.json
    # 与 scripts/huihuo_runtime_config/passwords/scm_password.dat
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _CONFIG_FILE = os.path.join(_SCRIPT_DIR, "huihuo_runtime_config.json")

    parser = argparse.ArgumentParser(description="SCM 回货技能 配置/密码设置工具")
    parser.add_argument("--username", help="设置 SCM 用户名（写入 huihuo_runtime_config.json）")
    parser.add_argument("--set-password", "--password", dest="password", help="设置 SCM 密码（AES-256 加密保存）")
    parser.add_argument("--clear-password", action="store_true", help="清除已加密保存的密码")
    parser.add_argument("--verify", action="store_true", help="只校验配置是否完整可用，不做修改")
    args = parser.parse_args()

    manager = ConfigManager(_CONFIG_FILE)
    secure_manager = SecurePasswordManager(manager)

    def _show_status(final: bool = False):
        username = manager.get_sc_config("username", "")
        has_pw = secure_manager.load_password("scm") is not None
        print(f"\n[{'配置完成' if final else '当前配置'}]")
        print(f"  配置文件        : {_CONFIG_FILE}")
        print(f"  SCM 用户名      : {username or '(未设置)'}")
        print(f"  SCM 密码        : {'已加密存储' if has_pw else '未设置'}")
        print(f"  密码存储目录    : {secure_manager._password_dir}")

    # ============ 命令行参数模式（非交互） ============
    if args.verify:
        _show_status()
        ok = True
        username = manager.get_sc_config("username", "")
        if not username or username == "your_username":
            print("\n[WARN] 用户名未配置（仍为占位符 your_username）")
            ok = False
        if not secure_manager.load_password("scm"):
            print("\n[WARN] SCM 密码未设置")
            ok = False
        print("\n[OK] 配置完整，SCM 可正常读取用户名与密码。" if ok else "\n[FAIL] 配置不完整，请重新配置。")
        sys.exit(0 if ok else 1)

    if args.username:
        manager.set_sc_config("username", args.username.strip())
    if args.clear_password:
        secure_manager.clear_password("scm")
    elif args.password:
        username = manager.get_sc_config("username", "") or "your_username"
        secure_manager.save_password("scm", username, args.password)

    if args.username or args.clear_password or args.password:
        _show_status(final=True)
        sys.exit(0)

    # ============ 交互式模式（默认） ============
    print("\n" + "=" * 60)
    print("  SCM 回货 配置 / 安全密码设置工具")
    print("=" * 60)
    _show_status()

    new_username = input("\nSCM 用户名（回车保持不变）：").strip()
    if new_username:
        manager.set_sc_config("username", new_username)

    print("\n密码操作：")
    print("  1 = 设置/修改密码")
    print("  2 = 清除密码")
    print("  0 = 跳过（回车）")
    choice = input("请选择 [0/1/2]：").strip()
    if choice == "1":
        pw = input("请输入 SCM 密码：").strip()
        if pw:
            manager.set_sc_config("username", manager.get_sc_config("username", "") or "your_username")
            secure_manager.save_password("scm", manager.get_sc_config("username", ""), pw)
    elif choice == "2":
        secure_manager.clear_password("scm")

    print("\n" + "=" * 60)
    _show_status(final=True)
    print("\n配置完成！")
