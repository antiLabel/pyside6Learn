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
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QTimer
from qt_material import apply_stylesheet
from urllib.parse import urlparse
import uuid

class ClickableLabel(QLabel):
    rightButtonClicked = Signal(str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightButtonClicked.emit(self.url)

def get_config_path():
    return os.path.join(get_cofig_dir(), 'config.ini')

def get_cofig_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(__file__)
    
class SearchWorker(QThread):
    thumbnail_ready = Signal(QPixmap, str)
    finished = Signal(int)

    def __init__(self, keyword, count):
        super().__init__()
        self.keyword = keyword
        self.count = count

    def run(self):
        # --- 这是新的 run 方法 ---
        if not self.keyword:
            self.finished.emit(0)
            return

        # 替换成您的Unsplash Access Key
        access_key = "T3qu5zPCUo-8Wq4gfiJY_PSwwTVAg6WAvMrI8iZwX4Q"
        
        # 官方API的地址和参数
        api_url = "https://api.unsplash.com/photos/random"
        params = {
            'client_id': access_key,
            'query': self.keyword,
            'count': self.count, # 一次性请求多张图片
            'orientation': 'landscape',
        }
        
        try:
            # 发送请求，这次不再需要禁止重定向了
            response = requests.get(api_url, params=params, timeout=15)
            response.raise_for_status() # 检查错误
            
            # 官方API直接返回一个包含图片信息的JSON列表
            data = response.json()

            loaded = 0
            for photo_data in data:
                # 从JSON数据中提取图片的URL
                # Unsplash提供了多种尺寸，'small'作为缩略图很合适
                thumb_url = photo_data['urls']['small']
                original_url = photo_data['urls']['raw'] # 高清原图URL

                # 下载缩略图数据
                img_data_response = requests.get(thumb_url)
                img_data_response.raise_for_status()
                
                pixmap = QPixmap()
                pixmap.loadFromData(img_data_response.content)                
                if not pixmap.isNull():
                    # 发射信号，这次我们把高清图的URL也一起传回去
                    scaled_pixmap = pixmap.scaled(480, 270, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.thumbnail_ready.emit(scaled_pixmap, original_url)
                    loaded += 1
            
            self.finished.emit(loaded)

        except Exception as e:
            print(f"API请求或下载失败: {e}")
            self.finished.emit(0) # 告诉主线程加载了0张图片

class DownloadWorker(QThread):
    progress = Signal(int)
    completed = Signal(str)

    def __init__(self, url, save_dir):
        super().__init__()
        self.url = url
        self.save_dir = save_dir

    def run(self):
        parsed_url = urlparse(self.url)
        filename = f"{os.path.basename(parsed_url.path)}.jpg" or f"{uuid.uuid4()}.jpg"
        local_name = os.path.join(self.save_dir, filename)
        response = requests.get(self.url, stream=True)
        total = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(local_name, 'wb') as f:
            for chunk in response.iter_content(1024):
                if chunk:
                    f.write(chunk)
                    if total > 0:
                        downloaded += len(chunk)
                        percent = int(downloaded / total * 100)
                        self.progress.emit(percent)
        self.completed.emit(local_name)

class WallpaperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Unsplash 壁纸浏览器')
        self.resize(900, 600)
        self.settings = QSettings(get_config_path(), QSettings.IniFormat)
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
        self.progress_bar.setVisible(False)
        container.layout().addWidget(self.progress_bar)


        settings_action = QAction('设置', self)
        settings_action.triggered.connect(self.choose_directory)
        self.menuBar().addAction(settings_action)

    def load_settings(self):
        self.last_keyword = self.settings.value('ini-gui/keyword', '')
        self.save_dir = self.settings.value('ini-gui/save_dir', get_cofig_dir())

    def save_settings(self):
        self.settings.setValue('ini-gui/keyword', self.search_input.text())
        self.settings.setValue('ini-gui/save_dir', self.save_dir)

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '选择保存路径', self.save_dir)
        if directory:
            self.save_dir = directory

    def start_search(self):
        self.search_button.setEnabled(False)
        for i in reversed(range(self.thumb_layout.count())):
            widget = self.thumb_layout.itemAt(i).widget()
            widget.setParent(None)
        keyword = self.search_input.text()
        self.search_thread = SearchWorker(keyword, 2)
        self.search_thread.thumbnail_ready.connect(self.add_thumbnail)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()

    def add_thumbnail(self, pixmap, url):
        index = self.thumb_layout.count()
        row = index // 3
        col = index % 2
        label = ClickableLabel(url)
        label.setPixmap(pixmap)
        label.rightButtonClicked.connect(self.download_original)
        self.thumb_layout.addWidget(label, row, col)

    def download_original(self, url):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.download_thread = DownloadWorker(url, self.save_dir)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.completed.connect(self.show_download_complete)
        self.download_thread.start()

    def on_search_finished(self, n):
        self.statusBar().showMessage(f'共加载 {n} 张缩略图')
        self.search_button.setEnabled(True)

    def show_download_complete(self, path):
        QTimer.singleShot(3000,lambda: self.progress_bar.setVisible(False))
        msg = QMessageBox(self)
        msg.setText(f'{path}下载完成')
        msg.show()
        QTimer.singleShot(3000, msg.accept)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = WallpaperApp()
    window.show()
    sys.exit(app.exec())
