#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from common import load_config, write_json


def candidate_paths(base: Path, value: str) -> list[Path]:
    parsed = urlparse(value)
    path_text = unquote(parsed.path)
    if not path_text or path_text == "/":
        return [base / "index.html"]
    candidate = (base / path_text).resolve()
    return [candidate, Path(str(candidate) + ".html"), candidate / "index.html"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a QEI static mirror for safety and completeness.")
    parser.add_argument("--config", default="mirror.config.json")
    parser.add_argument("--site", default="site")
    parser.add_argument("--json-report", default="reports/audit.json")
    parser.add_argument("--markdown-report", default="reports/AUDIT.md")
    parser.add_argument("--strict-links", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    site = Path(args.site).resolve()
    files = [path for path in site.rglob("*") if path.is_file()]
    extension_counts = Counter((path.suffix.lower() or "[no extension]") for path in files)
    html_files = [path for path in files if path.suffix.lower() in {".html", ".htm"}]
    total_bytes = sum(path.stat().st_size for path in files)

    active_forms: list[str] = []
    missing_noindex: list[str] = []
    tracking_refs: list[dict[str, str]] = []
    broken_links: list[dict[str, str]] = []
    transaction_links_not_disabled: list[dict[str, str]] = []
    tracking_fragments = [str(x).lower() for x in config.get("tracking_host_fragments", [])]
    transaction_words = ("donate", "payment", "checkout", "refer-a-patient", "send-enquiry", "medical-record")

    for path in html_files:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
        rel = path.relative_to(site).as_posix()
        for form in soup.find_all("form"):
            if form.get("action") != "#" or form.get("data-qei-static-form") != "disabled":
                active_forms.append(rel)
        robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        if config.get("add_noindex") and (robots is None or "noindex" not in str(robots.get("content", "")).lower()):
            missing_noindex.append(rel)

        for tag in soup.find_all(["script", "iframe", "img", "link"]):
            reference = str(tag.get("src") or tag.get("href") or "")
            if reference and any(fragment in reference.lower() for fragment in tracking_fragments):
                tracking_refs.append({"file": rel, "reference": reference})

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            text = anchor.get_text(" ", strip=True).lower()
            if any(word in (href.lower() + " " + text) for word in transaction_words):
                if anchor.get("data-qei-disabled-transaction") != "true" or href != "#":
                    transaction_links_not_disabled.append({"file": rel, "href": href})

        for tag in soup.find_all(True):
            for attribute in ("href", "src", "poster", "data-src"):
                value = str(tag.get(attribute) or "")
                if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "http://", "https://", "//")):
                    continue
                if "{" in value or "}" in value:
                    continue
                if not any(candidate.exists() for candidate in candidate_paths(path.parent, value)):
                    broken_links.append({"file": rel, "attribute": attribute, "target": value})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "html_file_count": len(html_files),
        "total_bytes": total_bytes,
        "extensions": dict(sorted(extension_counts.items())),
        "safety": {
            "active_forms": active_forms,
            "missing_noindex": missing_noindex,
            "tracking_references": tracking_refs,
            "transaction_links_not_disabled": transaction_links_not_disabled,
        },
        "broken_internal_references": broken_links,
    }
    write_json(args.json_report, report)

    markdown = [
        "# Static mirror audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Files: {len(files):,}",
        f"- HTML pages: {len(html_files):,}",
        f"- Total size: {total_bytes / 1024 / 1024:.2f} MiB",
        f"- Active forms: {len(active_forms)}",
        f"- Pages missing noindex: {len(missing_noindex)}",
        f"- Tracking references remaining: {len(tracking_refs)}",
        f"- Transaction links not disabled: {len(transaction_links_not_disabled)}",
        f"- Broken internal references detected: {len(broken_links)}",
        "",
        "## Safety result",
        "",
    ]
    safety_errors = active_forms + missing_noindex + tracking_refs + transaction_links_not_disabled
    markdown.append("PASS" if not safety_errors else "FAIL")
    if broken_links:
        markdown.extend(["", "## First broken references", ""])
        for item in broken_links[:100]:
            markdown.append(f"- `{item['file']}` → `{item['target']}`")
    Path(args.markdown_report).write_text("\n".join(markdown) + "\n", encoding="utf-8")

    if safety_errors:
        print("Safety audit failed.")
        return 1
    if args.strict_links and broken_links:
        print("Strict link audit failed.")
        return 2
    print(f"Audit passed. Files={len(files)}, pages={len(html_files)}, broken refs={len(broken_links)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
