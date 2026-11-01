"""Shared helpers for building mod-loader version JSON files."""

import json
import zipfile
from pathlib import Path
from typing import Optional


def extract_version_json(installer_jar: Path, version_id: str, mc_version: str) -> Optional[dict]:
    """
    从安装器 JAR 中提取版本数据。

    Forge 安装器结构:
        - install_profile.json  : 安装器配置（含 versionInfo）
        - version.json          : 部分新版本安装器包含

    NeoForge 安装器结构:
        - version.json : 完整版本清单
    """
    try:
        with zipfile.ZipFile(installer_jar) as zf:
            names = zf.namelist()

            if "version.json" in names:
                data = json.loads(zf.read("version.json").decode("utf-8"))
                data.setdefault("id", version_id)
                data.setdefault("inheritsFrom", mc_version)
                return data

            if "install_profile.json" in names:
                profile = json.loads(zf.read("install_profile.json").decode("utf-8"))
                info = profile.get("versionInfo") or profile.get("version")
                if isinstance(info, dict):
                    info.setdefault("id", version_id)
                    info.setdefault("inheritsFrom", mc_version)
                    return info

            candidates = [n for n in names if n.lower().endswith("version.json")]
            if candidates:
                candidates.sort(key=len)
                data = json.loads(zf.read(candidates[0]).decode("utf-8"))
                data.setdefault("id", version_id)
                data.setdefault("inheritsFrom", mc_version)
                return data
    except Exception:
        return None
    return None


def extract_install_profile(installer_jar: Path) -> Optional[dict]:
    """读取安装器内的 install_profile.json（Forge 1.13+ 含 processors/data）。"""
    try:
        with zipfile.ZipFile(installer_jar) as zf:
            if "install_profile.json" not in zf.namelist():
                return None
            return json.loads(zf.read("install_profile.json").decode("utf-8"))
    except Exception:
        return None


# ----------------------------------------------------------------- 处理器相关


def _coords_to_path(coords: str) -> Optional[str]:
    """
    把 Maven 坐标转成 libraries 下的相对路径。

    例：net.minecraft:client:1.20.1-20230612.114412:srg
        -> net/minecraft/client/1.20.1-20230612.114412/client-1.20.1-20230612.114412-srg.jar
    支持扩展名后缀：...:mappings@txt -> ...-mappings.txt
    """
    coords = coords.strip().strip("[]").strip()
    if not coords:
        return None

    ext = "jar"
    if "@" in coords:
        coords, _, suffix = coords.rpartition("@")
        ext = suffix or "jar"

    parts = coords.split(":")
    if len(parts) < 3:
        return None

    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) >= 4 and parts[3] else ""

    # 安装器里的扩展名可能只是占位写法，mcp_config 实际是 zip
    if artifact == "mcp_config" and classifier == "mappings":
        ext = "zip"

    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + f".{ext}"
    return "/".join(group.split(".") + [artifact, version, filename])


def iter_processor_artifacts(profile: dict) -> list[tuple[str, str]]:
    """
    从 install_profile.json 收集安装器处理器需要读取的文件。

    返回 [(相对路径, 来源)]，来源为 "maven" 或 "mojmap"。
    - maven  : 从 Forge maven / 镜像下载
    - mojmap : 从 Mojang 官方 piston-meta / piston-data 下载

    坐标里的扩展名可能是占位写法（例如 mcp_config 标注为 @txt，
    实际构件是 @zip），因此这里做一次兜底修正。
    """
    paths: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(coords: str):
        rel = _coords_to_path(coords)
        if not rel or rel in seen:
            return
        seen.add(rel)
        source = "mojmap" if rel.startswith("net/minecraft/") else "maven"
        paths.append((rel, source))

    for value in (profile.get("data") or {}).values():
        if not isinstance(value, dict):
            continue
        for side in ("client", "server"):
            raw = value.get(side)
            if isinstance(raw, str) and raw.strip().startswith("["):
                add(raw)

    for proc in (profile.get("processors") or []):
        if proc.get("jar"):
            add(proc["jar"])
        for cp in (proc.get("classpath") or []):
            add(cp)

    return paths
