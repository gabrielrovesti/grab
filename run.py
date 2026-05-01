import os
import socket
import threading

import uvicorn
import webview

from main import app

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging"

HOST = "0.0.0.0"
PORT = 8765


class Api:
    def choose_path(self, filename):
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=("Audio Files (*.mp3)",),
        )
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result


def _wait_for_server():
    while True:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.1):
                return
        except OSError:
            pass


def start_server():
    uvicorn.run(app, host=HOST, port=PORT, log_level="error")


if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    _wait_for_server()

    webview.create_window(
        "grab",
        f"http://127.0.0.1:{PORT}",
        width=740,
        height=700,
        resizable=True,
        js_api=Api(),
    )
    webview.start(gui="qt")
