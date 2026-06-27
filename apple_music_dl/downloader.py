"""Drive gamdl programmatically and (optionally) transcode the resulting m4a to MP3."""
import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable

from gamdl.api import AppleMusicApi
from gamdl.downloader import (
    AppleMusicBaseDownloader,
    AppleMusicDownloader,
    AppleMusicMusicVideoDownloader,
    AppleMusicSongDownloader,
    AppleMusicUploadedVideoDownloader,
)
from gamdl.interface import (
    AppleMusicBaseInterface,
    AppleMusicInterface,
    AppleMusicMusicVideoInterface,
    AppleMusicSongInterface,
    AppleMusicUploadedVideoInterface,
)


@dataclass
class TrackResult:
    title: str
    final_path: Path | None
    error: str | None = None
    skipped: bool = False


@dataclass
class SearchResult:
    id: str
    kind: str  # "song" | "album"
    title: str
    artist: str
    url: str
    artwork_url: str | None = None
    subtitle: str = ""  # album name (songs) or track count / year (albums)


# The dev token (a JWT scraped from Apple Music's web bundle) is expensive to
# fetch — it requires downloading a ~3 MB JS file. It changes rarely, so cache
# it across calls. It's just a string, so it's safe to reuse across the fresh
# event loops that asyncio.run() creates for each sync call below.
_cached_token: str | None = None


async def _create_api(media_user_token: str) -> AppleMusicApi:
    global _cached_token
    try:
        api = await AppleMusicApi.create(
            media_user_token=media_user_token,
            token=_cached_token,
        )
    except Exception:
        # Cached token may be stale/invalid — refresh once from scratch.
        _cached_token = None
        api = await AppleMusicApi.create(media_user_token=media_user_token)
    _cached_token = api.token
    return api


def _normalize_search(raw: dict) -> list[SearchResult]:
    results = raw.get("results", {}) or {}
    out: list[SearchResult] = []
    for kind, data_key in (("song", "songs"), ("album", "albums")):
        section = results.get(data_key, {}) or {}
        for item in section.get("data", []) or []:
            attrs = item.get("attributes", {}) or {}
            art = attrs.get("artwork", {}) or {}
            artwork_url = None
            if art.get("url"):
                artwork_url = (
                    art["url"].replace("{w}", "120").replace("{h}", "120")
                    .replace("{c}", "bb").replace("{f}", "jpg")
                )
            if kind == "song":
                subtitle = attrs.get("albumName", "")
            else:
                count = attrs.get("trackCount")
                year = (attrs.get("releaseDate", "") or "")[:4]
                parts = [p for p in (f"{count} tracks" if count else "", year) if p]
                subtitle = " · ".join(parts)
            out.append(
                SearchResult(
                    id=str(item.get("id", "")),
                    kind=kind,
                    title=attrs.get("name", "Unknown"),
                    artist=attrs.get("artistName", ""),
                    url=attrs.get("url", ""),
                    artwork_url=artwork_url,
                    subtitle=subtitle,
                )
            )
    return out


def search_sync(
    term: str,
    media_user_token: str,
    *,
    types: str = "songs,albums",
    limit: int = 25,
) -> list[SearchResult]:
    """Search the Apple Music catalog for songs and albums (blocking)."""
    async def _run() -> list[SearchResult]:
        api = await _create_api(media_user_token)
        try:
            raw = await api.get_search_results(term=term, types=types, limit=limit)
        finally:
            await api.client.aclose()
        return _normalize_search(raw)

    return asyncio.run(_run())


async def _build_downloader(
    media_user_token: str,
    output_path: Path,
    temp_path: Path,
) -> AppleMusicDownloader:
    api = await _create_api(media_user_token)
    if not api.active_subscription:
        raise RuntimeError("No active Apple Music subscription on this account.")

    base_iface = await AppleMusicBaseInterface.create(apple_music_api=api)
    song_iface = AppleMusicSongInterface(base=base_iface)
    mv_iface = AppleMusicMusicVideoInterface(base=base_iface)
    uv_iface = AppleMusicUploadedVideoInterface(base=base_iface)
    interface = AppleMusicInterface(
        song=song_iface, music_video=mv_iface, uploaded_video=uv_iface
    )

    base_dl = AppleMusicBaseDownloader(
        interface=interface,
        output_path=str(output_path),
        temp_path=str(temp_path),
    )
    return AppleMusicDownloader(
        song=AppleMusicSongDownloader(base=base_dl),
        music_video=AppleMusicMusicVideoDownloader(base=base_dl),
        uploaded_video=AppleMusicUploadedVideoDownloader(base=base_dl),
    )


def _transcode_to_mp3(src: Path, bitrate: str = "256k") -> Path:
    dst = src.with_suffix(".mp3")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-map_metadata", "0",
        "-id3v2_version", "3",
        str(dst),
    ]
    subprocess.check_call(cmd)
    src.unlink(missing_ok=True)
    return dst


async def download_url(
    url: str,
    media_user_token: str,
    output_path: Path,
    *,
    convert_to_mp3: bool = False,
    on_track: Callable[[TrackResult], None] | None = None,
) -> AsyncIterator[TrackResult]:
    """Yield one TrackResult per track. Handles song / album / playlist URLs."""
    if convert_to_mp3 and not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH (required for MP3 output).")

    output_path.mkdir(parents=True, exist_ok=True)
    temp_path = output_path / ".tmp"
    temp_path.mkdir(exist_ok=True)

    downloader = await _build_downloader(media_user_token, output_path, temp_path)

    async for item in downloader.get_download_item_from_url(url):
        # gamdl yields each media twice — first as a `partial` placeholder
        # (download() is a no-op, final_path stays None), then resolved.
        if item.media.partial:
            continue

        title = (
            item.media.media_metadata.get("attributes", {}).get("name", "Unknown")
            if item.media.media_metadata else "Unknown"
        )
        try:
            await downloader.download(item)
            if item.final_path is None:
                result = TrackResult(title=title, final_path=None, skipped=True)
            else:
                final = Path(item.final_path)
                if convert_to_mp3 and final.suffix.lower() == ".m4a":
                    final = _transcode_to_mp3(final)
                result = TrackResult(title=title, final_path=final)
        except Exception as e:
            result = TrackResult(title=title, final_path=None, error=str(e))

        if on_track:
            on_track(result)
        yield result


def download_url_sync(
    url: str,
    media_user_token: str,
    output_path: Path,
    *,
    convert_to_mp3: bool = False,
    on_track: Callable[[TrackResult], None] | None = None,
) -> list[TrackResult]:
    """Blocking helper for non-async callers (e.g., the pywebview JS bridge)."""
    async def _run():
        out = []
        async for r in download_url(
            url, media_user_token, output_path,
            convert_to_mp3=convert_to_mp3, on_track=on_track,
        ):
            out.append(r)
        return out

    return asyncio.run(_run())
