import requests

from version import APP_VERSION


VERSION_URL = "https://raw.githubusercontent.com/MarewBFN/grafik-dino/version.json"


def check_for_updates():
    try:
        response = requests.get(VERSION_URL, timeout=5)
        data = response.json()

        latest = data.get("version")

        if latest and latest != APP_VERSION:
            return {
                "available": True,
                "version": latest,
                "url": data.get("download_url")
            }

    except Exception as e:
        print("[UPDATE ERROR]", e)

    return {
        "available": False
    }