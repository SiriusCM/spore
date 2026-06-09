"""
Spore Desktop App - PyQt6 + Flask 一体化应用
"""
import os
import sys
import threading


# ── 平台特定的 QtWebEngine 渲染参数（必须在 QApplication 创建之前设置） ──
# Windows 11 上 QtWebEngine 的 D3D 合成器 + 多层 backdrop-filter blur 会导致弹窗闪烁。
# 这里通过 Chromium flags 让 Skia 接管渲染并禁用强制 vsync，同时关闭 GPU 合成里
# 已知会引发抖动的"线程化合成 + partial-raster"组合。
if sys.platform.startswith("win"):
    _flags = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        + " --disable-gpu-vsync"
        + " --disable-frame-rate-limit"
        + " --enable-features=UseSkiaRenderer"
        + " --disable-features=PaintHolding"
    )
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags.strip()


from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QIcon

from server import app as flask_app
from settings import PKG_DIR


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


class SporeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spore Agent")
        self.setGeometry(100, 100, 600, 800)

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
            self.setWindowTitle("Spore Agent - 已就绪")
        else:
            self.setWindowTitle(f"Spore Agent - 加载中 {progress}%")


def run_desktop():
    """运行桌面应用"""
    # 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName("Spore Agent")

    # 设置应用图标
    icon_path = os.path.join(PKG_DIR, "config", "icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

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
    window = SporeWindow()
    # 窗口也设置图标（macOS 下 dock 图标需要单独设置）
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()

    return app.exec()