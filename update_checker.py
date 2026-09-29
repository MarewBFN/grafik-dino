import os
import tempfile

import requests

from release_channel import RELEASE_CHANNEL
from version import APP_VERSION


MANIFEST_BASE_URL = "https://raw.githubusercontent.com/MarewBFN/grafik-dino/main/releases"
INSTALLER_ASSET_NAME = "DingoSetup.exe"

DOWNLOAD_CHUNK_SIZE = 1024 * 256


def _manifest_url():
    return f"{MANIFEST_BASE_URL}/{RELEASE_CHANNEL}.json"


def _parse_version(value: str) -> tuple:
    value = value.strip().lstrip("vV")
    parts = []
    for piece in value.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _is_newer(remote: str, local: str) -> bool:
    remote_v = _parse_version(remote)
    local_v = _parse_version(local)

    length = max(len(remote_v), len(local_v))
    remote_v = remote_v + (0,) * (length - len(remote_v))
    local_v = local_v + (0,) * (length - len(local_v))

    return remote_v > local_v


def check_for_updates():
    try:
        response = requests.get(_manifest_url(), timeout=5)

        if response.status_code == 404:
            return {"available": False}

        response.raise_for_status()
        data = response.json()

        latest = data.get("latest_version")
        if not latest:
            return {"available": False}

        if not _is_newer(latest, APP_VERSION):
            return {"available": False}

        download_url = data.get("download_url")
        if not download_url:
            return {"available": False}

        return {
            "available": True,
            "version": latest,
            "url": download_url,
            "notes": (data.get("changelog") or "").strip(),
        }

    except Exception as e:
        print("[UPDATE ERROR]", e)
        return {"available": False, "error": str(e)}


def download_installer(url, progress_callback=None, dest_path=None):
    if dest_path is None:
        dest_path = os.path.join(tempfile.gettempdir(), INSTALLER_ASSET_NAME)

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    total = int(response.headers.get("Content-Length", 0))
    downloaded = 0

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)

    return dest_path
