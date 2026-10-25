# settings_code.py
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QWidget, QLabel, QVBoxLayout, QFileDialog
from PySide6.QtCore import Qt, Signal

from settings import Ui_MainWindow
from config import (
    CONFIG_SECTION, read_conf, write_conf,
    get_bool, get_int, get_str,
)

NOTES_TEXT = """设置注意事项：

1. 必须填写你的 .minecraft 文件夹路径，这是下载 Minecraft 的关键。
   例如：C:/Users/Administrator/.minecraft

2. 镜像源视网络环境选择：
   - 中国大陆用户推荐使用镜像源；
   - 中国香港、中国澳门、中国台湾及海外用户优先使用官方源。

3. 若使用镜像源仍然几乎无法下载，可以尝试：
   - 切换回官方源；
   - 官方源 + VPN。

4. 线程数不要设置过大，建议 16~32，过大可能影响下载稳定性。
"""


class NotesWindow(QWidget):
    ...  # 不变，略


class SettingsWindow(QMainWindow, Ui_MainWindow):
    config_saved = Signal(object)   # ConfigParser 不是 Qt 内置类型，用 object 更稳

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("设置")

        self.config = config
        self._notes_window = None
        self._notes_shown = False

        self._load_from_config()

        self.threads_slider.valueChanged.connect(self.on_slider_changed)
        self.threads_spinBox.valueChanged.connect(self.on_spinbox_changed)
        self.find.clicked.connect(self.on_find_btn_clicked)
        self.ok.clicked.connect(self.on_ok)
        self.cancel.clicked.connect(self.on_cancel)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._notes_shown:
            self._notes_shown = True
            if not get_bool(self.config, "off_settings_notice", False):
                self._show_notes()

    # ---------- 回填 ----------
    def _load_from_config(self):
        threads = get_int(self.config, "threads", 32)
        self.threads_slider.setValue(threads)
        self.threads_spinBox.setValue(threads)

        self.lineEdit_minecraft_dir.setText(get_str(self.config, "minecraft_dir"))

        if get_bool(self.config, "use_mirror", True):
            self.yes.setChecked(True)
        else:
            self.no.setChecked(True)

        self.off_settings_notice.setChecked(
            get_bool(self.config, "off_settings_notice", False)
        )

    # ---------- 双向同步 ----------
    def on_slider_changed(self, value: int):
        if self.threads_spinBox.value() != value:
            self.threads_spinBox.setValue(value)

    def on_spinbox_changed(self, value: int):
        if self.threads_slider.value() != value:
            self.threads_slider.setValue(value)

    def on_find_btn_clicked(self):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            self.lineEdit_minecraft_dir.setText(d)

    # ---------- 确定 ----------
    def on_ok(self):
        self.config.set(CONFIG_SECTION, "minecraft_dir",
                        self.lineEdit_minecraft_dir.text().strip())
        self.config.set(CONFIG_SECTION, "use_mirror",
                        "true" if self.yes.isChecked() else "false")
        self.config.set(CONFIG_SECTION, "threads",
                        str(self.threads_spinBox.value()))
        self.config.set(CONFIG_SECTION, "off_settings_notice",
                        "true" if self.off_settings_notice.isChecked() else "false")

        write_conf(self.config)          # ★ 统一写文件入口
        self.config_saved.emit(self.config)
        self.close()

    def on_cancel(self):
        self.close()

    # ---------- 注意事项 ----------
    def _show_notes(self):
        if self._notes_window is not None:
            return
        self._notes_window = NotesWindow(self)
        self._notes_window.show()
        self._reposition_notes()

    def _reposition_notes(self):
        if self._notes_window is None:
            return
        screen = self.screen().availableGeometry()
        gap = 16
        w = self._notes_window.width()
        h = self._notes_window.height()
        x = self.x() + self.width() + gap
        y = self.y()
        if x + w > screen.right():
            x = self.x() - w - gap
            if x < screen.left():
                x = self.x()
                y = self.y() + self.height() + gap
                if y + h > screen.bottom():
                    y = self.y() - h - gap
        self._notes_window.move(x, y)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposition_notes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_notes()

    def closeEvent(self, event):
        if self._notes_window is not None:
            self._notes_window.close()
            self._notes_window = None
        super().closeEvent(event)