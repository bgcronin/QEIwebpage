#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from common import is_in_domain, load_config, normalise_host

GUARD_SCRIPT_ID = "qei-static-mirror-safety"
GUARD_SCRIPT = r"""
(function () {
  'use strict';
  const message = 'This is a static QEI website preview. Online forms and transactions are disabled. Please use the approved live QEI service or phone 07 3239 5000.';
  document.addEventListener('submit', function (event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    window.alert(message);
  }, true);
  document.addEventListener('click', function (event) {
    const target = event.target && event.target.closest ? event.target.closest('[data-qei-disabled-transaction]') : null;
    if (target) {
      event.preventDefault();
      event.stopImmediatePropagation();
      window.alert(message);
    }
  }, true);
  const nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      const method = String((init && init.method) || 'GET').toUpperCase();
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        return Promise.reject(new Error(message));
      }
      return nativeFetch.apply(this, arguments);
    };
  }
  const nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method) {
    this.__qeiBlockedMethod = !['GET', 'HEAD', 'OPTIONS'].includes(String(method || 'GET').toUpperCase());
    return nativeOpen.apply(this, arguments);
  };
  const nativeSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    if (this.__qeiBlockedMethod) {
      this.abort();
      throw new Error(message);
    }
    return nativeSend.apply(this, arguments);
  };
  if (navigator.sendBeacon) {
    navigator.sendBeacon = function () { return false; };
  }
})();
""".strip()

LINK_ATTRIBUTES = ("href", "src", "poster", "data-src", "data-lazy-src", "data-background-image")
TRANSACTION_WORDS = ("donate", "payment", "checkout", "register", "refer-a-patient", "send-enquiry", "medical-record")


def tracking_reference(value: str, fragments: list[str]) -> bool:
    lowered = value.lower()
    return any(fragment.lower() in lowered for fragment in fragments)


def current_host_for_file(path: Path, site_root: Path, canonical_host: str) -> str:
    relative = path.relative_to(site_root)
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "_subdomains":
        return normalise_host(parts[1])
    return normalise_host(canonical_host)


def target_for_internal_url(value: str, current_file: Path, site_root: Path, current_host: str, config: dict) -> str:
    root_domain = normalise_host(config["root_domain"])
    canonical = normalise_host(config["canonical_host"])
    parsed = urlparse(value)

    target_host: str | None = None
    target_path: str | None = None
    suffix = ""
    if parsed.scheme in {"http", "https"} and is_in_domain(parsed.hostname or "", root_domain):
        target_host = normalise_host(parsed.hostname or "")
        target_path = parsed.path.lstrip("/")
        suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
    elif value.startswith("//"):
        parsed = urlparse("https:" + value)
        if is_in_domain(parsed.hostname or "", root_domain):
            target_host = normalise_host(parsed.hostname or "")
            target_path = parsed.path.lstrip("/")
            suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
    elif value.startswith("/") and not value.startswith("//"):
        target_host = current_host
        split = value.split("#", 1)
        path_query = split[0]
        fragment = "#" + split[1] if len(split) == 2 else ""
        target_path = path_query.lstrip("/")
        suffix = fragment
    else:
        # Repair paths produced by wget after host-directory promotion.
        match = re.match(r"^(?P<prefix>(?:\.\./)+)(?P<host>(?:[a-z0-9-]+\.)*qei\.org\.au)/(?P<path>.*)$", value, re.I)
        if match:
            target_host = normalise_host(match.group("host"))
            target_path = match.group("path")

    if target_host is None or target_path is None:
        return value

    if target_path == "":
        target_path = "index.html"
    if target_host in {canonical, f"www.{canonical}"}:
        destination = site_root / target_path
    else:
        destination = site_root / "_subdomains" / target_host / target_path

    relative = os.path.relpath(destination, start=current_file.parent)
    return Path(relative).as_posix() + suffix


def rewrite_srcset(value: str, current_file: Path, site_root: Path, current_host: str, config: dict) -> str:
    parts: list[str] = []
    for item in value.split(","):
        tokens = item.strip().split()
        if not tokens:
            continue
        tokens[0] = target_for_internal_url(tokens[0], current_file, site_root, current_host, config)
        parts.append(" ".join(tokens))
    return ", ".join(parts)


