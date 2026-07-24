#!/usr/bin/env python3
"""Sinkronkan Google Sheet (via Apps Script) menjadi JSON statis GitHub Pages.

Hasil sinkronisasi:
- data/popular.json: enam produk populer + ringkasan rating seluruh game.
- data/<game>.json: produk satu game + ringkasan rating game tersebut.
- data/reviews.json: komentar pelanggan yang sudah tersedia dari Apps Script.
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
    "AKfycbwWfP0jLzMPt1w5F2s5e_XxTrpy90jYET9M-KoNke5vY-nv8s7dL_jTysmcL5YIkLuAYA/exec"
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


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _normalize_review(item: Any, game_name: str = "") -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    normalized_game = str(
        item.get("Game")
        or item.get("game")
        or item.get("__gameName")
        or game_name
        or "Game"
    ).strip().upper()
    return {
        **item,
        "Nama": item.get("Nama") or item.get("nama") or item.get("name") or "Pengguna",
        "Rating": item.get("Rating") if item.get("Rating") is not None else item.get("rating", 0),
        "Komentar": item.get("Komentar") or item.get("komentar") or item.get("comment") or item.get("ulasan") or "",
        "Tanggal": item.get("Tanggal") or item.get("tanggal") or item.get("date") or "",
        "Game": normalized_game,
        "__gameName": normalized_game,
    }


def fetch_review_data() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Ambil ringkasan rating dan komentar yang tersedia dari Apps Script."""
    payload = request_json({"action": "all_game_reviews"})
    raw_games = payload.get("games")
    if not isinstance(raw_games, dict):
        raise ValueError("Respons rating tidak memiliki object games.")

    summaries: dict[str, dict[str, Any]] = {}
    reviews: list[dict[str, Any]] = []
    for game_key, game_name in GAME_NAMES.items():
        raw = raw_games.get(game_name, {})
        if not isinstance(raw, dict):
            raw = {}
        raw_comments = _first_list(
            raw.get("comments"), raw.get("komentar"), raw.get("ulasan"), raw.get("reviews")
        )
        normalized_comments = [
            review for item in raw_comments
            if (review := _normalize_review(item, game_name)) is not None
        ]
        reviews.extend(normalized_comments)
        total = int(float(raw.get("jumlah_ulasan") or raw.get("total") or len(normalized_comments) or 0))
        average = float(raw.get("rata_rata") or raw.get("average") or raw.get("rating") or 0)
        summaries[game_key] = {
            "average": round(average, 1),
            "total": max(0, total),
        }

    top_level_comments = _first_list(
        payload.get("comments"), payload.get("reviews"), payload.get("ulasan")
    )
    reviews.extend(
        review for item in top_level_comments
        if (review := _normalize_review(item)) is not None
    )

    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for review in reviews:
        key = (
            str(review.get("Game", "")).lower(),
            str(review.get("Nama", "")).lower(),
            str(review.get("Komentar", "")).lower(),
            str(review.get("Tanggal", "")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(review)
    return summaries, deduplicated


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
        ratings, reviews = fetch_review_data()

        popular = fetch_products({"action": "popular"})
        popular["ratings"] = ratings
        changed += int(write_if_changed(DATA_DIR / "reviews.json", serialize({"success": True, "reviews": reviews})))
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
