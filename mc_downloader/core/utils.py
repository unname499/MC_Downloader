# mc_downloader/core/utils.py
"""
Utility functions for the downloader.
"""
import hashlib
import os
import time
import threading
from pathlib import Path
from typing import Optional

import requests

from mc_downloader.core.constants import (
    HEADERS, PROXIES, URL_REPLACE_MAP, MAX_RETRIES, CHUNK_SIZE,
    OFFICIAL_MANIFEST_URL, MIRROR_MANIFEST_URL, CONNECT_TIMEOUT, READ_TIMEOUT
)

# 强制直连，不走系统代理
os.environ["NO_PROXY"] = "bmclapi2.bangbang93.com,localhost,127.0.0.1"


def get_download_url(original_url: str, use_mirror: bool) -> str:
    """Convert official URL to mirror URL if needed."""
    if not use_mirror:
        return original_url
    for official, mirror in URL_REPLACE_MAP:
        if original_url.startswith(official):
            return mirror + original_url[len(official):]
    return original_url


def verify_sha1(file_path: Path, expected_sha1: str) -> bool:
    """Verify SHA1 hash of a file."""
    sha1 = hashlib.sha1()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha1.update(chunk)
    return sha1.hexdigest().lower() == expected_sha1.lower()


def fetch_text(url: str, use_mirror: bool = False, timeout: int = READ_TIMEOUT) -> str:
    """Fetch raw text from URL, with official-source fallback when mirror fails."""
    candidates = [url]
    if use_mirror:
        mirrored = get_download_url(url, True)
        official = get_download_url(url, False)
        candidates = [mirrored] if mirrored != official else []
        candidates.append(official)
    else:
        candidates = [get_download_url(url, False)]

    last_err: Exception | None = None
    for candidate in candidates:
        try:
            resp = requests.get(
                candidate, headers=HEADERS,
                timeout=(CONNECT_TIMEOUT, timeout), proxies=PROXIES,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise last_err


def fetch_json(url: str, use_mirror: bool = False, timeout: int = READ_TIMEOUT) -> dict:
    """Fetch JSON from URL, with official-source fallback when mirror fails."""
    import json as _json
    return _json.loads(fetch_text(url, use_mirror, timeout))


def fetch_version_list(use_mirror: bool) -> list[dict]:
    """获取 Minecraft 版本清单（镜像失败时自动回退官方源）。"""
    urls = [MIRROR_MANIFEST_URL, OFFICIAL_MANIFEST_URL] if use_mirror else [OFFICIAL_MANIFEST_URL]
    last_err: Exception | None = None
    for url in urls:
        try:
            data = fetch_json(url, use_mirror=False)
            return [{"id": v["id"], "type": v.get("type", "release")} for v in data.get("versions", [])]
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise last_err


class ProgressTracker:
    """Thread-safe progress tracker for downloads."""

    def __init__(self, total_bytes: int = 0):
        self._lock = threading.Lock()
        self._done_bytes = 0
        self._total_bytes = total_bytes
        self._cancelled = False
        self._listener = None

    def set_listener(self, callback):
        """注册进度回调 callback(done, total)，在加锁范围外调用。"""
        self._listener = callback

    @property
    def done_bytes(self) -> int:
        with self._lock:
            return self._done_bytes

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def set_total(self, total: int):
        with self._lock:
            self._total_bytes = total

    def add_done(self, bytes_count: int):
        listener = None
        with self._lock:
            self._done_bytes += bytes_count
            if self._listener is not None:
                listener = self._listener
            done, total = self._done_bytes, self._total_bytes
        if listener is not None:
            listener(done, total)

    def cancel(self):
        with self._lock:
            self._cancelled = True

    def get_progress(self) -> tuple[int, int]:
        with self._lock:
            return self._done_bytes, self._total_bytes


def download_file(
    url: str,
    path: Path,
    expected_sha1: Optional[str] = None,
    progress_tracker: Optional[ProgressTracker] = None,
    session: Optional[requests.Session] = None,
    use_mirror: bool = False,
    retry_delay_base: float = 1.0
) -> str:
    """
    Download a single file with retries and SHA1 verification.
    
    Returns: "OK", "SKIP", "CANCELLED", or raises exception
    """
    # Skip if already exists and verified
    if path.exists() and expected_sha1 and verify_sha1(path, expected_sha1):
        return "SKIP"
    
    path.parent.mkdir(parents=True, exist_ok=True)
    url = get_download_url(url, use_mirror)
    
    getter = session.get if session else requests.get
    last_err = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        if progress_tracker and progress_tracker.cancelled:
            return "CANCELLED"
        
        try:
            if use_mirror:
                time.sleep(0.1)  # Rate limiting for mirror
            
            resp = getter(url, headers=HEADERS, stream=True,
                          timeout=(CONNECT_TIMEOUT, READ_TIMEOUT * 3), proxies=PROXIES)
            resp.raise_for_status()
            
            with open(path, "wb") as f:
                for chunk in resp.iter_content(CHUNK_SIZE):
                    if progress_tracker and progress_tracker.cancelled:
                        f.close()
                        path.unlink(missing_ok=True)
                        return "CANCELLED"
                    f.write(chunk)
                    if progress_tracker:
                        progress_tracker.add_done(len(chunk))
            
            # Verify SHA1 if provided
            if expected_sha1 and not verify_sha1(path, expected_sha1):
                raise ValueError(f"SHA1 mismatch for {path.name}")
            
            return "OK"
            
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(retry_delay_base * attempt)
            else:
                raise last_err
    
    return "FAIL"


def apply_rules(rules: list[dict], os_name: str = "windows") -> bool:
    """Apply library download rules (allow/disallow based on OS)."""
    allowed = True
    for rule in rules:
        rule_os = rule.get("os", {}).get("name")
        action = rule.get("action")
        if action == "allow" and rule_os not in [None, os_name]:
            allowed = False
            break
        if action == "disallow" and rule_os == os_name:
            allowed = False
            break
    return allowed