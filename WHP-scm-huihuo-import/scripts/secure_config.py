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
from typing import Any, Dict, Optional


# ═══════════════════════════════════════════════════════
# 配置管理器
# ═══════════════════════════════════════════════════════

class ConfigManager:
    """配置管理器 - 支持明文和加密两种模式"""
    
    def __init__(self, config_file: str = "runtime_config.json"):
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
                "username": "your_username",
                "password": "",
                "audit_date": "2026-04-01",
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
# 独立运行：加密密码设置工具
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  SCM 安全密码设置工具")
    print("=" * 60)
    
    config_file = "runtime_config.json"
    manager = ConfigManager(config_file)
    secure_manager = SecurePasswordManager(manager)
    
    scm_password = input("\n请输入 SCM 密码（留空跳过）：").strip()
    if scm_password:
        secure_manager.save_password("scm", manager.get_sc_config("username", "your_username"), scm_password)
        print("[OK] SCM 密码已加密存储")
    
    print("\n密码设置完成！")
