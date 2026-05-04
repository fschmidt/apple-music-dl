"""Embed a webview pointing at music.apple.com, harvest the media-user-token cookie."""
import threading
import time
from typing import Callable

import webview

LOGIN_URL = "https://music.apple.com"
COOKIE_NAME = "media-user-token"
POLL_INTERVAL_S = 1.0
TIMEOUT_S = 300


def _extract_token(window) -> str | None:
    for jar in window.get_cookies():
        for name, morsel in jar.items():
            if name == COOKIE_NAME and morsel.value:
                return morsel.value
    return None


def login(on_token: Callable[[str], None]) -> None:
    """Open a login window. When the cookie appears, call on_token(token) and close."""
    win = webview.create_window(
        title="Sign in to Apple Music",
        url=LOGIN_URL,
        width=900,
        height=700,
    )

    def poll():
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_S)
            try:
                token = _extract_token(win)
            except Exception:
                continue
            if token:
                on_token(token)
                win.destroy()
                return

    threading.Thread(target=poll, daemon=True).start()
