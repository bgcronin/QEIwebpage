from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalise_host(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if value.startswith("*."):
        value = value[2:]
    return value


def is_in_domain(host: str, root_domain: str) -> bool:
    host = normalise_host(host)
    root_domain = normalise_host(root_domain)
    return host == root_domain or host.endswith("." + root_domain)


def host_is_excluded(host: str, config: dict[str, Any]) -> tuple[bool, str]:
    root_domain = normalise_host(config["root_domain"])
    host = normalise_host(host)
    if not is_in_domain(host, root_domain):
        return True, "outside root domain"
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        return True, "invalid hostname characters"
    labels = host[: -(len(root_domain) + 1)].split(".") if host != root_domain else []
    excluded = {str(x).lower() for x in config.get("excluded_host_labels", [])}
    for label in labels:
        if label in excluded:
            return True, f"excluded host label: {label}"
    return False, ""


def url_is_in_scope(url: str, hosts: set[str], config: dict[str, Any]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = normalise_host(parsed.hostname or "")
    if host not in hosts:
        return False
    path = parsed.path or "/"
    return not any(pattern.lower() in path.lower() for pattern in config.get("excluded_path_patterns", []))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, data: Any) -> None:
    output = Path(path)
    ensure_parent(output)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
