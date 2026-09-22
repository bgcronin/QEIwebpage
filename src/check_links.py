#!/usr/bin/env python3
"""Check internal links, images and anchors in the built site (web/)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=str(ROOT / "web"))
    ap.add_argument("--strict", action="store_true", help="exit non-zero on broken links")
    args = ap.parse_args()
    site = Path(args.site).resolve()
    pages = sorted(site.rglob("*.html"))
    broken: list[tuple[str, str]] = []
    checked = 0
    ids_cache: dict[Path, set[str]] = {}

    def page_ids(path: Path) -> set[str]:
        if path not in ids_cache:
            soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
            ids_cache[path] = {t["id"] for t in soup.find_all(id=True)} | {a["name"] for a in soup.find_all("a", attrs={"name": True})}
        return ids_cache[path]

    for page in pages:
        rel_dir = page.parent
        soup = BeautifulSoup(page.read_text(encoding="utf-8", errors="ignore"), "lxml")
        refs = [(a.get("href") or "", "link") for a in soup.find_all("a")]
        refs += [(i.get("src") or "", "img") for i in soup.find_all("img")]
        refs += [(l.get("href") or "", "asset") for l in soup.find_all("link") if l.get("rel") and ("stylesheet" in l["rel"] or "icon" in l["rel"] or "manifest" in l["rel"] or "preload" in l["rel"])]
        refs += [(s.get("src") or "", "script") for s in soup.find_all("script") if s.get("src")]
        for ref, kind in refs:
            if not ref or re.match(r"^(https?:|mailto:|tel:|data:|javascript:)", ref):
                continue
            checked += 1
            path_part, _, frag = ref.partition("#")
            path_part = unquote(path_part.split("?")[0])
            if path_part == "":
                target = page
            elif path_part.startswith("/"):
                target = (site / path_part.lstrip("/")).resolve()
            else:
                target = (rel_dir / path_part).resolve()
                if path_part.endswith("/"):
                    target = target / "index.html"
                elif target.is_dir():
                    target = target / "index.html"
            if not target.exists():
                broken.append((str(page.relative_to(site)), f"{kind}: {ref}"))
                continue
            if frag and target.suffix == ".html" and frag not in page_ids(target):
                broken.append((str(page.relative_to(site)), f"anchor: {ref}"))
    print(f"Checked {checked} references across {len(pages)} pages; {len(broken)} broken")
    seen = set()
    for page, ref in broken:
        key = ref
        if key in seen:
            continue
        seen.add(key)
        count = sum(1 for _, r in broken if r == ref)
        print(f"  {ref}  (first in {page}{', ' + str(count) + ' pages' if count > 1 else ''})")
    return 1 if (broken and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
