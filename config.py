# config.py
import sys
import configparser
from pathlib import Path

# ================= 打包/开发环境路径适配 =================
if getattr(sys, 'frozen', False):
    # 打包后的 exe 环境：配置保存在 exe 同级目录
    BASE_DIR = Path(sys.executable).parent
else:
    # 开发环境：配置保存在当前代码所在目录
    BASE_DIR = Path(__file__).resolve().parent

# 确保目录存在
BASE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = BASE_DIR / "config.ini"
# ==========================================================

CONFIG_SECTION = "config"

DEFAULT_CONFIG = {
    "minecraft_dir": "",
    "use_mirror": "true",
    "threads": "32",
    "off_settings_notice": "false",
}


def read_conf() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = DEFAULT_CONFIG
    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH, encoding="utf-8")
    return config


def write_conf(config: configparser.ConfigParser) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


def write_default_conf() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = DEFAULT_CONFIG
    write_conf(config)
    return config


def get_bool(config: configparser.ConfigParser, key: str, fallback: bool = False) -> bool:
    val = config.get(CONFIG_SECTION, key, fallback=str(fallback))
    return val.strip().lower() in ("true", "1", "yes", "on")


def get_int(config: configparser.ConfigParser, key: str, fallback: int = 0) -> int:
    return config.getint(CONFIG_SECTION, key, fallback=fallback)


def get_str(config: configparser.ConfigParser, key: str, fallback: str = "") -> str:
    return config.get(CONFIG_SECTION, key, fallback=fallback)