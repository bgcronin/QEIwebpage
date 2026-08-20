#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from common import is_in_domain, load_config, normalise_host, write_json

GUARD_SCRIPT_ID = "qei-static-mirror-safety"
GUARD_STYLE_ID = "qei-static-mirror-safety-style"
GUARD_MESSAGE = (
    "This is a static QEI website preview. Online forms and transactions are disabled. "
    "Please use the approved live QEI service or phone 07 3239 5000."
)
GUARD_SCRIPT = rf"""
(function () {{
  'use strict';
  const message = {GUARD_MESSAGE!r};
  const safeMethods = ['GET', 'HEAD', 'OPTIONS'];
  const block = function (event) {{
    if (event) {{
      event.preventDefault();
      event.stopImmediatePropagation();
    }}
    window.alert(message);
    return false;
  }};

  document.addEventListener('submit', block, true);
  document.addEventListener('click', function (event) {{
    const target = event.target && event.target.closest
      ? event.target.closest('[data-qei-disabled-transaction]')
      : null;
    if (target) block(event);
  }}, true);

  if (window.HTMLFormElement) {{
    HTMLFormElement.prototype.submit = function () {{ return block(); }};
    if (HTMLFormElement.prototype.requestSubmit) {{
      HTMLFormElement.prototype.requestSubmit = function () {{ return block(); }};
    }}
  }}

  const nativeFetch = window.fetch;
  if (nativeFetch) {{
    window.fetch = function (input, init) {{
      const requestMethod = input && typeof input === 'object' && input.method ? input.method : 'GET';
      const method = String((init && init.method) || requestMethod || 'GET').toUpperCase();
      if (!safeMethods.includes(method)) {{
        return Promise.reject(new Error(message));
      }}
      return nativeFetch.apply(this, arguments);
    }};
  }}

  if (window.XMLHttpRequest) {{
    const nativeOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method) {{
      this.__qeiBlockedMethod = !safeMethods.includes(String(method || 'GET').toUpperCase());
      return nativeOpen.apply(this, arguments);
    }};
    const nativeSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {{
      if (this.__qeiBlockedMethod) {{
        this.abort();
        throw new Error(message);
      }}
      return nativeSend.apply(this, arguments);
    }};
  }}

  if (navigator.sendBeacon) {{
    navigator.sendBeacon = function () {{ return false; }};
  }}
}})();
""".strip()

GUARD_STYLE = """
.qei-static-form-notice {
  box-sizing: border-box;
  margin: 0 0 1rem;
  padding: .8rem 1rem;
  border: 1px solid #8a99a8;
  border-radius: 4px;
  background: #f2f5f7;
  color: #18222d;
  font: 600 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
form[data-qei-static-form="disabled"] :disabled {
  opacity: 1;
}
form[data-qei-static-form="disabled"] button,
form[data-qei-static-form="disabled"] input,
form[data-qei-static-form="disabled"] select,
form[data-qei-static-form="disabled"] textarea {
  cursor: not-allowed;
}
""".strip()

LINK_ATTRIBUTES = ("href", "src", "poster", "data-src", "data-lazy-src", "data-background-image")
DEFAULT_TRANSACTION_WORDS = (
    "donate",
    "donation",
    "payment",
    "checkout",
    "register",
    "registration",
    "refer-a-patient",
    "refer a patient",
    "send-enquiry",
    "send enquiry",
    "medical-record",
    "medical record",
    "book appointment",
    "book laser",
    "appointment booking",
)
INLINE_TRACKING_PATTERNS = (
    "googletagmanager",
    "google-analytics",
    "gtag(",
    "fbq(",
    "connect.facebook.net",
    "hotjar(",
    "clarity(",
    "doubleclick.net",
)


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
        escaped_root = re.escape(root_domain)
        match = re.match(
            rf"^(?P<prefix>(?:\.\./)+)(?P<host>(?:[a-z0-9-]+\.)*{escaped_root})/(?P<path>.*)$",
            value,
            re.I,
        )
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
    if value.strip().lower().startswith("data:"):
        return value
    parts: list[str] = []
    for item in value.split(","):
        tokens = item.strip().split()
        if not tokens:
            continue
        tokens[0] = target_for_internal_url(tokens[0], current_file, site_root, current_host, config)
        parts.append(" ".join(tokens))
    return ", ".join(parts)


