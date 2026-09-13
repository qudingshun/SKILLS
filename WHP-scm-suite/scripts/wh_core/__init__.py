"""WH 惠而浦共享核心库。

由 4 个技能（export/import/received/download/query）共用的模块：
- secure_config:     配置管理器 + AES 密码管理器（集中密码库）
- whirlpool_common:  浏览器创建、本地密码解码、状态存储、通用工具

用法：将本包所在目录（scripts 目录）加入 sys.path 后：
    from wh_core.secure_config import ConfigManager, SecurePasswordManager
    from wh_core.whirlpool_common import create_browser, safe_print, ...
"""