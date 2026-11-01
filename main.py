# main.py
"""
MC Downloader - 主入口。

结构：
    mc_downloader/core       常量与通用下载工具
    mc_downloader/downloader 原版下载 + 模组加载器安装
    mc_downloader/ui         Qt 工作线程与设置窗口
"""
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QLineEdit, QTextEdit,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer
import qdarktheme

from mc_downloader.config import (
    read_conf, write_default_conf, is_first_run, get_bool, get_int, get_str,
)
from mc_downloader.ui.workers import (
    VersionFetcher, ModLoaderVersionFetcher, UnifiedDownloadWorker,
)
from mc_downloader.downloader.mod_loaders import list_loaders, MOD_LOADERS
from mc_downloader.ui.settings_window import SettingsWindow

WELCOME_MSG = "欢迎使用 MC Downloader！首次运行请先完成设置。"


def _human_size(num: float) -> str:
    """把字节数格式化为可读大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC Downloader v2.0")
        self.resize(940, 660)

        # ---- 状态 ----
        self._worker = None
        self._fetcher = None
        self._loader_fetcher = None
        self._valid_versions: set[str] = set()
        self._current_loader = "vanilla"
        self._pending_auto_fetch = False
        self._loaded_loader_key = None

        # ---- 配置 ----
        self._first_run = is_first_run()
        self.config = write_default_conf() if self._first_run else read_conf()

        self._build_ui()
        self._apply_config(self.config)

        QTimer.singleShot(100, self.on_refresh_versions)

    # ================================================================== UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(self._build_game_group())
        root.addWidget(self._build_loader_group())

        # 目录
        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("下载目录："))
        self.edit_dir = QLineEdit()
        row_dir.addWidget(self.edit_dir, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self.on_browse)
        row_dir.addWidget(btn_browse)
        root.addLayout(row_dir)

        # 进度
        self.label_stage = QLabel("就绪")
        root.addWidget(self.label_stage)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setPlaceholderText("下载日志将显示在这里…")
        root.addWidget(self.text_log, 1)

        # 操作按钮
        row_btn = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setMinimumHeight(34)
        self.btn_start.clicked.connect(self.on_start)
        row_btn.addWidget(self.btn_start, 2)

        self.btn_settings = QPushButton("设置")
        self.btn_settings.clicked.connect(self.on_settings)
        row_btn.addWidget(self.btn_settings)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.on_cancel)
        row_btn.addWidget(self.btn_cancel)

        row_btn.addStretch()

        btn_exit = QPushButton("退出")
        btn_exit.clicked.connect(self.close)
        row_btn.addWidget(btn_exit)
        root.addLayout(row_btn)

    def _build_game_group(self) -> QGroupBox:
        box = QGroupBox("游戏版本")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("Minecraft 版本："), 0, 0)
        self.combo_version = QComboBox()
        self.combo_version.setEditable(True)
        self.combo_version.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_version.lineEdit().setPlaceholderText("正在获取版本...")
        self.combo_version.currentTextChanged.connect(self._on_version_text_changed)
        grid.addWidget(self.combo_version, 0, 1)

        self.btn_refresh = QPushButton("刷新列表")
        self.btn_refresh.clicked.connect(self.on_refresh_versions)
        grid.addWidget(self.btn_refresh, 0, 2)

        return box

    def _build_loader_group(self) -> QGroupBox:
        box = QGroupBox("模组加载器（可选）")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("加载器："), 0, 0)
        self.combo_loader = QComboBox()
        self.combo_loader.addItem("原版（Vanilla）", "vanilla")
        for loader_id in list_loaders():
            self.combo_loader.addItem(MOD_LOADERS[loader_id].loader_display_name, loader_id)
        self.combo_loader.currentIndexChanged.connect(self.on_loader_changed)
        grid.addWidget(self.combo_loader, 0, 1)

        self.combo_loader_version = QComboBox()
        self.combo_loader_version.setEditable(True)
        self.combo_loader_version.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_loader_version.setEnabled(False)
        self.combo_loader_version.lineEdit().setPlaceholderText("原版无需选择加载器版本")
        grid.addWidget(self.combo_loader_version, 1, 1)

        self.btn_refresh_loader = QPushButton("刷新")
        self.btn_refresh_loader.clicked.connect(self.on_refresh_loader_versions)
        self.btn_refresh_loader.setEnabled(False)
        grid.addWidget(self.btn_refresh_loader, 1, 2)

        return box

    def _apply_config(self, config):
        self.config = config
        self.edit_dir.setText(get_str(config, "minecraft_dir"))

        idx = self.combo_loader.findData(get_str(config, "default_loader", "vanilla"))
        if idx >= 0 and idx != self.combo_loader.currentIndex():
            self.combo_loader.blockSignals(True)
            self.combo_loader.setCurrentIndex(idx)
            self.combo_loader.blockSignals(False)
            self._current_loader = self.combo_loader.currentData()

    # ================================================================== 版本列表

    def on_refresh_versions(self):
        if self._fetcher is not None and self._fetcher.isRunning():
            return

        self.btn_refresh.setEnabled(False)
        self.combo_version.lineEdit().setPlaceholderText("正在获取版本列表...")
        self._valid_versions.clear()

        self._fetcher = VersionFetcher(get_bool(self.config, "use_mirror", True), self)
        self._fetcher.finished.connect(self._on_versions_fetched)
        self._fetcher.failed.connect(self._on_versions_fetch_failed)
        self._fetcher.start()

    def _on_versions_fetched(self, versions: list):
        self.btn_refresh.setEnabled(True)
        self.combo_version.lineEdit().setPlaceholderText("选择或输入版本号")
        self._valid_versions = {v["id"] for v in versions}

        current = self.combo_version.currentText().strip()
        self.combo_version.blockSignals(True)
        self.combo_version.clear()
        for v in versions:
            self.combo_version.addItem(v["id"])
        idx = self.combo_version.findText(current)
        if idx >= 0:
            self.combo_version.setCurrentIndex(idx)
        elif current:
            self.combo_version.setEditText(current)
        else:
            # 默认选中最新的正式版
            release = next((v["id"] for v in versions if v["type"] == "release"), None)
            if release:
                self.combo_version.setCurrentText(release)
        self.combo_version.blockSignals(False)

        self.append_log(f"版本列表已更新，共 {len(versions)} 个版本")
        self._maybe_fetch_loader_versions()

    def _on_versions_fetch_failed(self, err: str):
        self.btn_refresh.setEnabled(True)
        self.combo_version.lineEdit().setPlaceholderText("获取失败，点击刷新重试")
        self.append_log(f"[WARN] 获取版本列表失败：{err}")

    def _on_version_text_changed(self, _text: str):
        self._maybe_fetch_loader_versions()

    # ================================================================== 模组加载器

    def on_loader_changed(self, index: int):
        loader_id = self.combo_loader.itemData(index)
        self._current_loader = loader_id

        if loader_id == "vanilla":
            self.combo_loader_version.blockSignals(True)
            self.combo_loader_version.clear()
            self.combo_loader_version.blockSignals(False)
            self.combo_loader_version.setEnabled(False)
            self.combo_loader_version.lineEdit().setPlaceholderText("原版无需选择加载器版本")
            self.btn_refresh_loader.setEnabled(False)
        else:
            self.combo_loader_version.setEnabled(True)
            self.combo_loader_version.lineEdit().setPlaceholderText("正在获取加载器版本...")
            self.btn_refresh_loader.setEnabled(True)
            self._loaded_loader_key = None
            self._maybe_fetch_loader_versions()

    def _maybe_fetch_loader_versions(self):
        """MC 版本有效且选中了加载器时，自动拉取加载器版本列表。"""
        if self._current_loader == "vanilla":
            return

        mc_version = self.combo_version.currentText().strip()
        if not mc_version or mc_version not in self._valid_versions:
            self.combo_loader_version.lineEdit().setPlaceholderText(
                "请先选择有效的 Minecraft 版本"
            )
            return

        # 同样的 (加载器, MC 版本) 已加载过则不重复请求
        key = (self._current_loader, mc_version)
        if key == self._loaded_loader_key and self.combo_loader_version.count() > 0:
            return

        self.on_refresh_loader_versions(silent=True)

    def on_refresh_loader_versions(self, silent: bool = False):
        mc_version = self.combo_version.currentText().strip()

        if not mc_version:
            if not silent:
                QMessageBox.warning(self, "提示", "请先选择或输入 Minecraft 版本号")
            return

        if mc_version not in self._valid_versions:
            if not silent:
                QMessageBox.warning(
                    self, "版本无效",
                    f"版本 “{mc_version}” 不存在或无效。\n请从下拉列表中选择，或刷新版本列表。"
                )
            return

        # 同一版本已有请求在进行中：标记待刷新
        if self._loader_fetcher is not None and self._loader_fetcher.isRunning():
            self._pending_auto_fetch = True
            return

        loader_name, loader_mc = self._current_loader, mc_version
        self.btn_refresh_loader.setEnabled(False)
        self.combo_loader_version.lineEdit().setPlaceholderText("正在获取加载器版本...")

        self._loader_fetcher = ModLoaderVersionFetcher(
            loader_name, loader_mc,
            get_bool(self.config, "use_mirror", True), self,
        )

        def on_done(versions, loader=loader_name, mc=loader_mc):
            self._loaded_loader_key = (loader, mc)
            self._on_loader_versions_fetched(versions)

        def on_fail(err, loader=loader_name, mc=loader_mc):
            self._loaded_loader_key = None
            self._on_loader_versions_failed(err)

        self._loader_fetcher.finished.connect(on_done)
        self._loader_fetcher.failed.connect(on_fail)
        self._loader_fetcher.start()

    def _on_loader_versions_fetched(self, versions: list):
        self.btn_refresh_loader.setEnabled(True)
        self.combo_loader_version.lineEdit().setPlaceholderText("选择加载器版本")

        current = self.combo_loader_version.currentText().strip()
        current = current.split("（")[0].strip() if current else ""

        self.combo_loader_version.blockSignals(True)
        self.combo_loader_version.clear()
        for v in versions:
            display = v["version"]
            if v.get("branch") and v["branch"] not in ("release", "stable"):
                display = f"{v['version']}（{v['branch']}）"
            self.combo_loader_version.addItem(display, v["version"])

        # 恢复上次选择；没有就默认第一个（通常是最新版本）
        idx = self.combo_loader_version.findData(current) if current else -1
        if idx >= 0:
            self.combo_loader_version.setCurrentIndex(idx)
        self.combo_loader_version.blockSignals(False)

        name = self.combo_loader.currentText()
        if not versions:
            self.append_log(f"[WARN] {name} 没有适用于 {self.combo_version.currentText().strip()} 的版本")
        else:
            self.append_log(f"{name} 版本列表已更新，共 {len(versions)} 个版本")

        if self._pending_auto_fetch:
            self._pending_auto_fetch = False
            QTimer.singleShot(0, self._maybe_fetch_loader_versions)

    def _on_loader_versions_failed(self, err: str):
        self.btn_refresh_loader.setEnabled(True)
        self.combo_loader_version.lineEdit().setPlaceholderText("获取失败，点击刷新重试")
        self.append_log(f"[WARN] 获取 {self.combo_loader.currentText()} 版本列表失败：{err}")

        if self._pending_auto_fetch:
            self._pending_auto_fetch = False
            QTimer.singleShot(0, self._maybe_fetch_loader_versions)

    def on_browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择 .minecraft 目录")
        if d:
            self.edit_dir.setText(d)

    # ================================================================== 开始下载

    def on_start(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "任务正在进行中")
            return

        version = self.combo_version.currentText().strip()
        if not version:
            QMessageBox.warning(self, "提示", "请输入或选择 Minecraft 版本号")
            return
        if version not in self._valid_versions:
            QMessageBox.warning(
                self, "版本无效",
                f"版本 “{version}” 不存在或无效。\n请从下拉列表中选择，或刷新版本列表。"
            )
            return

        loader_id = self._current_loader
        loader_version = None
        if loader_id != "vanilla":
            loader_version = self.combo_loader_version.currentData()
            if not loader_version:
                text = self.combo_loader_version.currentText().strip()
                loader_version = text.split(" ")[0].replace("（", " ").split(" ")[0] if text else None
            if not loader_version:
                QMessageBox.warning(
                    self, "提示",
                    f"请选择 {self.combo_loader.currentText()} 版本，或点击「刷新」。"
                )
                return

        mc_dir = self.edit_dir.text().strip()
        if not mc_dir:
            QMessageBox.warning(self, "提示", "请先选择 .minecraft 下载目录")
            return

        from pathlib import Path
        mc_path = Path(mc_dir)
        if not mc_path.is_absolute():
            QMessageBox.warning(self, "提示", "请使用绝对路径选择 .minecraft 目录")
            return

        if not mc_path.exists():
            reply = QMessageBox.question(
                self, "目录不存在", f"目录 {mc_dir} 不存在，是否尝试创建？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                mc_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "创建失败", f"无法创建目录：{e}")
                return

        self.text_log.clear()
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.label_stage.setText("准备中…")
        self._set_running(True)

        self._worker = UnifiedDownloadWorker(
            version_id=version,
            mc_dir=mc_path,
            loader_name=loader_id if loader_id != "vanilla" else None,
            loader_version=loader_version,
            threads=get_int(self.config, "threads", 32),
            use_mirror=get_bool(self.config, "use_mirror", True),
            run_java_installer=get_bool(self.config, "run_java_installer", True),
            java_path=get_str(self.config, "java_path"),
            parent=self,
        )
        self._worker.log.connect(self.append_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.stage.connect(self.on_stage)
        self._worker.finished_ok.connect(self.on_finished)
        self._worker.failed.connect(self.on_failed)
        self._worker.cancelled_sig.connect(self.on_cancelled)
        self._worker.start()

    def on_cancel(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.append_log("[WARN] 正在取消…")
            self.btn_cancel.setEnabled(False)

    def _set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.btn_refresh.setEnabled(not running)
        self.btn_refresh_loader.setEnabled(not running and self._current_loader != "vanilla")
        self.combo_loader.setEnabled(not running)
        self.combo_version.setEnabled(not running)
        self.combo_loader_version.setEnabled(not running and self._current_loader != "vanilla")

    # ================================================================== 日志与进度

    def append_log(self, msg: str):
        self.text_log.append(msg)

    def on_stage(self, name: str):
        self.label_stage.setText(f"当前阶段：{name}")

    def _update_bar(self, done: int, total: int):
        """按字节刷新进度条，并显示百分比与大小。"""
        if total <= 0:
            return
        ratio = max(0.0, min(1.0, done / total))
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(int(ratio * 1000))
        self.progress_bar.setFormat(
            f"{ratio * 100:.1f}%  ({_human_size(done)} / {_human_size(total)})"
        )

    def on_progress(self, done: int, total: int):
        """当前阶段进度（单文件下载期间也会持续刷新）。"""
        self._update_bar(done, total)

    def on_finished(self):
        self._set_running(False)
        self.label_stage.setText("完成")
        self.progress_bar.setValue(self.progress_bar.maximum())
        QMessageBox.information(self, "完成", "下载 / 安装完成！")

    def on_failed(self, err: str):
        self._set_running(False)
        self.label_stage.setText("失败")
        QMessageBox.critical(self, "任务失败", err)

    def on_cancelled(self):
        self._set_running(False)
        self.label_stage.setText("已取消")
        self.append_log("[WARN] 任务已取消")

    # ================================================================== 设置

    def on_settings(self):
        win = SettingsWindow(self.config, self)
        win.setWindowModality(Qt.WindowModality.ApplicationModal)
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        win.config_saved.connect(self._on_config_saved)
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_config_saved(self, config):
        self._apply_config(config)
        if self._current_loader != "vanilla":
            self._maybe_fetch_loader_versions()
        self.on_refresh_versions()

    # ================================================================== 退出

    def closeEvent(self, event):
        for fetcher in (self._fetcher, self._loader_fetcher):
            if fetcher is not None and fetcher.isRunning():
                fetcher.terminate()
                fetcher.wait()
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("auto")

    win = MainWindow()
    win.show()

    if win._first_run:
        QMessageBox.information(win, "欢迎使用", WELCOME_MSG)
        win.on_settings()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
