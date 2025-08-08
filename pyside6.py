import sys
import os
import json
import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLineEdit, QPushButton,
    QScrollArea, QLabel, QGridLayout, QVBoxLayout, QFileDialog,
    QMessageBox, QProgressBar
)
from PySide6.QtGui import QPixmap, QAction
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from qt_material import apply_stylesheet

class SearchWorker(QThread):
    thumbnail_ready = Signal(QPixmap, str)
    finished = Signal(int)

    def __init__(self, keyword, count):
        super().__init__()
        self.keyword = keyword
        self.count = count

    def run(self):
        urls = []
        for _ in range(self.count):
            response = requests.get(
                f"https://source.unsplash.com/featured/?{self.keyword}",
                allow_redirects=False
            )
            url = response.headers.get("Location")
            if url and url not in urls:
                urls.append(url)
        loaded = 0
        for url in urls:
            img_data = requests.get(url).content
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            thumbnail = pixmap.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_ready.emit(thumbnail, url)
            loaded += 1
        self.finished.emit(loaded)

class DownloadWorker(QThread):
    progress = Signal(int)
    completed = Signal(str)

    def __init__(self, url, save_dir):
        super().__init__()
        self.url = url
        self.save_dir = save_dir

    def run(self):
        local_name = os.path.join(self.save_dir, os.path.basename(self.url))
        response = requests.get(self.url, stream=True)
        total = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(local_name, 'wb') as f:
            for chunk in response.iter_content(1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int(downloaded / total * 100)
                    self.progress.emit(percent)
        self.completed.emit(local_name)

class WallpaperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Unsplash 壁纸浏览器')
        self.resize(900, 600)
        self.settings = QSettings('config.ini', QSettings.IniFormat)
        apply_stylesheet(app, theme='dark_teal.xml')
        self.load_settings()
        self.init_ui()

    def init_ui(self):
        container = QWidget()
        layout = QVBoxLayout()
        input_layout = QWidget()
        input_layout.setLayout(QGridLayout())
        self.search_input = QLineEdit(self.last_keyword)
        self.search_button = QPushButton('搜索')
        self.search_button.clicked.connect(self.start_search)
        input_layout.layout().addWidget(self.search_input, 0, 0)
        input_layout.layout().addWidget(self.search_button, 0, 1)
        layout.addWidget(input_layout)
        self.scroll_area = QScrollArea()
        self.thumb_container = QWidget()
        self.thumb_layout = QGridLayout()
        self.thumb_container.setLayout(self.thumb_layout)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.thumb_container)
        layout.addWidget(self.scroll_area)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.progress_bar = QProgressBar()
        self.statusBar().addPermanentWidget(self.progress_bar)
        settings_action = QAction('设置', self)
        settings_action.triggered.connect(self.choose_directory)
        self.menuBar().addAction(settings_action)

    def load_settings(self):
        self.last_keyword = self.settings.value('ini-gui/keyword', '')
        self.save_dir = self.settings.value('ini-gui/save_dir', os.getcwd())

    def save_settings(self):
        self.settings.setValue('ini-gui/keyword', self.search_input.text())
        self.settings.setValue('ini-gui/save_dir', self.save_dir)

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '选择保存路径', self.save_dir)
        if directory:
            self.save_dir = directory

    def start_search(self):
        for i in reversed(range(self.thumb_layout.count())):
            widget = self.thumb_layout.itemAt(i).widget()
            widget.setParent(None)
        keyword = self.search_input.text()
        self.search_thread = SearchWorker(keyword, 15)
        self.search_thread.thumbnail_ready.connect(self.add_thumbnail)
        self.search_thread.finished.connect(lambda n: self.statusBar().showMessage(f'共加载 {n} 张缩略图'))
        self.search_thread.start()

    def add_thumbnail(self, pixmap, url):
        row = self.thumb_layout.rowCount()
        col = self.thumb_layout.columnCount() % 5
        label = QLabel()
        label.setPixmap(pixmap)
        label.mousePressEvent = lambda e, u=url: self.download_original(u)
        self.thumb_layout.addWidget(label, row, col)

    def download_original(self, url):
        self.progress_bar.setValue(0)
        self.download_thread = DownloadWorker(url, self.save_dir)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.completed.connect(self.show_download_complete)
        self.download_thread.start()

    def show_download_complete(self, path):
        msg = QMessageBox(self)
        msg.setText('下载完成')
        msg.show()
        #QTimer.singleShot(3000, msg.accept)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = WallpaperApp()
    window.show()
    sys.exit(app.exec())
