#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from common import load_config, write_json
from postprocess import (
    GUARD_SCRIPT_ID,
    GUARD_STYLE_ID,
    INLINE_TRACKING_PATTERNS,
    link_is_external_transaction,
)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def candidate_paths(base: Path, site_root: Path, value: str) -> list[Path]:
    parsed = urlparse(value)
    path_text = unquote(parsed.path)
    if not path_text:
        return []

    if path_text.startswith("/"):
        candidate = (site_root / path_text.lstrip("/")).resolve()
    else:
        candidate = (base / path_text).resolve()
    if not is_within(candidate, site_root):
        return []
    if path_text.endswith("/") or candidate.is_dir():
        return [candidate, candidate / "index.html"]
    return [candidate, Path(str(candidate) + ".html"), candidate / "index.html"]


def tracking_match(reference: str, inline: str, tracking_fragments: list[str]) -> bool:
    lowered_reference = reference.lower()
    lowered_inline = inline.lower()
    return any(fragment in lowered_reference for fragment in tracking_fragments) or any(
        pattern in lowered_inline for pattern in INLINE_TRACKING_PATTERNS
    )


def form_safety_issues(form) -> list[str]:
    issues: list[str] = []
    if form.get("action") != "#":
        issues.append("action is not #")
    if str(form.get("method", "")).lower() != "get":
        issues.append("method is not GET")
    if form.get("data-qei-static-form") != "disabled":
        issues.append("missing disabled marker")
    if "return false" not in str(form.get("onsubmit", "")).lower():
        issues.append("missing submit blocker")

    for control_index, control in enumerate(form.find_all(["input", "textarea", "select", "button"]), start=1):
        label = f"{control.name}[{control_index}]"
        if not control.has_attr("disabled"):
            issues.append(f"{label} is enabled")
        if control.has_attr("name"):
            issues.append(f"{label} retains a name")
        if control.has_attr("formaction"):
            issues.append(f"{label} retains formaction")
        control_type = str(control.get("type", "")).lower()
        if control.name == "button" and control_type not in {"", "button"}:
            issues.append(f"{label} can submit")
        if control.name == "input" and control_type in {"submit", "image"}:
            issues.append(f"{label} can submit")
    return issues


def iter_srcset_urls(value: str):
    for item in value.split(","):
        tokens = item.strip().split()
        if tokens:
            yield tokens[0]


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
    css_files = [path for path in files if path.suffix.lower() == ".css"]
    total_bytes = sum(path.stat().st_size for path in files)
    oversized_files = [
        {"file": path.relative_to(site).as_posix(), "bytes": path.stat().st_size}
        for path in files
        if path.stat().st_size >= 95 * 1024 * 1024
    ]

    active_forms: list[dict[str, object]] = []
    missing_noindex: list[str] = []
    missing_safety_guard: list[str] = []
    tracking_refs: list[dict[str, str]] = []
    broken_links: list[dict[str, str]] = []
    transaction_links_not_disabled: list[dict[str, str]] = []
    tracking_fragments = [str(x).lower() for x in config.get("tracking_host_fragments", [])]
    robots_path = site / "robots.txt"
    robots_text = robots_path.read_text(encoding="utf-8", errors="replace").lower() if robots_path.exists() else ""
    robots_txt_blocked = "user-agent: *" in robots_text and "disallow: /" in robots_text
    missing_robots_block = [] if not config.get("add_noindex") or robots_txt_blocked else ["robots.txt"]

    for path in html_files:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
        rel = path.relative_to(site).as_posix()

        for form_index, form in enumerate(soup.find_all("form"), start=1):
            issues = form_safety_issues(form)
            if issues:
                active_forms.append({"file": rel, "form": form_index, "issues": issues})

        if config.get("disable_forms"):
            if soup.find("script", id=GUARD_SCRIPT_ID) is None or soup.find("style", id=GUARD_STYLE_ID) is None:
                missing_safety_guard.append(rel)

        robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        if config.get("add_noindex") and (robots is None or "noindex" not in str(robots.get("content", "")).lower()):
            missing_noindex.append(rel)

        for tag in soup.find_all(["script", "iframe", "img", "link", "noscript"]):
            reference = str(tag.get("src") or tag.get("href") or "")
            inline = tag.get_text(" ", strip=False) if tag.name in {"script", "noscript"} else ""
            if tracking_match(reference, inline, tracking_fragments):
                tracking_refs.append({"file": rel, "reference": reference or "[inline tracking code]"})

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            text = anchor.get_text(" ", strip=True)
            original_href = str(anchor.get("data-original-href") or "")
            active_sensitive_link = link_is_external_transaction(href, text, config)
            malformed_disabled_link = bool(original_href) and link_is_external_transaction(original_href, text, config) and (
                anchor.get("data-qei-disabled-transaction") != "true" or href != "#"
            )
            if active_sensitive_link or malformed_disabled_link:
                transaction_links_not_disabled.append({"file": rel, "href": href, "text": text[:120]})

        for tag in soup.find_all(True):
            references: list[tuple[str, str]] = []
            for attribute in ("href", "src", "poster", "data-src", "data-lazy-src", "data-background-image"):
                value = str(tag.get(attribute) or "")
                if value:
                    references.append((attribute, value))
            if tag.has_attr("srcset"):
                references.extend(("srcset", value) for value in iter_srcset_urls(str(tag.get("srcset") or "")))

            for attribute, value in references:
                if value.startswith(("#", "?", "mailto:", "tel:", "javascript:", "data:", "http://", "https://", "//")):
                    continue
                if "{" in value or "}" in value:
                    continue
                candidates = candidate_paths(path.parent, site, value)
                if not candidates or not any(candidate.exists() for candidate in candidates):
                    broken_links.append({"file": rel, "attribute": attribute, "target": value})

    for path in css_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for fragment in tracking_fragments:
            if fragment in text.lower():
                tracking_refs.append({"file": path.relative_to(site).as_posix(), "reference": fragment})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "html_file_count": len(html_files),
        "total_bytes": total_bytes,
        "extensions": dict(sorted(extension_counts.items())),
        "oversized_files": oversized_files,
        "safety": {
            "active_or_incompletely_disabled_forms": active_forms,
            "missing_safety_guard": missing_safety_guard,
            "missing_noindex": missing_noindex,
            "missing_robots_txt_block": missing_robots_block,
            "tracking_references": tracking_refs,
            "external_transaction_links_not_disabled": transaction_links_not_disabled,
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
        f"- Active or incompletely disabled forms: {len(active_forms)}",
        f"- Pages missing the browser safety guard: {len(missing_safety_guard)}",
        f"- Pages missing noindex: {len(missing_noindex)}",
        f"- Missing robots.txt site-wide block: {len(missing_robots_block)}",
        f"- Tracking references remaining: {len(tracking_refs)}",
        f"- External transaction links not disabled: {len(transaction_links_not_disabled)}",
        f"- Broken internal references detected: {len(broken_links)}",
        f"- Files at or above GitHub's practical 95 MiB guardrail: {len(oversized_files)}",
        "",
        "## Safety result",
        "",
    ]
    safety_errors = (
        active_forms
        + missing_safety_guard
        + missing_noindex
        + missing_robots_block
        + tracking_refs
        + transaction_links_not_disabled
        + oversized_files
    )
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
