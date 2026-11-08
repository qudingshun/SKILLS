# -*- coding: utf-8 -*-
"""
erp_runtime_config.json 配置模板（不含任何明文密码）

说明：
  - 密码不在此文件，也不在任何技能源文件里；密码由 erp_secure_config.py
    加密保存到 erp_runtime_config/passwords/erp_password.dat。
  - 本文件仅保存非敏感配置。首次运行 erp_ops.py 会自动创建
    erp_runtime_config.json（若不存在）。

字段：
  erp.username       ERP 登录账号（固定 hsa697）
  erp.home_url       EBS 首页地址
  erp.download_dir   报表/文件下载落地目录
  forms.jnlp_dir     Forms 启动 JNLP 缓存目录
  forms.window_title 连接 Forms Java 窗口时的标题匹配（正则）
"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_BASE_DIR, "..", "erp_runtime_config.json")

DEFAULT_CONFIG = {
    "erp": {
        "username": "hsa697",
        "home_url": (
            "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
            "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
            "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y"
            "&oapc=2&transactionid=1652645857&oas=BqTsZ_lSLwh9QeRE263_4g.."
        ),
        "download_dir": r"D:\360安全浏览器下载",
    },
    "forms": {
        "jnlp_dir": os.path.join(_BASE_DIR, "..", "forms_runtime"),
        "window_title_re": r"Oracle.*|.*E-Business Suite.*|.*Forms.*",
    },
}


def ensure_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"[配置] 已创建默认配置: {CONFIG_FILE}")
    return CONFIG_FILE


if __name__ == "__main__":
    ensure_config()
