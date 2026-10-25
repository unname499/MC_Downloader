# downloader.py
import json
import hashlib
import concurrent.futures
import threading
import time
import os
from pathlib import Path

# 强制直连，不走系统代理，防止 USTC 等失效镜像劫持
os.environ["NO_PROXY"] = "bmclapi2.bangbang93.com,localhost,127.0.0.1"

import requests
from PySide6.QtCore import QThread, Signal

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MC-Downloader/1.0"}
PROXIES = {"http": None, "https": None}

URL_REPLACE_MAP = [
    ("https://launchermeta.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://launcher.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://libraries.minecraft.net/", "https://bmclapi2.bangbang93.com/maven/"),
    ("http://resources.download.minecraft.net/", "https://bmclapi2.bangbang93.com/assets/"),
    ("https://resources.download.minecraft.net/", "https://bmclapi2.bangbang93.com/assets/"),
    ("https://piston-meta.mojang.com/", "https://bmclapi2.bangbang93.com/"),
    ("https://piston-data.mojang.com/", "https://bmclapi2.bangbang93.com/"),
]


def get_download_url(original_url: str, use_mirror: bool) -> str:
    if not use_mirror:
        return original_url
    for official, mirror in URL_REPLACE_MAP:
        if original_url.startswith(official):
            return mirror + original_url[len(official):]
    return original_url


def verify_sha1(file_path: Path, expected_sha1: str) -> bool:
    sha1 = hashlib.sha1()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha1.update(chunk)
    return sha1.hexdigest() == expected_sha1


def fetch_version_list(use_mirror: bool) -> list[dict]:
    url = ("https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
           if use_mirror
           else "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
    resp = requests.get(url, headers=HEADERS, timeout=30, proxies=PROXIES)
    resp.raise_for_status()
    data = resp.json()
    return [{"id": v["id"], "type": v.get("type", "release")} for v in data.get("versions", [])]


class VersionFetcher(QThread):
    """后台线程：拉取版本列表"""
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, use_mirror: bool, parent=None):
        super().__init__(parent)
        self.use_mirror = use_mirror

    def run(self):
        try:
            versions = fetch_version_list(self.use_mirror)
            self.finished.emit(versions)
        except Exception as e:
            self.failed.emit(str(e))


