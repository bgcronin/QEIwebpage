#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from common import host_is_excluded, load_config, normalise_host, write_json


def fetch_json(url: str, user_agent: str, timeout: int) -> object:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def certificate_hosts(root_domain: str, user_agent: str, timeout: int) -> tuple[set[str], str | None]:
    url = f"https://crt.sh/?q=%25.{root_domain}&output=json"
    try:
        payload = fetch_json(url, user_agent, timeout)
    except Exception as exc:  # Network failure must not block explicit hosts.
        return set(), f"Certificate Transparency lookup failed: {exc}"

    hosts: set[str] = set()
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            for value in str(row.get("name_value", "")).splitlines():
                host = normalise_host(value)
                if host:
                    hosts.add(host)
    return hosts, None


def resolve_host(host: str) -> list[str]:
    addresses: set[str] = set()
    for item in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
        addresses.add(item[4][0])
    return sorted(addresses)


def probe_host(host: str, user_agent: str, timeout: int) -> dict[str, object]:
    result: dict[str, object] = {"host": host, "active": False, "attempts": []}
    try:
        result["addresses"] = resolve_host(host)
    except OSError as exc:
        result["reason"] = f"DNS resolution failed: {exc}"
        return result

    login_markers = (
        "webmail login",
        "cpanel login",
        "sign in to your account",
        "roundcube webmail",
        "wordpress login",
    )

    for scheme in ("https", "http"):
        url = f"{scheme}://{host}/"
        request = Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Range": "bytes=0-65535",
            },
        )
        attempt: dict[str, object] = {"url": url}
        try:
            with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
                status = int(getattr(response, "status", 200))
                content_type = response.headers.get_content_type()
                final_url = response.geturl()
                body = response.read(65536).decode("utf-8", errors="ignore").lower()
                attempt.update(status=status, content_type=content_type, final_url=final_url)
                result["attempts"].append(attempt)
                if status < 400 and content_type in {"text/html", "application/xhtml+xml"}:
                    if any(marker in body for marker in login_markers):
                        result["reason"] = "page appears to be an access or webmail login"
                        return result
                    result.update(active=True, preferred_url=final_url, reason="public HTML response")
                    return result
        except HTTPError as exc:
            attempt.update(status=exc.code, error=str(exc))
            result["attempts"].append(attempt)
            if exc.code in {401, 403}:
                result["reason"] = f"access-controlled HTTP response ({exc.code})"
                return result
        except (URLError, TimeoutError, OSError) as exc:
            attempt["error"] = str(exc)
            result["attempts"].append(attempt)

    result.setdefault("reason", "no public HTML response")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Passively discover and validate public QEI web hosts.")
    parser.add_argument("--config", default="mirror.config.json")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()

    config = load_config(args.config)
    reports = Path(args.reports)
    reports.mkdir(parents=True, exist_ok=True)
    root_domain = normalise_host(config["root_domain"])
    explicit = {normalise_host(x) for x in config.get("explicit_hosts", [])}
    candidates = set(explicit)
    warnings: list[str] = []

    if config.get("include_public_subdomains") and config.get("passive_certificate_discovery"):
        discovered, warning = certificate_hosts(
            root_domain,
            str(config["user_agent"]),
            int(config["request_timeout_seconds"]),
        )
        candidates.update(discovered)
        if warning:
            warnings.append(warning)

    included: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for host in sorted(candidates):
        blocked, reason = host_is_excluded(host, config)
        if blocked:
            excluded.append({"host": host, "reason": reason, "source": "certificate transparency"})
            continue

        probe = probe_host(host, str(config["user_agent"]), int(config["request_timeout_seconds"]))
        probe["explicit"] = host in explicit
        if probe.get("active"):
            included.append(probe)
        elif host in explicit:
            # Explicit production hosts remain crawl seeds even if a transient probe fails.
            probe["active"] = True
            probe["reason"] = f"explicit production host retained; probe result: {probe.get('reason', 'unknown')}"
            probe["preferred_url"] = f"https://{host}/"
            included.append(probe)
        else:
            excluded.append(probe)

    active_hosts = sorted({str(item["host"]) for item in included})
    (reports / "active-hosts.txt").write_text("\n".join(active_hosts) + "\n", encoding="utf-8")
    (reports / "excluded-hosts.txt").write_text(
        "\n".join(f"{item.get('host', '')}\t{item.get('reason', '')}" for item in excluded) + ("\n" if excluded else ""),
        encoding="utf-8",
    )
    write_json(
        reports / "host-discovery.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "root_domain": root_domain,
            "method": "explicit hosts plus passive Certificate Transparency; no brute force",
            "warnings": warnings,
            "included": included,
            "excluded": excluded,
        },
    )

    print(f"Active public web hosts: {len(active_hosts)}")
    for host in active_hosts:
        print(f"  {host}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
