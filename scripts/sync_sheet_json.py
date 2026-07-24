#!/usr/bin/env python3
"""Sinkronkan Google Sheet (via Apps Script) menjadi JSON statis GitHub Pages.

Hasil sinkronisasi:
- data/popular.json: enam produk populer + ringkasan rating seluruh game.
- data/<game>.json: produk satu game + ringkasan rating game tersebut.

Komentar pelanggan tidak disimpan ke JSON publik ini. Komentar baru diambil dari
Apps Script setelah pengunjung menekan tombol untuk melihat ulasan.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyzVtkIaOI6qbrlrlKJAKzON3V5upOrgx_TeDAVAmCG-_gh5JwM9Ngrc4krPqrrut-ulA/exec"
)
BASE_URL = os.environ.get("APPS_SCRIPT_URL", DEFAULT_APPS_SCRIPT_URL).strip()
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HOME_FILE = ROOT / "index.html"
POPULAR_DATA_START = "<!-- WILLPEDIA_POPULAR_DATA_START -->"
POPULAR_DATA_END = "<!-- WILLPEDIA_POPULAR_DATA_END -->"

GAME_FILES: dict[str, str] = {
    "genshin": "genshin.json",
    "hsr": "hsr.json",
    "zzz": "zzz.json",
    "wuwa": "wuwa.json",
}

GAME_NAMES: dict[str, str] = {
    "genshin": "GENSHIN IMPACT",
    "hsr": "HONKAI STAR RAIL",
    "zzz": "ZENLESS ZONE ZERO",
    "wuwa": "WUTHERING WAVES",
}


def request_json(params: dict[str, str]) -> dict[str, Any]:
    query = dict(params)
    query["_sync"] = str(int(time.time()))
    url = f"{BASE_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Willpedia-GitHub-Sync/2.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Respons Apps Script bukan object JSON.")
    if payload.get("success") is False:
        raise ValueError(str(payload.get("message") or "Apps Script mengembalikan error."))
    return payload


def fetch_products(params: dict[str, str]) -> dict[str, Any]:
    payload = request_json(params)
    products = payload.get("products")
    if not isinstance(products, list):
        raise ValueError("Respons Apps Script tidak memiliki array products.")
    payload["products"] = [item for item in products if isinstance(item, dict)]
    payload["success"] = True
    return payload


def fetch_rating_summaries() -> dict[str, dict[str, Any]]:
    """Ambil ringkasan rating seluruh game, tanpa menyimpan komentar ke JSON."""
    payload = request_json({"action": "all_game_reviews"})
    raw_games = payload.get("games")
    if not isinstance(raw_games, dict):
        raise ValueError("Respons rating tidak memiliki object games.")

    summaries: dict[str, dict[str, Any]] = {}
    for game_key, game_name in GAME_NAMES.items():
        raw = raw_games.get(game_name, {})
        if not isinstance(raw, dict):
            raw = {}
        total = int(float(raw.get("jumlah_ulasan") or 0))
        average = float(raw.get("rata_rata") or 0)
        summaries[game_key] = {
            "average": round(average, 1),
            "total": max(0, total),
        }
    return summaries


def serialize(payload: dict[str, Any]) -> str:
    # Deterministik: file tidak berubah jika produk/rating tidak berubah.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == content:
        print(f"Tidak berubah: {path.relative_to(ROOT)}")
        return False
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    print(f"Diperbarui: {path.relative_to(ROOT)}")
    return True


def embed_popular_payload(payload: dict[str, Any]) -> bool:
    """Tanam data populer ke index.html agar halaman home tidak perlu fetch saat dibuka."""
    if not HOME_FILE.exists():
        raise ValueError("index.html tidak ditemukan untuk penyisipan data populer.")
    html = HOME_FILE.read_text(encoding="utf-8")
    start = html.find(POPULAR_DATA_START)
    end = html.find(POPULAR_DATA_END, start + len(POPULAR_DATA_START))
    if start < 0 or end < 0:
        raise ValueError("Marker data populer tidak ditemukan di index.html.")
    safe_json = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).replace("</", "<\\/")
    block = (
        f"{POPULAR_DATA_START}\n"
        f"    <script id=\"willpedia-popular-data\" type=\"application/json\">"
        f"{safe_json}</script>\n"
        f"    {POPULAR_DATA_END}"
    )
    updated = html[:start] + block + html[end + len(POPULAR_DATA_END):]
    return write_if_changed(HOME_FILE, updated)


def main() -> int:
    if not BASE_URL.startswith("https://script.google.com/"):
        print("APPS_SCRIPT_URL tidak valid.", file=sys.stderr)
        return 2

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    changed = 0

    try:
        ratings = fetch_rating_summaries()

        popular = fetch_products({"action": "popular"})
        popular["ratings"] = ratings
        # Tidak ikut menyimpan comments dari endpoint rating.
        changed += int(write_if_changed(DATA_DIR / "popular.json", serialize(popular)))
        changed += int(embed_popular_payload(popular))

        for game_key, filename in GAME_FILES.items():
            payload = fetch_products({"action": "products", "game": game_key})
            payload["rating"] = ratings.get(game_key, {"average": 0, "total": 0})
            changed += int(write_if_changed(DATA_DIR / filename, serialize(payload)))

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"Sinkronisasi gagal: {exc}", file=sys.stderr)
        return 1

    print(f"Sinkronisasi selesai. {changed} file berubah (termasuk index.html bila data populer berubah).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
