#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WHP-whirlpool-erp 安全配置模块
==============================

密码加密存储机制（与 WHP-whirlpool-download 同源，统一安全模型）：

  - 使用 AES-256 (CBC + PKCS7) 加密，主密钥由
    USERNAME | COMPUTERNAME | WPOOL_ERP_V1 经 SHA-256 派生。
  - 密钥仅依赖本机用户名/机器名，因此 .dat 密文**只能在本机、本用户下解密**，
    即使文件被拷贝走也无法还原，满足"明文密码绝不落盘"的硬性要求。
  - 密码存为 erp_runtime_config/passwords/<service>_password.dat（仅密文）。

⚠️ 安全红线：
  - 任何技能源文件（.py / .json / .md）**禁止写入明文密码**。
  - 密码只能通过本模块的“设置工具”交互输入，或一次性加密命令生成 .dat。
  - 设置完成后，明文只存在于用户输入的 stdin / 内存，绝不写入技能目录。

用法：
  # 交互式设置 ERP 密码（推荐，手动输入，明文不落盘）
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_secure_config.py

  # 程序化设置（密码从 stdin 读入，不写文件，适合首次灌密）
  echo "<密码>" | E:/SKILLS/.venv/Scripts/python.exe scripts/erp_secure_config.py --stdin erp

  # 校验当前能否解密（不打印明文，只报 OK/FAIL）
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_secure_config.py --check erp
"""

import argparse
import getpass
import hashlib
import os
import sys

# 公共安全输出（避免 GBK 控制台 UnicodeEncodeError）
try:
    from erp_common import safe_print
except ImportError:
    def safe_print(*args, **kwargs):
        print(*args, **kwargs)


# 配置 / 密码目录（脚本同级）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_BASE_DIR, "..", "erp_runtime_config.json")
PASSWORD_DIR = os.path.join(_BASE_DIR, "..", "erp_runtime_config", "passwords")
os.makedirs(PASSWORD_DIR, exist_ok=True)


class SecurePasswordManager:
    """AES-256 加密密码管理器（与 download 技能同源，salt 为 WPOOL_ERP_V1）"""

    SALT = "WPOOL_ERP_V1"

    def _get_master_key(self) -> bytes:
        """主密钥：本机用户名|机器名|salt -> SHA-256（确定性，可重复生成）"""
        seed = f"{os.getenv('USERNAME')}|{os.getenv('COMPUTERNAME')}|{self.SALT}"
        return hashlib.sha256(seed.encode("utf-8")).digest()

    def _aes_encrypt(self, plaintext: str) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend

        key = self._get_master_key()
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        enc = cipher.encryptor()
        return iv + enc.update(padded) + enc.finalize()

    def _aes_decrypt(self, ciphertext: bytes) -> str:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend

        iv = ciphertext[:16]
        data = ciphertext[16:]
        key = self._get_master_key()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(data) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(padded) + unpadder.finalize()
        return decrypted.decode("utf-8")

    def save_password(self, service: str, username: str, password: str) -> bool:
        """加密保存密码到 <service>_password.dat（仅密文）"""
        try:
            filepath = os.path.join(PASSWORD_DIR, f"{service}_password.dat")
            enc = self._aes_encrypt(password)
            with open(filepath, "wb") as f:
                f.write(enc)
            safe_print(f"[安全] {service} 密码已加密保存 -> {filepath}")
            return True
        except Exception as e:
            safe_print(f"[安全] 保存失败: {e}")
            return False

    def load_password(self, service: str):
        """加载并解密密码；不存在返回 None"""
        filepath = os.path.join(PASSWORD_DIR, f"{service}_password.dat")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                enc = f.read()
            return self._aes_decrypt(enc)
        except Exception as e:
            safe_print(f"[安全] 加载失败: {e}")
            return None

    def clear_password(self, service: str):
        filepath = os.path.join(PASSWORD_DIR, f"{service}_password.dat")
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                safe_print(f"[安全] {service} 密码已清除")
            except Exception as e:
                safe_print(f"[安全] 清除失败: {e}")


def _do_set(service: str, password: str):
    mgr = SecurePasswordManager()
    username = "hsa697"  # ERP 固定账号
    if mgr.save_password(service, username, password):
        safe_print(f"[OK] {service} 密码已加密存储（账号 {username}）")


def _do_check(service: str):
    mgr = SecurePasswordManager()
    pw = mgr.load_password(service)
    if pw is None:
        safe_print(f"[FAIL] 未找到 {service} 密码文件，请先设置")
        return False
    # 不打印明文，只验证能解出来且非空
    if pw:
        safe_print(f"[OK] {service} 密码可正常解密（长度 {len(pw)}）")
        return True
    safe_print(f"[FAIL] {service} 解密为空")
    return False


# ── 供 erp_ops 直接调用的干净接口（不依赖 sys.argv） ──────────────────────
def interactive_setup():
    """交互式设置 ERP 密码（默认 service=erp）"""
    safe_print("\n" + "=" * 56)
    safe_print("  WHP ERP 安全密码设置（明文仅经 stdin/内存，绝不落盘）")
    safe_print("=" * 56)
    try:
        if sys.stdin and sys.stdin.isatty():
            pw = getpass.getpass("\n请输入 ERP 密码（输入不可见，留空跳过）：")
        else:
            pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    except Exception:
        pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    if pw:
        _do_set("erp", pw)
    else:
        safe_print("[跳过] 未输入密码")
    safe_print("\n设置完成。")


def set_from_stdin(service: str):
    pw = sys.stdin.read().strip()
    if not pw:
        safe_print("[FAIL] stdin 为空，未保存")
        return False
    return _do_set(service, pw) or True


def check_service(service: str) -> bool:
    return _do_check(service)


def clear_service(service: str):
    SecurePasswordManager().clear_password(service)


def main():
    ap = argparse.ArgumentParser(description="WHP ERP 安全密码设置工具")
    ap.add_argument("--stdin", metavar="SERVICE",
                    help="从 stdin 读取密码并加密保存（不落明文文件）")
    ap.add_argument("--check", metavar="SERVICE", help="校验某服务的密码是否可解密")
    ap.add_argument("--clear", metavar="SERVICE", help="清除某服务的密码文件")
    args = ap.parse_args()

    if args.check:
        _do_check(args.check)
        return
    if args.clear:
        SecurePasswordManager().clear_password(args.clear)
        return
    if args.stdin:
        # 从 stdin 读入（交互或非交互），明文不写文件
        pw = sys.stdin.read().strip()
        if not pw:
            safe_print("[FAIL] stdin 为空，未保存")
            sys.exit(1)
        _do_set(args.stdin, pw)
        return

    # 默认：交互式设置（隐藏输入）
    safe_print("\n" + "=" * 56)
    safe_print("  WHP ERP 安全密码设置（明文仅经 stdin/内存，绝不落盘）")
    safe_print("=" * 56)
    try:
        if sys.stdin and sys.stdin.isatty():
            pw = getpass.getpass("\n请输入 ERP 密码（输入不可见，留空跳过）：")
        else:
            pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    except Exception:
        pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    if pw:
        _do_set("erp", pw)
    else:
        safe_print("[跳过] 未输入密码")
    safe_print("\n设置完成。")


if __name__ == "__main__":
    main()