def link_is_external_transaction(href: str, text: str, config: dict) -> bool:
    if not config.get("disable_external_transactions", True):
        return False
    value = href.strip()
    if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return False

    parsed = urlparse("https:" + value if value.startswith("//") else value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    root_domain = normalise_host(config["root_domain"])
    if is_in_domain(parsed.hostname, root_domain):
        return False

    lowered = (value + " " + text).lower()
    words = [str(x).lower() for x in config.get("transaction_words", DEFAULT_TRANSACTION_WORDS)]
    host_fragments = [str(x).lower() for x in config.get("transaction_host_fragments", [])]
    return any(word in lowered for word in words) or any(fragment in parsed.hostname.lower() for fragment in host_fragments)


def disable_form(form: Tag, soup: BeautifulSoup) -> None:
    original_action = str(form.get("action", ""))
    original_method = str(form.get("method", "get"))
    if original_action and not form.has_attr("data-original-action"):
        form["data-original-action"] = original_action
    if not form.has_attr("data-original-method"):
        form["data-original-method"] = original_method
    form["action"] = "#"
    form["method"] = "get"
    form["onsubmit"] = "return false"
    form["novalidate"] = "novalidate"
    form["autocomplete"] = "off"
    form["data-qei-static-form"] = "disabled"
    form["aria-disabled"] = "true"

    for control in form.find_all(["input", "textarea", "select", "button"]):
        if control.has_attr("name"):
            control["data-original-name"] = str(control.get("name"))
            del control["name"]
        if control.has_attr("formaction"):
            control["data-original-formaction"] = str(control.get("formaction"))
            del control["formaction"]
        if control.name == "button" or (control.name == "input" and str(control.get("type", "")).lower() in {"submit", "image"}):
            control["type"] = "button"
        if control.name == "input" and str(control.get("type", "")).lower() in {"hidden", "password", "file"}:
            control["value"] = ""
        control["disabled"] = "disabled"
        control["aria-disabled"] = "true"
        control["tabindex"] = "-1"

    previous = form.previous_sibling
    while previous is not None and not isinstance(previous, Tag):
        previous = previous.previous_sibling
    if not (isinstance(previous, Tag) and "qei-static-form-notice" in (previous.get("class") or [])):
        notice = soup.new_tag("div")
        notice["class"] = ["qei-static-form-notice"]
        notice["role"] = "note"
        notice.string = GUARD_MESSAGE
        form.insert_before(notice)


def process_html(path: Path, site_root: Path, config: dict) -> dict[str, int]:
    original = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(original, "lxml")
    stats = {
        "forms_disabled": 0,
        "form_controls_disabled": 0,
        "tracking_nodes_removed": 0,
        "links_rewritten": 0,
        "transactions_disabled": 0,
    }
    current_host = current_host_for_file(path, site_root, str(config["canonical_host"]))

    if config.get("disable_tracking"):
        fragments = [str(x) for x in config.get("tracking_host_fragments", [])]
        for tag in list(soup.find_all(["script", "iframe", "img", "link", "noscript"])):
            reference = str(tag.get("src") or tag.get("href") or "")
            inline = tag.get_text(" ", strip=False) if tag.name in {"script", "noscript"} else ""
            if (reference and tracking_reference(reference, fragments)) or (
                inline and any(pattern in inline.lower() for pattern in INLINE_TRACKING_PATTERNS)
            ):
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

    # Disable direct links to external payment, donation, appointment, referral,
    # or registration processors while preserving navigation to mirrored QEI pages.
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        text = anchor.get_text(" ", strip=True)
        if link_is_external_transaction(href, text, config):
            anchor["data-qei-disabled-transaction"] = "true"
            anchor["data-original-href"] = href
            anchor["href"] = "#"
            stats["transactions_disabled"] += 1

    if config.get("disable_forms"):
        for form in soup.find_all("form"):
            controls = len(form.find_all(["input", "textarea", "select", "button"]))
            disable_form(form, soup)
            stats["forms_disabled"] += 1
            stats["form_controls_disabled"] += controls

        style = soup.find("style", id=GUARD_STYLE_ID)
        if style is None:
            style = soup.new_tag("style", id=GUARD_STYLE_ID)
            head.insert(0, style)
        style.string = GUARD_STYLE

        guard = soup.find("script", id=GUARD_SCRIPT_ID)
        if guard is None:
            guard = soup.new_tag("script", id=GUARD_SCRIPT_ID)
            head.insert(0, guard)
        guard.string = GUARD_SCRIPT

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
        "form_controls_disabled": 0,
        "tracking_nodes_removed": 0,
        "links_rewritten": 0,
        "transactions_disabled": 0,
        "css_urls_rewritten": 0,
        "robots_txt_written": 0,
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

    if config.get("add_noindex"):
        (site_root / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        totals["robots_txt_written"] = 1

    write_json(args.report, totals)
    print(totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
