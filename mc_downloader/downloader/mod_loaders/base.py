# mc_downloader/downloader/mod_loaders/base.py
"""
Base class for mod loader installers.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import concurrent.futures
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests

from mc_downloader.core.constants import HEADERS, PROXIES, MAX_RETRIES, CHUNK_SIZE
from mc_downloader.core.utils import (
    fetch_json, get_download_url, download_file, ProgressTracker, verify_sha1,
    apply_rules,
)
from mc_downloader.core.java_env import find_java, java_version


class ModLoaderInstaller(ABC):
    """Base class for mod loader installers."""
    
    # Class-level attributes for identification without instantiation
    loader_name: str = ""
    loader_display_name: str = ""
    
    def __init__(
        self,
        mc_version: str = "",
        mc_dir: Path = None,
        threads: int = 8,
        use_mirror: bool = False,
        log_callback=None,
        progress_callback=None,
        stage_callback=None,
        cancelled_callback=None,
        run_java_installer: bool = False,
        java_path: str = "",
    ):
        self.mc_version = mc_version
        self.mc_dir = mc_dir or Path(".")
        self.use_mirror = use_mirror
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda done, total: None)
        self.stage_callback = stage_callback or (lambda name: None)
        self.cancelled_callback = cancelled_callback or (lambda: False)

        # 可选：调用 Java 安装器补全数据处理器产物
        self.run_java_installer = run_java_installer
        self.java_path = java_path

        self.threads = max(1, min(threads, 16 if use_mirror else 64))
        self._progress_tracker = ProgressTracker()
        self._progress_tracker.set_listener(self.progress_callback)
        self._session = None
        self._version_data = None
    
    @property
    def cancelled(self) -> bool:
        return self.cancelled_callback()
    
    def _log(self, msg: str):
        self.log_callback(msg)

    def _new_tracker(self) -> ProgressTracker:
        """创建绑定到 progress_callback 的新进度计数器（每个阶段独立）。"""
        tracker = ProgressTracker()
        tracker.set_listener(self.progress_callback)
        self._progress_tracker = tracker
        return tracker
    
    def _get_session(self) -> requests.Session:
        """Get or create requests session with connection pooling."""
        if self._session is None:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=self.threads,
                pool_maxsize=self.threads,
            )
            self._session.mount("https://", adapter)
        return self._session

    # ------------------------------------------------------------ Java 安装器

    def _resolve_java(self) -> Optional[Path]:
        """定位可用的 Java；找不到时记录提示并返回 None。"""
        java = find_java(self.java_path)
        if java is None:
            self._log("[WARN] 未找到 Java，无法运行安装器补全数据处理器产物。")
            self._log("       可安装 JDK 17/21，或在设置中指定 java 路径。")
            return None
        self._log(f"使用 Java: {java}")
        version = java_version(java)
        if version:
            self._log(f"Java 版本: {version}")
        return java

    def _ensure_launcher_profiles(self) -> Path:
        """
        Forge/NeoForge 官方安装器要求 .minecraft 下存在 launcher_profiles.json，
        否则会报 “There is no Minecraft launcher profile” 并中止。

        下载器创建的 .minecraft 没有这个文件，这里生成一个最小可用版本。
        """
        path = self.mc_dir / "launcher_profiles.json"
        if path.exists() and path.stat().st_size > 2:
            return path

        data = {
            "profiles": {},
            "selectedProfile": "",
            "clientToken": "",
            "authenticationDatabase": {},
            "launcherVersion": {"name": "MC-Downloader", "format": 1},
            "settings": {"locale": "zh_CN"},
            "version": 3,
        }
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._log(f"已创建启动器配置文件: {path.name}")
        except Exception as e:  # noqa: BLE001
            self._log(f"[WARN] 创建 launcher_profiles.json 失败: {e}")
        return path

    def _prepare_installer_temp(self) -> Path:
        """
        为安装器准备一个确定可写的临时目录。

        优先级：.minecraft/temp → 系统临时目录 → 用户主目录。
        逐个尝试写入，全部失败时回退到系统临时目录。
        """
        import os as _os
        import tempfile

        candidates = [
            self.mc_dir / "temp",
            Path(tempfile.gettempdir()),
            Path(_os.path.expanduser("~")) / ".mc_downloader_tmp",
        ]

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / f".write_test_{_os.getpid()}"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                return candidate
            except Exception:  # noqa: BLE001
                continue

        return Path(tempfile.gettempdir())

    def _run_installer_java(self, installer_jar: Path, timeout: int = 900) -> bool:
        """
        执行安装器：java -jar <installer>.jar --installClient <mc_dir>

        这一步会运行 Forge/NeoForge 的数据处理器，生成 srg / extra /
        patched 等补全文件（缺失会导致游戏启动崩溃）。
        输出实时转发到日志。
        """
        java = self._resolve_java()
        if java is None:
            return False

        if self.cancelled:
            return False

        # 官方安装器要求存在 launcher_profiles.json
        self._ensure_launcher_profiles()

        # 安装器以进程 cwd 会变，这里统一使用绝对路径
        installer_jar = Path(installer_jar).resolve()
        mc_dir = Path(self.mc_dir).resolve()

        cmd = [str(java), "-jar", str(installer_jar),
               "--installClient", str(mc_dir)]

        self._log(f"执行安装器: {' '.join(cmd)}")
        self.stage_callback("运行安装器 (Java)")

        env = dict(os.environ)
        env.setdefault("JAVA_TOOL_OPTIONS", "")
        # 部分安装器在非 UTF-8 环境下会乱码或报错
        env.setdefault("LANG", "en_US.UTF-8")

        # 安装器会在系统临时目录创建 forge_installerXXXX 工作目录。
        # 若继承的 TEMP 不可写（沙箱、权限受限、代理软件重定向等），
        # 会直接抛 AccessDeniedException，因此这里指定一个确定可写的目录。
        temp_dir = self._prepare_installer_temp()
        env["TEMP"] = env["TMP"] = str(temp_dir)
        env["TMPDIR"] = str(temp_dir)

        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(mc_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=flags,
            )
        except FileNotFoundError:
            self._log("[ERROR] 无法启动 Java，请检查 Java 安装是否完整")
            return False
        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] 启动安装器失败: {e}")
            return False

        # 实时读取输出；超时或取消时终止进程
        lines: queue.Queue[Optional[str]] = queue.Queue()

        def reader():
            try:
                for line in proc.stdout:  # type: ignore[union-attr]
                    lines.put(line.rstrip())
            finally:
                lines.put(None)

        threading.Thread(target=reader, daemon=True).start()

        import time
        deadline = time.monotonic() + timeout
        cancelled = False

        while True:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                line = ""

            if line is None:  # 输出结束
                break
            if line:
                self._log(f"  {line}")

            if self.cancelled:
                cancelled = True
                proc.terminate()
                self._log("[WARN] 已请求取消，正在终止安装器…")
                break

            if time.monotonic() > deadline:
                proc.terminate()
                self._log(f"[ERROR] 安装器执行超时（{timeout} 秒）")
                return False

        try:
            returncode = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = -1

        if cancelled or self.cancelled:
            return False

        if returncode == 0:
            self._log("安装器执行成功")
            return True

        self._log(f"[ERROR] 安装器返回非零代码: {returncode}")
        return False

    def _installer_products(self) -> List[Path]:
        """安装器补全流程需要生成的关键文件（用于校验）。"""
        return []

    def _verify_installer_products(self) -> bool:
        """校验安装器产物是否齐全。"""
        missing = [p for p in self._installer_products() if not p.exists()]
        if not missing:
            return True
        for p in missing:
            self._log(f"[WARN] 缺失文件: {p}")
        return False

    
    @abstractmethod
    def fetch_loader_versions(self) -> List[Dict[str, Any]]:
        """Fetch available loader versions for the Minecraft version."""
        pass
    
    @abstractmethod
    def get_installer_url(self, loader_version: str) -> str:
        """Get the installer/download URL for a specific loader version."""
        pass
    
    @abstractmethod
    def install_loader(self, loader_version: str) -> bool:
        """Install the mod loader."""
        pass
    
    def _download_libraries(self, libraries: List[Dict], task_name: str) -> bool:
        """下载依赖库（自动跳过其他平台 / 已存在 / 无法下载的构件）。"""
        tasks = []
        for lib in libraries:
            if not apply_rules(lib.get("rules", []), "windows"):
                continue
            artifact = lib.get("downloads", {}).get("artifact")
            if not artifact:
                continue
            # Forge/NeoForge 的 client、patched 等构件 URL 为空，
            # 需要安装器处理器生成，跳过而不是报 Invalid URL
            if not artifact.get("url") or not artifact.get("path"):
                self._log(f"跳过无法直接下载的构件: {lib.get('name', '?')}")
                continue
            tasks.append({
                "url": artifact["url"],
                "path": self.mc_dir / "libraries" / artifact["path"],
                "sha1": artifact.get("sha1"),
                "size": artifact.get("size", 0),
            })

        if tasks:
            self._execute_download_tasks(tasks, task_name)
        return True
    
    def _execute_download_tasks(self, tasks: list, task_name: str):
        """Execute download tasks with thread pool."""
        if not tasks:
            return
        
        pending = []
        total_size = 0
        for t in tasks:
            if not t.get("url"):
                self._log(f"跳过缺少下载地址的文件: {t['path'].name}")
                continue
            if t["path"].exists() and t.get("sha1") and verify_sha1(t["path"], t["sha1"]):
                continue
            pending.append(t)
            total_size += t.get("size", 0)
        
        if not pending:
            self._log(f"{task_name}：全部已存在，跳过")
            return
        
        # 每个阶段使用全新的进度计数
        tracker = self._new_tracker()
        tracker.set_total(total_size)
        self.stage_callback(task_name)
        self.progress_callback(0, total_size)
        self._log(f"开始下载 {task_name}（共 {len(pending)} 个文件，{self.threads} 线程）")
        
        session = self._get_session()
        
        def worker(task):
            if self.cancelled:
                return
            try:
                download_file(
                    task["url"], task["path"], task.get("sha1"),
                    progress_tracker=tracker,
                    session=session,
                    use_mirror=self.use_mirror
                )
            except Exception as e:
                self._log(f"[FAIL] {task['path'].name}: {e}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as ex:
            futures = [ex.submit(worker, t) for t in pending]
            for _ in concurrent.futures.as_completed(futures):
                if self.cancelled:
                    break

        # 确保进度条到达 100%
        self.progress_callback(total_size, total_size)
        self._log(f"{task_name}处理完毕")
    
    def _save_version_json(self, version_id: str, version_data: dict):
        """Save version.json file."""
        version_json_path = self.mc_dir / "versions" / version_id / f"{version_id}.json"
        version_json_path.parent.mkdir(parents=True, exist_ok=True)
        version_json_path.write_text(
            json.dumps(version_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        self._log(f"版本详情已保存: {version_json_path}")
    
    def _merge_version_json(self, base_version: str, loader_version_data: dict) -> dict:
        """
        Merge loader version data with vanilla version data.
        This creates a new version that includes both vanilla and loader libraries.
        """
        # Load vanilla version data
        vanilla_path = self.mc_dir / "versions" / base_version / f"{base_version}.json"
        if not vanilla_path.exists():
            raise ValueError(f"原版版本 {base_version} 未下载，请先下载原版")
        
        vanilla_data = json.loads(vanilla_path.read_text(encoding="utf-8"))
        
        # Merge libraries
        vanilla_libs = {lib.get("name", ""): lib for lib in vanilla_data.get("libraries", [])}
        loader_libs = loader_version_data.get("libraries", [])
        
        for loader_lib in loader_libs:
            lib_name = loader_lib.get("name", "")
            if lib_name:
                vanilla_libs[lib_name] = loader_lib
        
        vanilla_data["libraries"] = list(vanilla_libs.values())
        
        # Update main class if provided
        if "mainClass" in loader_version_data:
            vanilla_data["mainClass"] = loader_version_data["mainClass"]
        
        # Update inheritsFrom if needed
        if "inheritsFrom" in loader_version_data:
            vanilla_data["inheritsFrom"] = loader_version_data["inheritsFrom"]
        
        return vanilla_data