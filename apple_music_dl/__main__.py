"""Entry point: pywebview window with a Python<->JS bridge."""
import threading
from pathlib import Path

import webview

from . import auth, downloader, token_store

DEFAULT_OUTPUT = Path.home() / "Music" / "AppleDL"
UI_DIR = Path(__file__).parent / "ui"


class JsApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def has_token(self) -> bool:
        return token_store.load() is not None

    def login(self) -> None:
        def _save(token: str) -> None:
            token_store.save(token)
            if self.window:
                self.window.evaluate_js("window.onLoggedIn && window.onLoggedIn();")

        auth.login(_save)

    def logout(self) -> None:
        token_store.clear()

    def download(self, url: str, mp3: bool) -> None:
        token = token_store.load()
        if not token:
            self._emit({"type": "error", "message": "Not logged in."})
            return

        def run() -> None:
            try:
                def on_track(r: downloader.TrackResult) -> None:
                    self._emit({
                        "type": "track",
                        "title": r.title,
                        "path": str(r.final_path) if r.final_path else None,
                        "error": r.error,
                        "skipped": r.skipped,
                    })

                downloader.download_url_sync(
                    url=url,
                    media_user_token=token,
                    output_path=DEFAULT_OUTPUT,
                    convert_to_mp3=mp3,
                    on_track=on_track,
                )
                self._emit({"type": "done"})
            except Exception as e:
                self._emit({"type": "error", "message": str(e)})

        threading.Thread(target=run, daemon=True).start()

    def _emit(self, payload: dict) -> None:
        if not self.window:
            return
        import json
        self.window.evaluate_js(f"window.onEvent && window.onEvent({json.dumps(payload)});")


def main() -> None:
    api = JsApi()
    window = webview.create_window(
        title="Apple Music DL",
        url=str(UI_DIR / "index.html"),
        js_api=api,
        width=720,
        height=520,
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