class DownloadWorker(QThread):
    """后台线程：下载游戏文件"""
    log = Signal(str)
    progress = Signal(int, int)
    stage = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    MAX_RETRIES = 3
    CHUNK_SIZE = 16384

    def __init__(self, version_id: str, mc_dir: Path, threads: int = 8, use_mirror: bool = False, parent=None):
        super().__init__(parent)
        self.version_id = version_id
        self.mc_dir = mc_dir
        self.use_mirror = use_mirror

        if use_mirror:
            self.threads = max(1, min(threads, 16))
        else:
            self.threads = max(1, min(threads, 64))

        self._cancelled = False
        self._lock = threading.Lock()
        self._done_bytes = 0
        self._total_bytes = 0

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.use_mirror:
                self.log.emit("镜像源：BMCLAPI (https://bmclapi2.bangbang93.com)")
            else:
                self.log.emit("镜像源：Mojang 官方")
            self.log.emit(f"===== 开始下载 Minecraft {self.version_id} =====")

            version_data = self._get_version_data()
            if self._cancelled: return

            asset_index = self._download_core_files(version_data)
            if not asset_index:
                self.failed.emit("没有获取到 assetIndex")
                return

            lib_tasks = self._generate_library_tasks(version_data)
            self._execute_download_tasks(lib_tasks, "依赖库")

            asset_tasks = self._generate_asset_tasks(asset_index)
            self._execute_download_tasks(asset_tasks, "资源文件")

            self.log.emit("===== 全部下载完成！ =====")
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))

    def _get_manifest_url(self) -> str:
        if self.use_mirror:
            return "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
        return "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

    def _get_version_data(self) -> dict:
        self.log.emit(f"正在获取版本 {self.version_id} 的清单...")
        resp = requests.get(self._get_manifest_url(), headers=HEADERS, timeout=30, proxies=PROXIES)
        resp.raise_for_status()
        manifest = resp.json()

        target_url = next((v["url"] for v in manifest["versions"] if v["id"] == self.version_id), None)
        if not target_url:
            raise ValueError(f"找不到版本: {self.version_id}")

        target_url = get_download_url(target_url, self.use_mirror)
        detail_resp = requests.get(target_url, headers=HEADERS, timeout=30, proxies=PROXIES)
        detail_resp.raise_for_status()
        version_data = detail_resp.json()

        version_json_path = self.mc_dir / "versions" / self.version_id / f"{self.version_id}.json"
        version_json_path.parent.mkdir(parents=True, exist_ok=True)
        version_json_path.write_text(json.dumps(version_data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log.emit(f"版本详情已保存: {version_json_path}")
        return version_data

    def _download_core_files(self, version_data: dict):
        tasks = []
        client_info = version_data.get("downloads", {}).get("client")
        if client_info:
            tasks.append({"url": client_info["url"],
                          "path": self.mc_dir / "versions" / self.version_id / f"{self.version_id}.jar",
                          "sha1": client_info["sha1"], "size": client_info.get("size", 0)})

        asset_index = version_data.get("assetIndex")
        if asset_index:
            tasks.append(
                {"url": asset_index["url"], "path": self.mc_dir / "assets" / "indexes" / f"{asset_index['id']}.json",
                 "sha1": asset_index["sha1"], "size": asset_index.get("size", 0)})

        logging_info = version_data.get("logging", {}).get("client", {}).get("file")
        if logging_info:
            tasks.append(
                {"url": logging_info["url"], "path": self.mc_dir / "assets" / "log_configs" / logging_info["id"],
                 "sha1": logging_info["sha1"], "size": logging_info.get("size", 0)})

        for task in tasks:
            if self._cancelled: return asset_index
            self.log.emit(f"下载核心文件: {task['path'].name}")
            url = get_download_url(task["url"], self.use_mirror)
            try:
                self._download_one(url, task["path"], task["sha1"])
                self.log.emit(f"[OK] {task['path'].name}")
            except Exception as e:
                self.log.emit(f"[FAIL] {task['path'].name}: {e}")
        return asset_index

    def _generate_library_tasks(self, version_data: dict) -> list:
        tasks = []
        for lib in version_data.get("libraries", []):
            allowed = True
            for rule in lib.get("rules", []):
                os_name = rule.get("os", {}).get("name")
                if rule.get("action") == "allow" and os_name not in [None, "windows"]:
                    allowed = False;
                    break
                if rule.get("action") == "disallow" and os_name == "windows":
                    allowed = False;
                    break
            if not allowed: continue
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                tasks.append({"url": artifact["url"], "path": self.mc_dir / "libraries" / artifact["path"],
                              "sha1": artifact["sha1"], "size": artifact.get("size", 0)})
        return tasks

    def _generate_asset_tasks(self, asset_index: dict) -> list:
        tasks = []
        index_path = self.mc_dir / "assets" / "indexes" / f"{asset_index['id']}.json"
        if not index_path.exists():
            self.log.emit("[ERROR] 找不到资源索引文件")
            return tasks

        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        for _logical, info in index_data.get("objects", {}).items():
            h = info.get("hash")
            if not h: continue
            prefix = h[:2]
            tasks.append({"url": f"https://resources.download.minecraft.net/{prefix}/{h}",
                          "path": self.mc_dir / "assets" / "objects" / prefix / h, "sha1": h,
                          "size": info.get("size", 0)})
        return tasks

    def _execute_download_tasks(self, tasks: list, task_name: str):
        if not tasks: return

        total = 0
        pending = []
        for t in tasks:
            if t["path"].exists() and t.get("sha1") and verify_sha1(t["path"], t["sha1"]): continue
            pending.append(t)
            total += t.get("size", 0)

        if not pending:
            self.log.emit(f"{task_name}：全部已存在，跳过")
            return

        with self._lock:
            self._done_bytes = 0
            self._total_bytes = total
        self.stage.emit(task_name)
        self.progress.emit(0, total)
        self.log.emit(f"开始下载 {task_name}（共 {len(pending)} 个文件，{self.threads} 线程）")

        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=self.threads, pool_maxsize=self.threads)
        session.mount("https://", adapter)

        def worker(task):
            if self._cancelled: return
            try:
                url = get_download_url(task["url"], self.use_mirror)
                self._download_one(url, task["path"], task.get("sha1"), session)
            except Exception as e:
                self.log.emit(f"[FAIL] {task['path'].name}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as ex:
            futures = [ex.submit(worker, t) for t in pending]
            for _ in concurrent.futures.as_completed(futures):
                if self._cancelled: break
        self.log.emit(f"{task_name}处理完毕")

    def _download_one(self, url: str, path: Path, expected_sha1: str = None, session=None):
        if path.exists() and expected_sha1 and verify_sha1(path, expected_sha1): return "SKIP"
        path.parent.mkdir(parents=True, exist_ok=True)

        getter = session.get if session else requests.get
        last_err = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            if self._cancelled: return "CANCELLED"
            try:
                if self.use_mirror: time.sleep(0.1)
                resp = getter(url, headers=HEADERS, stream=True, timeout=30, proxies=PROXIES)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(self.CHUNK_SIZE):
                        if self._cancelled: return "CANCELLED"
                        f.write(chunk)
                        with self._lock:
                            self._done_bytes += len(chunk)
                            done = self._done_bytes
                            total = self._total_bytes
                        if total > 0: self.progress.emit(done, total)
                return "OK"
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    self.log.emit(f"[RETRY {attempt}/{self.MAX_RETRIES}] {path.name}: {e}")
                    time.sleep(1 * attempt)
                else:
                    raise last_err
        return "FAIL"