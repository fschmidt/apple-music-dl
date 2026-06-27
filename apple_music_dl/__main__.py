"""Entry point: pywebview window with a Python<->JS bridge."""
import json
import queue as queuelib
import threading
from dataclasses import asdict
from pathlib import Path

import webview

from . import auth, downloader, token_store

DEFAULT_OUTPUT = Path.home() / "Music" / "AppleDL"
UI_DIR = Path(__file__).parent / "ui"


class JsApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self._queue: "queuelib.Queue[dict]" = queuelib.Queue()
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()

    # --- auth -------------------------------------------------------------

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

    # --- search -----------------------------------------------------------

    def search(self, term: str) -> dict:
        term = (term or "").strip()
        if not term:
            return {"results": []}
        token = token_store.load()
        if not token:
            return {"error": "Not logged in."}
        try:
            results = downloader.search_sync(term, token)
            return {"results": [asdict(r) for r in results]}
        except Exception as e:
            return {"error": str(e)}

    # --- download queue ---------------------------------------------------

    def enqueue(self, item: dict) -> None:
        """item: {id, url, title, mp3}. Processed serially by a worker thread."""
        if not token_store.load():
            self._emit({
                "type": "item-error",
                "id": item.get("id"),
                "message": "Not logged in.",
            })
            return
        self._queue.put(item)
        self._emit({"type": "queued", "id": item.get("id")})
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run_worker, daemon=True)
            self._worker.start()

    def _run_worker(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queuelib.Empty:
                return
            try:
                self._process_item(item)
            finally:
                self._queue.task_done()

    def _process_item(self, item: dict) -> None:
        item_id = item.get("id")
        token = token_store.load()
        if not token:
            self._emit({"type": "item-error", "id": item_id, "message": "Not logged in."})
            return

        self._emit({"type": "item-start", "id": item_id})
        counts = {"ok": 0, "failed": 0, "skipped": 0}

        def on_track(r: downloader.TrackResult) -> None:
            if r.error:
                counts["failed"] += 1
            elif r.skipped:
                counts["skipped"] += 1
            else:
                counts["ok"] += 1
            self._emit({
                "type": "track",
                "id": item_id,
                "title": r.title,
                "path": str(r.final_path) if r.final_path else None,
                "error": r.error,
                "skipped": r.skipped,
            })

        try:
            downloader.download_url_sync(
                url=item["url"],
                media_user_token=token,
                output_path=DEFAULT_OUTPUT,
                convert_to_mp3=bool(item.get("mp3", True)),
                on_track=on_track,
            )
            self._emit({"type": "item-done", "id": item_id, **counts})
        except Exception as e:
            self._emit({"type": "item-error", "id": item_id, "message": str(e)})

    # --- helpers ----------------------------------------------------------

    def _emit(self, payload: dict) -> None:
        if not self.window:
            return
        self.window.evaluate_js(
            f"window.onEvent && window.onEvent({json.dumps(payload)});"
        )


def main() -> None:
    api = JsApi()
    window = webview.create_window(
        title="Apple Music DL",
        url=str(UI_DIR / "index.html"),
        js_api=api,
        width=820,
        height=720,
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
