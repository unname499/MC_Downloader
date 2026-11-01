# mc_downloader/downloader/vanilla.py
"""
Vanilla Minecraft downloader.
Handles downloading vanilla Minecraft versions (client jar, libraries, assets).
"""
import json
import concurrent.futures
from pathlib import Path
from typing import Optional

import requests

from mc_downloader.core.constants import (
    OFFICIAL_MANIFEST_URL, MIRROR_MANIFEST_URL,
    MIRROR_MAX_THREADS, OFFICIAL_MAX_THREADS
)
from mc_downloader.core.utils import (
    fetch_json, get_download_url, download_file, apply_rules,
    ProgressTracker, verify_sha1
)


class VanillaDownloader:
    """Handles vanilla Minecraft downloads."""
    
    def __init__(
        self,
        version_id: str,
        mc_dir: Path,
        threads: int = 8,
        use_mirror: bool = False,
        log_callback=None,
        progress_callback=None,
        stage_callback=None,
        cancelled_callback=None
    ):
        self.version_id = version_id
        self.mc_dir = mc_dir
        self.use_mirror = use_mirror
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda done, total: None)
        self.stage_callback = stage_callback or (lambda name: None)
        self.cancelled_callback = cancelled_callback or (lambda: False)
        
        # Adjust threads based on mirror usage
        if use_mirror:
            self.threads = max(1, min(threads, MIRROR_MAX_THREADS))
        else:
            self.threads = max(1, min(threads, OFFICIAL_MAX_THREADS))
        
        self._progress_tracker = ProgressTracker()
        self._progress_tracker.set_listener(self.progress_callback)
        self._session = None
        self._version_data = None
    
    @property
    def cancelled(self) -> bool:
        return self.cancelled_callback()
    
    def _new_tracker(self) -> ProgressTracker:
        """创建绑定到 progress_callback 的新进度计数器（每个阶段独立）。"""
        tracker = ProgressTracker()
        tracker.set_listener(self.progress_callback)
        self._progress_tracker = tracker
        return tracker

    def _log(self, msg: str):
        self.log_callback(msg)
    
    def _get_manifest_url(self) -> str:
        return MIRROR_MANIFEST_URL if self.use_mirror else OFFICIAL_MANIFEST_URL
    
    def _get_version_data(self) -> dict:
        """获取版本清单与版本详情（镜像失败时自动回退官方源）。"""
        self._log(f"正在获取版本 {self.version_id} 的清单...")

        manifest = None
        for candidate in ([MIRROR_MANIFEST_URL, OFFICIAL_MANIFEST_URL]
                          if self.use_mirror else [OFFICIAL_MANIFEST_URL]):
            try:
                manifest = fetch_json(candidate, use_mirror=False)
                break
            except Exception as e:  # noqa: BLE001
                self._log(f"[WARN] 清单源失败 {candidate}: {e}")
        if manifest is None:
            raise RuntimeError("无法获取版本清单（镜像与官方源均失败）")

        target_url = next(
            (v["url"] for v in manifest["versions"] if v["id"] == self.version_id),
            None
        )
        if not target_url:
            raise ValueError(f"找不到版本: {self.version_id}")

        version_data = None
        for candidate in ([get_download_url(target_url, True), target_url]
                          if self.use_mirror else [target_url]):
            try:
                version_data = fetch_json(candidate, use_mirror=False)
                break
            except Exception as e:  # noqa: BLE001
                self._log(f"[WARN] 获取版本详情失败 {candidate}: {e}")
        if version_data is None:
            raise RuntimeError(f"无法获取 Minecraft {self.version_id} 的版本详情")
        
        # Save version.json
        version_json_path = self.mc_dir / "versions" / self.version_id / f"{self.version_id}.json"
        version_json_path.parent.mkdir(parents=True, exist_ok=True)
        version_json_path.write_text(
            json.dumps(version_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        self._log(f"版本详情已保存: {version_json_path}")
        
        self._version_data = version_data
        return version_data
    
    def _download_core_files(self, version_data: dict) -> Optional[dict]:
        """下载客户端 jar、资源索引、日志配置（显示逐文件进度）。"""
        tasks = []

        # Client jar
        client_info = version_data.get("downloads", {}).get("client")
        if client_info:
            tasks.append({
                "url": client_info["url"],
                "path": self.mc_dir / "versions" / self.version_id / f"{self.version_id}.jar",
                "sha1": client_info["sha1"],
                "size": client_info.get("size", 0)
            })

        # Asset index
        asset_index = version_data.get("assetIndex")
        if asset_index:
            tasks.append({
                "url": asset_index["url"],
                "path": self.mc_dir / "assets" / "indexes" / f"{asset_index['id']}.json",
                "sha1": asset_index["sha1"],
                "size": asset_index.get("size", 0)
            })

        # Logging config
        logging_info = version_data.get("logging", {}).get("client", {}).get("file")
        if logging_info:
            tasks.append({
                "url": logging_info["url"],
                "path": self.mc_dir / "assets" / "log_configs" / logging_info["id"],
                "sha1": logging_info["sha1"],
                "size": logging_info.get("size", 0)
            })

        if not tasks:
            return asset_index

        # 按文件总大小推进进度条（核心文件通常包含一个较大的客户端 jar）
        total = sum(t.get("size", 0) for t in tasks) or 1
        tracker = self._new_tracker()
        tracker.set_total(total)
        self.stage_callback("核心文件")
        self.progress_callback(0, total)

        self._ensure_session()
        for task in tasks:
            if self.cancelled:
                return asset_index
            self._log(f"下载核心文件: {task['path'].name}")
            try:
                download_file(
                    task["url"], task["path"], task["sha1"],
                    progress_tracker=tracker,
                    session=self._session,
                    use_mirror=self.use_mirror
                )
                self._log(f"[OK] {task['path'].name}")
            except Exception as e:  # noqa: BLE001
                self._log(f"[FAIL] {task['path'].name}: {e}")

        # 确保进度条到达 100%
        self.progress_callback(total, total)
        return asset_index

    def _ensure_session(self):
        """创建带连接池的会话。"""
        if self._session is None:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=self.threads, pool_maxsize=self.threads
            )
            self._session.mount("https://", adapter)
    
    def _generate_library_tasks(self, version_data: dict) -> list:
        """Generate library download tasks."""
        tasks = []
        for lib in version_data.get("libraries", []):
            if not apply_rules(lib.get("rules", []), "windows"):
                continue
            
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                tasks.append({
                    "url": artifact["url"],
                    "path": self.mc_dir / "libraries" / artifact["path"],
                    "sha1": artifact["sha1"],
                    "size": artifact.get("size", 0)
                })
        return tasks
    
    def _generate_asset_tasks(self, asset_index: dict) -> list:
        """Generate asset download tasks from asset index."""
        tasks = []
        index_path = self.mc_dir / "assets" / "indexes" / f"{asset_index['id']}.json"
        
        if not index_path.exists():
            self._log("[ERROR] 找不到资源索引文件")
            return tasks
        
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        for _logical, info in index_data.get("objects", {}).items():
            h = info.get("hash")
            if not h:
                continue
            prefix = h[:2]
            tasks.append({
                "url": f"https://resources.download.minecraft.net/{prefix}/{h}",
                "path": self.mc_dir / "assets" / "objects" / prefix / h,
                "sha1": h,
                "size": info.get("size", 0)
            })
        return tasks
    
    def _execute_download_tasks(self, tasks: list, task_name: str):
        """Execute download tasks with thread pool."""
        if not tasks:
            return
        
        # Filter out already downloaded and verified files
        pending = []
        total_size = 0
        for t in tasks:
            if t["path"].exists() and t.get("sha1") and verify_sha1(t["path"], t["sha1"]):
                continue
            pending.append(t)
            total_size += t.get("size", 0)
        
        if not pending:
            self._log(f"{task_name}：全部已存在，跳过")
            return
        
        # 每个阶段使用全新的进度计数，避免总量与已完成量错乱
        tracker = self._new_tracker()
        tracker.set_total(total_size)
        self.stage_callback(task_name)
        self.progress_callback(0, total_size)
        self._log(f"开始下载 {task_name}（共 {len(pending)} 个文件，{self.threads} 线程）")
        
        # 连接池会话
        self._ensure_session()
        
        def worker(task):
            if self.cancelled:
                return
            try:
                download_file(
                    task["url"], task["path"], task.get("sha1"),
                    progress_tracker=tracker,
                    session=self._session,
                    use_mirror=self.use_mirror
                )
            except Exception as e:
                self._log(f"[FAIL] {task['path'].name}: {e}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as ex:
            futures = [ex.submit(worker, t) for t in pending]
            for _ in concurrent.futures.as_completed(futures):
                if self.cancelled:
                    break
        
        self._log(f"{task_name}处理完毕")
    
    def download(self) -> bool:
        """Main download entry point."""
        try:
            if self.use_mirror:
                self._log("镜像源：BMCLAPI (https://bmclapi2.bangbang93.com)")
            else:
                self._log("镜像源：Mojang 官方")
            self._log(f"===== 开始下载 Minecraft {self.version_id} =====")
            
            version_data = self._get_version_data()
            if self.cancelled:
                return False
            
            asset_index = self._download_core_files(version_data)
            if not asset_index:
                self._log("[ERROR] 没有获取到 assetIndex")
                return False
            
            if self.cancelled:
                return False
            
            lib_tasks = self._generate_library_tasks(version_data)
            self._execute_download_tasks(lib_tasks, "依赖库")
            
            if self.cancelled:
                return False
            
            asset_tasks = self._generate_asset_tasks(asset_index)
            self._execute_download_tasks(asset_tasks, "资源文件")
            
            self._log("===== 全部下载完成！ =====")
            return True
            
        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] {e}")
            return False