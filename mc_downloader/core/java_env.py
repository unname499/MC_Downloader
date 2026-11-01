# mc_downloader/core/java_env.py
"""
Java 运行环境探测。

用于可选的「运行安装器补全」功能：Forge / NeoForge 的数据处理器
必须由 Java 执行，才能生成 srg / extra / client 等补丁文件。

查找顺序：
    1. 配置中显式指定的路径
    2. 环境变量 JAVA_HOME
    3. PATH 中的 java
    4. 常见安装目录（Zulu / Adoptium / Oracle / Microsoft / 各个 vendor）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Windows 上 Java 主程序的名称
JAVA_EXE = "javaw.exe" if sys.platform == "win32" else "java"
CONSOLE_JAVA = "java.exe" if sys.platform == "win32" else "java"


def _common_roots() -> list[Path]:
    """各平台常见的 JDK/JRE 安装根目录。"""
    roots: list[Path] = []

    if sys.platform == "win32":
        for base in (
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("ProgramFiles", ""),
        ):
            if not base:
                continue
            base_path = Path(base)
            if not base_path.exists():
                continue
            roots.append(base_path / "Zulu")
            roots.append(base_path / "Eclipse Adoptium")
            roots.append(base_path / "Java")
            roots.append(base_path / "Microsoft" / "jdk")
            roots.append(base_path / "Amazon Corretto")
            roots.append(base_path / "BellSoft" / "LibericaJDK")
            roots.append(base_path / "Programs" / "Eclipse Adoptium")
    else:
        # Linux / macOS 常见位置
        roots.extend([
            Path("/usr/lib/jvm"),
            Path("/usr/java"),
            Path("/Library/Java/JavaVirtualMachines"),
            Path.home() / ".sdkman" / "candidates" / "java",
            Path.home() / "Library" / "Java" / "JavaVirtualMachines",
        ])

    return roots


def _java_in_dir(directory: Path) -> Optional[Path]:
    """在给定目录下寻找可用的 java 可执行文件。"""
    for exe in (CONSOLE_JAVA, JAVA_EXE, "java"):
        candidate = directory / exe
        if candidate.is_file():
            return candidate

    # macOS 的 .jdk/Contents/Home 结构
    mac_home = directory / "Contents" / "Home" / "bin" / "java"
    if mac_home.is_file():
        return mac_home

    return None


def find_java(explicit: str = "") -> Optional[Path]:
    """
    返回可用的 java 可执行文件路径；找不到返回 None。

    优先返回控制台版 java（java.exe），便于捕获安装器输出。
    """
    # 1) 显式配置
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        if p.is_dir():
            found = _java_in_dir(p / "bin") or _java_in_dir(p)
            if found:
                return found

    # 2) JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        found = _java_in_dir(Path(java_home) / "bin") or _java_in_dir(Path(java_home))
        if found:
            return found

    # 3) PATH
    which = shutil.which(CONSOLE_JAVA) or shutil.which("java")
    if which:
        return Path(which)

    # 4) 常见目录（递归两层，匹配 zulu-21 / jdk-21 这类版本目录）
    for root in _common_roots():
        if not root.exists():
            continue
        found = _java_in_dir(root / "bin")
        if found:
            return found
        try:
            entries = sorted([p for p in root.iterdir() if p.is_dir()],
                             key=lambda p: p.name, reverse=True)
        except OSError:
            continue
        for entry in entries:
            found = _java_in_dir(entry / "bin") or _java_in_dir(entry)
            if found:
                return found
            # 再下一层（如 Microsoft/jdk/17.0.x）
            try:
                for sub in sorted(entry.iterdir(), key=lambda p: p.name, reverse=True):
                    if sub.is_dir():
                        found = _java_in_dir(sub / "bin") or _java_in_dir(sub)
                        if found:
                            return found
            except OSError:
                continue

    return None


def java_version(java: Path, timeout: int = 15) -> str:
    """获取 java -version 的首行（失败返回空串）。"""
    try:
        result = subprocess.run(
            [str(java), "-version"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_no_window_flags(),
        )
        output = (result.stderr or result.stdout or "").strip()
        return output.splitlines()[0] if output else ""
    except Exception:  # noqa: BLE001
        return ""


def java_major_version(java: Path) -> Optional[int]:
    """解析主版本号，例如 17 / 21 / 8。"""
    text = java_version(java)
    if not text:
        return None
    import re
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        return None
    major = int(m.group(1))
    # 1.8.0_xxx 形式
    if major == 1 and m.group(2):
        return int(m.group(2))
    return major


def _no_window_flags() -> int:
    """Windows 下启动子进程时不额外弹出控制台窗口。"""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0
