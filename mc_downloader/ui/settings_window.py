# mc_downloader/ui/settings_window.py
"""
Settings window with mod loader options.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGridLayout, QTabWidget, QFileDialog, QComboBox, QLineEdit, QPushButton,
    QRadioButton, QCheckBox, QSlider, QSpinBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal

from mc_downloader.config import (
    CONFIG_SECTION, write_conf,
    get_bool, get_int, get_str,
)
from mc_downloader.downloader.mod_loaders import list_loaders, MOD_LOADERS

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

5. 模组加载器：主界面选择加载器并下载 MC 版本后，会自动拉取可用版本。

6. 安装模组加载器前建议先下载对应的原版游戏文件。
"""


class NotesWindow(QWidget):
    """设置注意事项子窗口：显示在设置窗口旁边，不遮挡"""

    def __init__(self, parent_settings_window: QWidget):
        super().__init__(
            parent_settings_window,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
        )
        self.setWindowTitle("设置注意事项")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.label = QLabel(NOTES_TEXT)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)

        hint = QLabel("—— 此说明仅此一次 ——")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

        self.setFixedWidth(max(self.sizeHint().width(), 300))
        self.adjustSize()


class SettingsWindow(QMainWindow):
    config_saved = Signal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(500, 600)

        self.config = config
        self._notes_window = None
        self._notes_shown = False

        self._setup_ui()
        self._load_from_config()

    # ------------------------------------------------------------------ UI

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self._build_basic_tab(), "基本设置")
        self.tab_widget.addTab(self._build_download_tab(), "下载设置")
        self.tab_widget.addTab(self._build_loader_tab(), "模组加载器")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.on_ok)
        self.button_box.rejected.connect(self.on_cancel)
        layout.addWidget(self.button_box)

    def _build_basic_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.lineEdit_minecraft_dir = QLineEdit()
        self.btn_find = QPushButton("浏览")
        self.btn_find.clicked.connect(self.on_find_btn_clicked)
        form.addRow(QLabel(".minecraft文件夹路径："), self.lineEdit_minecraft_dir)
        form.addRow("", self.btn_find)

        self.yes = QRadioButton("是")
        self.no = QRadioButton("否")
        self.yes.setChecked(True)
        mirror_row = QHBoxLayout()
        mirror_row.addWidget(self.yes)
        mirror_row.addWidget(self.no)
        mirror_row.addStretch()
        form.addRow(QLabel("是否使用镜像源："), mirror_row)

        self.combo_loader = QComboBox()
        self.combo_loader.addItem("原版", "vanilla")
        for loader_id in list_loaders():
            display_name = MOD_LOADERS[loader_id].loader_display_name
            self.combo_loader.addItem(display_name, loader_id)
        form.addRow(QLabel("默认模组加载器："), self.combo_loader)

        self.off_settings_notice = QCheckBox("关闭设置提示")
        form.addRow("", self.off_settings_notice)

        self.label_info = QLabel(
            "镜像源由 BMCLAPI 提供，[点此访问此 API 文档](https://bmclapidoc.bangbang93.com/)"
        )
        self.label_info.setTextFormat(Qt.TextFormat.MarkdownText)
        self.label_info.setAlignment(
            Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.label_info.setOpenExternalLinks(True)
        form.addRow("", self.label_info)

        return tab

    def _build_download_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)

        grid.addWidget(QLabel("下载线程数："), 0, 0)

        self.threads_slider = QSlider(Qt.Orientation.Horizontal)
        self.threads_slider.setMinimum(1)
        self.threads_slider.setMaximum(128)
        self.threads_slider.setValue(32)
        grid.addWidget(self.threads_slider, 0, 1)

        self.threads_spinBox = QSpinBox()
        self.threads_spinBox.setMinimum(1)
        self.threads_spinBox.setMaximum(128)
        self.threads_spinBox.setValue(32)
        grid.addWidget(self.threads_spinBox, 0, 2)

        self.threads_slider.valueChanged.connect(self.on_slider_changed)
        self.threads_spinBox.valueChanged.connect(self.on_spinbox_changed)

        note = QLabel("镜像源模式下线程数会自动限制为 16 个。")
        note.setStyleSheet("color: grey;")
        note.setWordWrap(True)
        grid.addWidget(note, 1, 0, 1, 3)

        return tab

    def _build_loader_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        info = QLabel(
            "· Fabric / Quilt：从官方元数据获取版本 JSON，并下载 loader 依赖。\n"
            "· Forge / NeoForge：下载安装器 JAR 并解析版本清单，无需 Java。\n"
            "· 安装加载器前请先下载对应的原版游戏文件。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        form.addRow(info)

        # 运行 Java 安装器补全
        self.chk_run_java = QCheckBox("运行安装器补全（Forge / NeoForge）")
        self.chk_run_java.setToolTip(
            "勾选后会用 Java 执行安装器，生成 srg / extra / client 等补丁文件；\n"
            "缺少这些文件时游戏会启动崩溃。"
        )
        self.chk_run_java.toggled.connect(self._on_run_java_toggled)
        form.addRow(self.chk_run_java)

        java_row = QWidget()
        java_row_layout = QHBoxLayout(java_row)
        java_row_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_java_path = QLineEdit()
        self.edit_java_path.setPlaceholderText("留空则自动探测（JAVA_HOME / PATH / 常见目录）")
        self.btn_find_java = QPushButton("浏览")
        self.btn_find_java.clicked.connect(self.on_find_java_clicked)
        java_row_layout.addWidget(self.edit_java_path, 1)
        java_row_layout.addWidget(self.btn_find_java)
        form.addRow("Java 路径：", java_row)

        self.label_java_status = QLabel("")
        self.label_java_status.setWordWrap(True)
        self.label_java_status.setStyleSheet("color: grey;")
        form.addRow("", self.label_java_status)

        return tab

    def _on_run_java_toggled(self, checked: bool):
        self.edit_java_path.setEnabled(checked)
        self.btn_find_java.setEnabled(checked)
        self._refresh_java_status()

    def on_find_java_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 java 可执行文件", "", "Java 可执行文件 (java.exe java javaw.exe);;所有文件 (*)"
        )
        if path:
            self.edit_java_path.setText(path)
            self._refresh_java_status()

    def _refresh_java_status(self):
        from mc_downloader.core.java_env import find_java, java_version

        java = find_java(self.edit_java_path.text().strip())
        if java is None:
            self.label_java_status.setText("未检测到 Java，启用补全功能前请先安装 JDK 17/21。")
            self.label_java_status.setStyleSheet("color: #c0392b;")
            return

        version = java_version(java) or "版本未知"
        self.label_java_status.setText(f"已检测到：{java}\n{version}")
        self.label_java_status.setStyleSheet("color: #27ae60;")

    # ------------------------------------------------------------------ 配置

    def showEvent(self, event):
        super().showEvent(event)
        if not self._notes_shown:
            self._notes_shown = True
            if not get_bool(self.config, "off_settings_notice", False):
                self._show_notes()

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

        idx = self.combo_loader.findData(get_str(self.config, "default_loader", "vanilla"))
        if idx >= 0:
            self.combo_loader.setCurrentIndex(idx)

        # Java 安装器补全
        self.chk_run_java.setChecked(get_bool(self.config, "run_java_installer", True))
        self.edit_java_path.setText(get_str(self.config, "java_path"))
        self.edit_java_path.setEnabled(self.chk_run_java.isChecked())
        self.btn_find_java.setEnabled(self.chk_run_java.isChecked())
        self._refresh_java_status()

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

    def on_ok(self):
        section = CONFIG_SECTION
        self.config.set(section, "minecraft_dir", self.lineEdit_minecraft_dir.text().strip())
        self.config.set(section, "use_mirror", "true" if self.yes.isChecked() else "false")
        self.config.set(section, "threads", str(self.threads_spinBox.value()))
        self.config.set(section, "off_settings_notice",
                        "true" if self.off_settings_notice.isChecked() else "false")
        self.config.set(section, "default_loader", self.combo_loader.currentData())
        self.config.set(section, "run_java_installer",
                        "true" if self.chk_run_java.isChecked() else "false")
        self.config.set(section, "java_path", self.edit_java_path.text().strip())

        write_conf(self.config)
        self.config_saved.emit(self.config)
        self.close()

    def on_cancel(self):
        self.close()

    # ------------------------------------------------------------------ 注意事项

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
        w, h = self._notes_window.width(), self._notes_window.height()
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
