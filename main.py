# main.py
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QLineEdit, QTextEdit,
    QProgressBar, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
import qdarktheme

from config import (
    CONFIG_SECTION, read_conf, write_default_conf, is_first_run,
    get_bool, get_int, get_str,
)
from settings_code import SettingsWindow
from downloader import DownloadWorker, fetch_version_list

WELCOME_MSG = "欢迎回来！由于您是第一次使用该软件，稍后会弹出设置窗口，请您自行配置。"


def _is_dark_system() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC Downloader")
        self.resize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 版本行
        row_v = QHBoxLayout()
        row_v.addWidget(QLabel("版本："))
        self.combo_version = QComboBox()
        self.combo_version.setEditable(True)
        self.combo_version.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_version.lineEdit().setPlaceholderText("选择或输入版本号")
        row_v.addWidget(self.combo_version, 1)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.on_refresh_versions)
        row_v.addWidget(self.btn_refresh)
        root.addLayout(row_v)

        # 目录行
        row_d = QHBoxLayout()
        row_d.addWidget(QLabel("下载目录："))
        self.edit_dir = QLineEdit()
        row_d.addWidget(self.edit_dir, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self.on_browse)
        row_d.addWidget(btn_browse)
        root.addLayout(row_d)

        self.label_stage = QLabel("就绪")
        root.addWidget(self.label_stage)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        root.addWidget(self.text_log, 1)

        row_b = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.clicked.connect(self.on_start)
        row_b.addWidget(self.btn_start)

        self.btn_settings = QPushButton("打开设置")
        self.btn_settings.clicked.connect(self.on_settings)
        row_b.addWidget(self.btn_settings)

        row_b.addStretch()

        btn_exit = QPushButton("退出")
        btn_exit.clicked.connect(self.close)
        row_b.addWidget(btn_exit)
        root.addLayout(row_b)

        # 配置（唯一入口）
        self._first_run = is_first_run()
        self.config = write_default_conf() if self._first_run else read_conf()
        self.edit_dir.setText(get_str(self.config, "minecraft_dir"))

        self._worker = None
        self._valid_versions = set()

        QTimer.singleShot(0, self.on_refresh_versions)

    # ---------- 版本列表 ----------
    def on_refresh_versions(self):
        use_mirror = get_bool(self.config, "use_mirror", True)
        try:
            versions = fetch_version_list(use_mirror)
        except Exception as e:
            self.append_log(f"[WARN] 获取版本列表失败：{e}")
            return

        self._valid_versions = {v["id"] for v in versions}

        current = self.combo_version.currentText()
        self.combo_version.clear()
        for v in versions:
            self.combo_version.addItem(v["id"])

        idx = self.combo_version.findText(current)
        if idx >= 0:
            self.combo_version.setCurrentIndex(idx)
        elif current:
            self.combo_version.setEditText(current)
        self.append_log(f"版本列表已更新，共 {len(versions)} 个版本")

    def on_browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择 .minecraft 目录")
        if d:
            self.edit_dir.setText(d)

    # ---------- 开始下载 ----------
    def on_start(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "下载正在进行中")
            return

        version = self.combo_version.currentText().strip()
        if not version:
            QMessageBox.warning(self, "提示", "请输入或选择版本号")
            return
        if version not in self._valid_versions:
            QMessageBox.warning(
                self, "版本无效",
                f"版本 “{version}” 不存在或无效。\n"
                "请从下拉列表中选择，或点“刷新”后重新输入。"
            )
            return

        mc_dir = self.edit_dir.text().strip()
        if not mc_dir:
            QMessageBox.warning(self, "提示", "请先选择 .minecraft 下载目录")
            return
        mc_path = Path(mc_dir)
        if not mc_path.exists():
            QMessageBox.warning(self, "提示", f"目录不存在：{mc_dir}")
            return

        threads = get_int(self.config, "threads", 32)
        use_mirror = get_bool(self.config, "use_mirror", True)

        self.text_log.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1000)
        self.label_stage.setText("准备中…")
        self.btn_start.setEnabled(False)

        self._worker = DownloadWorker(version, mc_path, threads, use_mirror, self)
        self._worker.log.connect(self.append_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.stage.connect(self.on_stage)
        self._worker.finished_ok.connect(self.on_finished)
        self._worker.failed.connect(self.on_failed)
        self._worker.start()

    def append_log(self, msg: str):
        self.text_log.append(msg)

    def on_stage(self, name: str):
        self.label_stage.setText(f"当前阶段：{name}")

    def on_progress(self, done: int, total: int):
        if total <= 0:
            return
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(int(done * 1000 / total))

    def on_finished(self):
        self.btn_start.setEnabled(True)
        self.label_stage.setText("完成")
        self.progress_bar.setValue(self.progress_bar.maximum())
        QMessageBox.information(self, "完成", "Minecraft 下载完成！")

    def on_failed(self, err: str):
        self.btn_start.setEnabled(True)
        self.label_stage.setText("失败")
        QMessageBox.critical(self, "下载失败", err)

    # ---------- 设置 ----------
    def on_settings(self):
        win = SettingsWindow(self.config, self)
        win.setWindowModality(Qt.WindowModality.ApplicationModal)
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        win.config_saved.connect(self._on_config_saved)
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_config_saved(self, config):
        self.config = config
        self.edit_dir.setText(get_str(config, "minecraft_dir"))
        # ★ 设置里改了镜像源，版本列表也要按新源重拉
        self.on_refresh_versions()

    def closeEvent(self, event):
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