#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import ssl
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from common import load_config, normalise_host, url_is_in_scope, write_json


def fetch_bytes(url: str, user_agent: str, timeout: int, limit: int = 20_000_000) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"response exceeded {limit} bytes")
        if data[:2] == b"\x1f\x8b" or response.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)
        return data, response.geturl()


def ensure_final_url_in_scope(final_url: str, hosts: set[str], config: dict) -> None:
    if not url_is_in_scope(final_url, hosts, config):
        final_host = normalise_host(urlparse(final_url).hostname or "")
        raise ValueError(f"redirect destination is outside active public hosts: {final_host or final_url}")


def robots_sitemaps(
    host: str,
    hosts: set[str],
    config: dict,
    user_agent: str,
    timeout: int,
) -> tuple[list[str], str | None]:
    url = f"https://{host}/robots.txt"
    try:
        payload, final_url = fetch_bytes(url, user_agent, timeout, limit=1_000_000)
        ensure_final_url_in_scope(final_url, hosts, config)
    except Exception as exc:
        return [], str(exc)
    sitemaps: list[str] = []
    for raw_line in payload.decode("utf-8", errors="replace").splitlines():
        if raw_line.lower().startswith("sitemap:"):
            candidate = raw_line.split(":", 1)[1].strip()
            if candidate:
                resolved = urljoin(final_url, candidate)
                if url_is_in_scope(resolved, hosts, config):
                    sitemaps.append(resolved)
    return sitemaps, None


def parse_sitemap(data: bytes) -> tuple[str, list[str]]:
    root = ElementTree.fromstring(data)
    local_name = root.tag.rsplit("}", 1)[-1].lower()
    locations: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text:
            locations.append(element.text.strip())
    return local_name, locations


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover QEI page URLs from robots and XML sitemaps.")
    parser.add_argument("--config", default="mirror.config.json")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()

    config = load_config(args.config)
    reports = Path(args.reports)
    hosts_file = reports / "active-hosts.txt"
    if not hosts_file.exists():
        raise SystemExit("Run scripts/discover_hosts.py first.")
    hosts = {normalise_host(line) for line in hosts_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    user_agent = str(config["user_agent"])
    timeout = int(config["request_timeout_seconds"])
    max_urls = int(config.get("max_sitemap_urls", 25000))

    page_urls: set[str] = {f"https://{host}/" for host in hosts}
    sitemap_queue: deque[str] = deque()
    attempted: set[str] = set()
    report_hosts: dict[str, object] = {}

    for host in sorted(hosts):
        discovered, robots_error = robots_sitemaps(host, hosts, config, user_agent, timeout)
        candidates = discovered + [
            f"https://{host}/wp-sitemap.xml",
            f"https://{host}/sitemap_index.xml",
            f"https://{host}/sitemap.xml",
        ]
        for candidate in candidates:
            if url_is_in_scope(candidate, hosts, config) and candidate not in attempted:
                sitemap_queue.append(candidate)
        report_hosts[host] = {"robots_error": robots_error, "candidate_sitemaps": candidates}

    sitemap_results: list[dict[str, object]] = []
    while sitemap_queue and len(page_urls) < max_urls:
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in attempted:
            continue
        attempted.add(sitemap_url)
        parsed_host = normalise_host(urlparse(sitemap_url).hostname or "")
        if parsed_host not in hosts:
            continue
        result: dict[str, object] = {"url": sitemap_url}
        try:
            payload, final_url = fetch_bytes(sitemap_url, user_agent, timeout)
            ensure_final_url_in_scope(final_url, hosts, config)
            kind, locations = parse_sitemap(payload)
            result.update(status="ok", final_url=final_url, type=kind, locations=len(locations))
            if kind == "sitemapindex":
                for location in locations:
                    if url_is_in_scope(location, hosts, config) and location not in attempted:
                        sitemap_queue.append(location)
            else:
                for location in locations:
                    if url_is_in_scope(location, hosts, config):
                        page_urls.add(location)
                        if len(page_urls) >= max_urls:
                            break
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, ElementTree.ParseError) as exc:
            result.update(status="error", error=str(exc))
        sitemap_results.append(result)

    sorted_urls = sorted(page_urls)
    (reports / "seed-urls.txt").write_text("\n".join(sorted_urls) + "\n", encoding="utf-8")
    write_json(
        reports / "url-discovery.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hosts": report_hosts,
            "sitemaps": sitemap_results,
            "seed_url_count": len(sorted_urls),
            "maximum": max_urls,
        },
    )
    print(f"Seed URLs: {len(sorted_urls)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
