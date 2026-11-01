# mc_downloader/core/constants.py
"""
Core constants used throughout the downloader.
"""

# 请求头
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MC-Downloader/2.0"}

# 连接 / 读取超时（秒）
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 20

# 禁用系统代理
PROXIES = {"http": None, "https": None}

# 镜像源 URL 映射表
URL_REPLACE_MAP = [
    ("https://launchermeta.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://launcher.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://libraries.minecraft.net/", "https://bmclapi2.bangbang93.com/maven/"),
    ("http://resources.download.minecraft.net/", "https://bmclapi2.bangbang93.com/assets/"),
    ("https://resources.download.minecraft.net/", "https://bmclapi2.bangbang93.com/assets/"),
    ("https://piston-meta.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://piston-data.mojang.com/", "https://bmclapi2.bangbang93.com/"),
]

# 官方源 URL
OFFICIAL_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MIRROR_MANIFEST_URL = "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"

# 下载配置
MAX_RETRIES = 3
CHUNK_SIZE = 16384

# 线程数限制
MIRROR_MAX_THREADS = 16
OFFICIAL_MAX_THREADS = 64