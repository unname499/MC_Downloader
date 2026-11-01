# mc_downloader/ui/workers.py
"""
UI Workers - QThread wrappers for downloaders.

- 安装模组加载器时，若原版缺失会先自动补齐原版文件。
- 进度通过节流后 emit，避免每个数据块都排队一个跨线程事件
  （高并发下载时这会让进度事件堆积并滞后，看起来像“进度条没反应”）。
"""
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from mc_downloader.downloader import VanillaDownloader, get_installer
from mc_downloader.core.utils import fetch_version_list

# 进度信号最小发送间隔（秒）
PROGRESS_INTERVAL = 0.1


class VersionFetcher(QThread):
    """后台线程：拉取版本列表。"""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, use_mirror: bool, parent=None):
        super().__init__(parent)
        self.use_mirror = use_mirror

    def run(self):
        try:
            self.finished.emit(fetch_version_list(self.use_mirror))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ModLoaderVersionFetcher(QThread):
    """后台线程：拉取某个模组加载器的版本列表。"""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, loader_name: str, mc_version: str, use_mirror: bool, parent=None):
        super().__init__(parent)
        self.loader_name = loader_name
        self.mc_version = mc_version
        self.use_mirror = use_mirror

    def run(self):
        try:
            installer_class = get_installer(self.loader_name)
            if not installer_class:
                self.failed.emit(f"未知的模组加载器: {self.loader_name}")
                return

            installer = installer_class(
                mc_version=self.mc_version,
                mc_dir=Path("."),
                use_mirror=self.use_mirror,
            )
            self.finished.emit(installer.fetch_loader_versions())
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class UnifiedDownloadWorker(QThread):
    """统一下载/安装工作线程。"""

    log = Signal(str)
    progress = Signal(int, int)      # (当前字节, 总字节)
    stage = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)
    cancelled_sig = Signal()

    def __init__(
        self,
        version_id: str,
        mc_dir: Path,
        loader_name: Optional[str] = None,
        loader_version: Optional[str] = None,
        threads: int = 8,
        use_mirror: bool = False,
        run_java_installer: bool = False,
        java_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.version_id = version_id
        self.mc_dir = mc_dir
        self.loader_name = loader_name
        self.loader_version = loader_version
        self.use_mirror = use_mirror
        self.run_java_installer = run_java_installer
        self.java_path = java_path
        self.threads = max(1, min(threads, 16 if use_mirror else 64))
        self._cancelled = False

        # 进度节流状态
        self._last_emit = 0.0
        self._last_value = -1

    # ------------------------------------------------------------------ 控制

    def cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    # ------------------------------------------------------------------ 进度

    def _on_progress(self, done: int, total: int):
        """节流后的阶段进度（跨线程 emit 到 UI）。"""
        if total <= 0:
            return
        now = time.monotonic()
        value = int(done * 1000 / total)
        finished = done >= total
        if not finished:
            if value == self._last_value:
                return
            if now - self._last_emit < PROGRESS_INTERVAL:
                return
        self._last_emit = now
        self._last_value = value
        self.progress.emit(done, total)

    def _reset_progress(self):
        self._last_emit = 0.0
        self._last_value = -1

    # ------------------------------------------------------------------ 主流程

    def run(self):
        try:
            self._emit_source()

            if self.loader_name:
                self.log.emit(
                    f"===== 开始安装 {self.loader_name.capitalize()} "
                    f"{self.version_id}-{self.loader_version} ====="
                )
                self._install_mod_loader()
            else:
                self.log.emit(f"===== 开始下载 Minecraft {self.version_id} =====")
                self._download_vanilla()

            if self.cancelled:
                self.cancelled_sig.emit()
                return

            self.log.emit("===== 全部完成！ =====")
            self.finished_ok.emit()

        except Exception as e:  # noqa: BLE001
            if self.cancelled:
                self.cancelled_sig.emit()
            else:
                self.failed.emit(str(e))

    def _emit_source(self):
        if self.use_mirror:
            self.log.emit("镜像源：BMCLAPI (https://bmclapi2.bangbang93.com)")
        else:
            self.log.emit("镜像源：Mojang 官方")

    # ------------------------------------------------------------------ 原版

    def _download_vanilla(self) -> bool:
        downloader = VanillaDownloader(
            version_id=self.version_id,
            mc_dir=self.mc_dir,
            threads=self.threads,
            use_mirror=self.use_mirror,
            log_callback=self.log.emit,
            progress_callback=self._on_progress,
            stage_callback=self.stage.emit,
            cancelled_callback=lambda: self.cancelled,
        )
        return downloader.download()

    # ------------------------------------------------------------------ 模组加载器

    def _install_mod_loader(self):
        installer_class = get_installer(self.loader_name)
        if not installer_class:
            raise ValueError(f"未知的模组加载器: {self.loader_name}")

        # 原版缺失或客户端 jar 不存在时自动补齐
        if not self._vanilla_ready():
            self.log.emit(f"未检测到完整的 Minecraft {self.version_id}，先下载原版文件…")
            self.stage.emit("原版游戏文件")
            if not self._download_vanilla():
                raise RuntimeError(f"下载 Minecraft {self.version_id} 失败，无法继续安装加载器")
            if self.cancelled:
                return
            self._reset_progress()

        installer = installer_class(
            mc_version=self.version_id,
            mc_dir=self.mc_dir,
            threads=self.threads,
            use_mirror=self.use_mirror,
            log_callback=self.log.emit,
            progress_callback=self._on_progress,
            stage_callback=self.stage.emit,
            cancelled_callback=lambda: self.cancelled,
            run_java_installer=self.run_java_installer,
            java_path=self.java_path,
        )

        if not installer.install_loader(self.loader_version):
            raise RuntimeError(f"{self.loader_name} 安装失败")

    def _vanilla_ready(self) -> bool:
        """原版版本 JSON 与客户端 jar 是否就绪。"""
        base = self.mc_dir / "versions" / self.version_id
        return (base / f"{self.version_id}.json").exists() and (base / f"{self.version_id}.jar").exists()