def process_html(path: Path, site_root: Path, config: dict) -> dict[str, int]:
    original = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(original, "lxml")
    stats = {"forms_disabled": 0, "tracking_nodes_removed": 0, "links_rewritten": 0, "transactions_disabled": 0}
    current_host = current_host_for_file(path, site_root, str(config["canonical_host"]))

    if config.get("disable_tracking"):
        fragments = [str(x) for x in config.get("tracking_host_fragments", [])]
        for tag in list(soup.find_all(["script", "iframe", "img", "link"])):
            reference = str(tag.get("src") or tag.get("href") or "")
            if reference and tracking_reference(reference, fragments):
                tag.decompose()
                stats["tracking_nodes_removed"] += 1

    head = soup.head
    if head is None:
        html = soup.html or soup.new_tag("html")
        if soup.html is None:
            soup.append(html)
        head = soup.new_tag("head")
        html.insert(0, head)

    if config.get("add_noindex"):
        robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        if robots is None:
            robots = soup.new_tag("meta")
            robots["name"] = "robots"
            head.append(robots)
        robots["content"] = "noindex,nofollow,noarchive,nosnippet"

    if config.get("disable_forms"):
        for form in soup.find_all("form"):
            original_action = str(form.get("action", ""))
            if original_action:
                form["data-original-action"] = original_action
            form["action"] = "#"
            form["method"] = "get"
            form["data-qei-static-form"] = "disabled"
            form.attrs.pop("onsubmit", None)
            for control in form.find_all(attrs={"formaction": True}):
                control["data-original-formaction"] = control.get("formaction")
                del control["formaction"]
            stats["forms_disabled"] += 1

        if soup.find("script", id=GUARD_SCRIPT_ID) is None:
            guard = soup.new_tag("script", id=GUARD_SCRIPT_ID)
            guard.string = GUARD_SCRIPT
            head.insert(0, guard)

    for tag in soup.find_all(True):
        for attribute in LINK_ATTRIBUTES:
            if not tag.has_attr(attribute):
                continue
            old = str(tag.get(attribute) or "")
            if not old or old.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            new = target_for_internal_url(old, path, site_root, current_host, config)
            if new != old:
                tag[attribute] = new
                stats["links_rewritten"] += 1
        if tag.has_attr("srcset"):
            old = str(tag.get("srcset") or "")
            new = rewrite_srcset(old, path, site_root, current_host, config)
            if new != old:
                tag["srcset"] = new
                stats["links_rewritten"] += 1

    # Mark links that could initiate a transaction or transmit sensitive information.
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        text = anchor.get_text(" ", strip=True).lower()
        lowered = href.lower() + " " + text
        if any(word in lowered for word in TRANSACTION_WORDS):
            anchor["data-qei-disabled-transaction"] = "true"
            anchor["data-original-href"] = href
            anchor["href"] = "#"
            stats["transactions_disabled"] += 1

    path.write_text(str(soup), encoding="utf-8")
    return stats


def process_css(path: Path, site_root: Path, config: dict) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    current_host = current_host_for_file(path, site_root, str(config["canonical_host"]))
    count = 0

    def replacement(match: re.Match[str]) -> str:
        nonlocal count
        quote = match.group("quote") or ""
        value = match.group("value").strip()
        new = target_for_internal_url(value, path, site_root, current_host, config)
        if new != value:
            count += 1
        return f"url({quote}{new}{quote})"

    updated = re.sub(
        r"url\(\s*(?P<quote>['\"]?)(?P<value>[^)'\"]+)(?P=quote)\s*\)",
        replacement,
        text,
        flags=re.I,
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitise and prepare the mirrored QEI static site.")
    parser.add_argument("--config", default="mirror.config.json")
    parser.add_argument("--site", default="site")
    parser.add_argument("--report", default="reports/postprocess.json")
    args = parser.parse_args()

    config = load_config(args.config)
    site_root = Path(args.site).resolve()
    totals = {
        "html_files": 0,
        "css_files": 0,
        "forms_disabled": 0,
        "tracking_nodes_removed": 0,
        "links_rewritten": 0,
        "transactions_disabled": 0,
        "css_urls_rewritten": 0,
    }

    for path in sorted(site_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".html", ".htm"}:
            stats = process_html(path, site_root, config)
            totals["html_files"] += 1
            for key, value in stats.items():
                totals[key] += value
        elif path.suffix.lower() == ".css":
            totals["css_files"] += 1
            totals["css_urls_rewritten"] += process_css(path, site_root, config)

    from common import write_json

    write_json(args.report, totals)
    print(totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
