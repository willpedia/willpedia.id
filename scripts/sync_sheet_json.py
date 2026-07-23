#!/usr/bin/env python3
"""Sinkronkan Google Sheet (via Apps Script) menjadi JSON statis GitHub Pages.

Hasil sinkronisasi:
- data/popular.json: enam produk populer + ringkasan rating seluruh game.
- data/<game>.json: produk satu game + ringkasan rating game tersebut.
- data/reviews.json: maksimal 12 komentar Approved untuk homepage.

Website membaca file JSON langsung dari GitHub Pages. Apps Script tetap dipakai oleh
GitHub Actions sebagai sumber sinkronisasi dan oleh form pengiriman ulasan.
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
MAX_HOME_REVIEWS = 12

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
            "User-Agent": "Willpedia-GitHub-Sync/3.0",
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


def normalize_review(raw: dict[str, Any], game_name: str) -> dict[str, Any] | None:
    comment = str(raw.get("Komentar") or "").strip()
    if not comment:
        return None
    try:
        rating = int(round(float(raw.get("Rating") or 0)))
    except (TypeError, ValueError):
        rating = 0
    rating = max(0, min(5, rating))
    return {
        "ID_Komentar": str(raw.get("ID_Komentar") or "").strip(),
        "ID_Produk": str(raw.get("ID_Produk") or "").strip(),
        "Nama": str(raw.get("Nama") or "Pengguna").strip()[:50],
        "Rating": rating,
        "Komentar": comment[:300],
        "Tanggal": str(raw.get("Tanggal") or "").strip(),
        "Game": game_name,
    }


def collect_balanced_reviews(game_queues: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    queues = [list(queue) for queue in game_queues if queue]
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()
    queue_index = 0

    while queues and len(reviews) < MAX_HOME_REVIEWS:
        current_index = queue_index % len(queues)
        queue = queues[current_index]
        review = queue.pop(0)
        if not queue:
            queues.pop(current_index)
        else:
            queue_index += 1

        signature = "|".join(
            [
                str(review.get("ID_Komentar") or ""),
                str(review.get("Nama") or ""),
                str(review.get("Komentar") or ""),
                str(review.get("Tanggal") or ""),
            ]
        ).lower()
        if signature in seen:
            continue
        seen.add(signature)
        reviews.append(review)

    return reviews


def fetch_rating_and_reviews() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Ambil rating dan komentar Approved dalam satu request Apps Script."""
    payload = request_json({"action": "all_game_reviews"})
    raw_games = payload.get("games")
    if not isinstance(raw_games, dict):
        raise ValueError("Respons rating tidak memiliki object games.")

    summaries: dict[str, dict[str, Any]] = {}
    review_queues: list[list[dict[str, Any]]] = []

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

        queue: list[dict[str, Any]] = []
        raw_comments = raw.get("comments")
        if isinstance(raw_comments, list):
            for item in raw_comments:
                if not isinstance(item, dict):
                    continue
                normalized = normalize_review(item, game_name)
                if normalized:
                    queue.append(normalized)
        review_queues.append(queue)

    return summaries, collect_balanced_reviews(review_queues)


def serialize(payload: dict[str, Any]) -> str:
    # Deterministik: file tidak berubah jika data Sheet tidak berubah.
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


def main() -> int:
    if not BASE_URL.startswith("https://script.google.com/"):
        print("APPS_SCRIPT_URL tidak valid.", file=sys.stderr)
        return 2

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    changed = 0

    try:
        ratings, reviews = fetch_rating_and_reviews()

        popular = fetch_products({"action": "popular"})
        popular["ratings"] = ratings
        changed += int(write_if_changed(DATA_DIR / "popular.json", serialize(popular)))

        reviews_payload = {"success": True, "reviews": reviews}
        changed += int(write_if_changed(DATA_DIR / "reviews.json", serialize(reviews_payload)))

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

    print(f"Sinkronisasi selesai. {changed} file berubah.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
