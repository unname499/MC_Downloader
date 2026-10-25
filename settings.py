# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings.ui'
##
## Created by: Qt User Interface Compiler version 6.12.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton,
    QRadioButton, QSizePolicy, QSlider, QSpinBox,
    QTabWidget, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(439, 550)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.cancel = QPushButton(self.centralwidget)
        self.cancel.setObjectName(u"cancel")

        self.gridLayout.addWidget(self.cancel, 1, 2, 1, 1)

        self.ok = QPushButton(self.centralwidget)
        self.ok.setObjectName(u"ok")

        self.gridLayout.addWidget(self.ok, 1, 1, 1, 1)

        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")
        self.tab = QWidget()
        self.tab.setObjectName(u"tab")
        self.formLayout = QFormLayout(self.tab)
        self.formLayout.setObjectName(u"formLayout")
        self.label = QLabel(self.tab)
        self.label.setObjectName(u"label")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label)

        self.lineEdit_minecraft_dir = QLineEdit(self.tab)
        self.lineEdit_minecraft_dir.setObjectName(u"lineEdit_minecraft_dir")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEdit_minecraft_dir)

        self.find = QPushButton(self.tab)
        self.find.setObjectName(u"find")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.find)

        self.label_2 = QLabel(self.tab)
        self.label_2.setObjectName(u"label_2")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_2)

        self.yes = QRadioButton(self.tab)
        self.yes.setObjectName(u"yes")
        self.yes.setChecked(True)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.yes)

        self.no = QRadioButton(self.tab)
        self.no.setObjectName(u"no")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.no)

        self.off_settings_notice = QCheckBox(self.tab)
        self.off_settings_notice.setObjectName(u"off_settings_notice")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.off_settings_notice)

        self.label_3 = QLabel(self.tab)
        self.label_3.setObjectName(u"label_3")
        self.label_3.setTextFormat(Qt.TextFormat.MarkdownText)
        self.label_3.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.label_3.setOpenExternalLinks(True)

        self.formLayout.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.label_3)

        self.tabWidget.addTab(self.tab, "")
        self.tab_2 = QWidget()
        self.tab_2.setObjectName(u"tab_2")
        self.gridLayout_3 = QGridLayout(self.tab_2)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.threads_slider = QSlider(self.tab_2)
        self.threads_slider.setObjectName(u"threads_slider")
        self.threads_slider.setMinimum(1)
        self.threads_slider.setMaximum(128)
        self.threads_slider.setValue(32)
        self.threads_slider.setOrientation(Qt.Orientation.Horizontal)

        self.gridLayout_3.addWidget(self.threads_slider, 0, 1, 1, 1)

        self.label_4 = QLabel(self.tab_2)
        self.label_4.setObjectName(u"label_4")

        self.gridLayout_3.addWidget(self.label_4, 0, 0, 1, 1)

        self.threads_spinBox = QSpinBox(self.tab_2)
        self.threads_spinBox.setObjectName(u"threads_spinBox")
        self.threads_spinBox.setMinimum(1)
        self.threads_spinBox.setMaximum(128)
        self.threads_spinBox.setValue(32)

        self.gridLayout_3.addWidget(self.threads_spinBox, 0, 2, 1, 1)

        self.label_5 = QLabel(self.tab_2)
        self.label_5.setObjectName(u"label_5")
        font = QFont()
        font.setPointSize(11)
        self.label_5.setFont(font)
        self.label_5.setStyleSheet(u"color: grey")
        self.label_5.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.gridLayout_3.addWidget(self.label_5, 1, 0, 1, 2)

        self.tabWidget.addTab(self.tab_2, "")

        self.gridLayout.addWidget(self.tabWidget, 0, 0, 1, 3)

        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)

        self.tabWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"\u8bbe\u7f6e", None))
        self.cancel.setText(QCoreApplication.translate("MainWindow", u"\u53d6\u6d88", None))
        self.ok.setText(QCoreApplication.translate("MainWindow", u"\u786e\u5b9a", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u".minecraft\u6587\u4ef6\u5939\u8def\u5f84\uff1a", None))
        self.find.setText(QCoreApplication.translate("MainWindow", u"\u6d4f\u89c8", None))
        self.label_2.setText(QCoreApplication.translate("MainWindow", u"\u662f\u5426\u4f7f\u7528\u955c\u50cf\u6e90\uff1a", None))
        self.yes.setText(QCoreApplication.translate("MainWindow", u"\u662f", None))
        self.no.setText(QCoreApplication.translate("MainWindow", u"\u5426", None))
        self.off_settings_notice.setText(QCoreApplication.translate("MainWindow", u"\u5173\u95ed\u8bbe\u7f6e\u63d0\u793a", None))
        self.label_3.setText(QCoreApplication.translate("MainWindow", u"\u955c\u50cf\u6e90\u7531 BMCLAPI \u63d0\u4f9b\uff0c[\u70b9\u6b64\u8bbf\u95ee\u6b64 API \u6587\u6863](https://bmclapidoc.bangbang93.com/)", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), QCoreApplication.translate("MainWindow", u"\u57fa\u672c\u8bbe\u7f6e", None))
        self.label_4.setText(QCoreApplication.translate("MainWindow", u"\u4e0b\u8f7d\u7ebf\u7a0b\u6570\uff1a", None))
        self.label_5.setText(QCoreApplication.translate("MainWindow", u"\u5176\u4ed6\u6682\u65f6\u6ca1\u505a", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), QCoreApplication.translate("MainWindow", u"\u4e0b\u8f7d\u8bbe\u7f6e", None))
    # retranslateUi

