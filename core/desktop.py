"""
Starfish Desktop App - PyQt6 + Flask 一体化应用
"""
import os
import sys
import threading

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.server import app as flask_app


class ServerSignals(QObject):
    """服务器信号"""
    started = pyqtSignal()
    error = pyqtSignal(str)


def run_flask_server(host: str = "127.0.0.1", port: int = 8765, signals: ServerSignals = None):
    """在后台线程运行 Flask 服务器"""
    try:
        flask_app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        if signals:
            signals.error.emit(str(e))


class StarfishWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Starfish Agent")
        self.setGeometry(100, 100, 800, 600)

        # 创建 WebView
        self.browser = QWebEngineView()
        http_url = "http://127.0.0.1:8765"
        self.browser.setUrl(QUrl(http_url))

        # 加载失败处理
        self.browser.loadFinished.connect(self.on_load_finished)
        self.browser.loadProgress.connect(self.on_load_progress)

        self.setCentralWidget(self.browser)

    def on_load_finished(self, ok):
        if not ok:
            QMessageBox.warning(
                self,
                "加载失败",
                "无法加载界面，请检查服务是否正常启动。"
            )

    def on_load_progress(self, progress):
        if progress == 100:
            self.setWindowTitle("Starfish Agent - 已就绪")
        else:
            self.setWindowTitle(f"Starfish Agent - 加载中 {progress}%")


def run_desktop():
    """运行桌面应用"""
    # 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName("Starfish Agent")

    # 启动信号
    signals = ServerSignals()

    # 在后台线程启动 Flask 服务器
    server_thread = threading.Thread(
        target=run_flask_server,
        args=("127.0.0.1", 8765, signals),
        daemon=True
    )
    server_thread.start()

    # 等待服务器就绪
    import time
    for _ in range(50):  # 最多等 5 秒
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("127.0.0.1", 8765))
            sock.close()
            if result == 0:
                break
        except:
            pass
        time.sleep(0.1)

    # 创建并显示窗口
    window = StarfishWindow()
    window.show()

    return app.exec()