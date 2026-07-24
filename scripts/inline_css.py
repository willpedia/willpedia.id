#!/usr/bin/env python3
"""Sisipi assets/css/willpedia.min.css ke seluruh index.html.

Jalankan setelah mengubah CSS:
    python scripts/inline_css.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = ROOT / "assets" / "css" / "willpedia.min.css"
STYLE_RE = re.compile(
    r'<style id="willpedia-critical-css">.*?</style>',
    re.DOTALL,
)
LINK_RE = re.compile(
    r'<link href="assets/css/willpedia\.min\.css\?v=[^"]+" rel="stylesheet"/>'
)


def main() -> int:
    css = CSS_FILE.read_text(encoding="utf-8")
    # URL font dalam style inline harus relatif terhadap dokumen, bukan file CSS.
    inline_css = css.replace('url("../webfonts/', 'url("assets/webfonts/').replace(
        "url('../webfonts/", "url('assets/webfonts/"
    )
    style = f'<style id="willpedia-critical-css">{inline_css}</style>'

    pages = [ROOT / "index.html", *sorted(ROOT.glob("*/index.html"))]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        if STYLE_RE.search(html):
            updated = STYLE_RE.sub(lambda _: style, html, count=1)
        elif LINK_RE.search(html):
            updated = LINK_RE.sub(lambda _: style, html, count=1)
        else:
            raise RuntimeError(f"Marker CSS tidak ditemukan: {page.relative_to(ROOT)}")
        page.write_text(updated, encoding="utf-8")
        print(f"Diperbarui: {page.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
