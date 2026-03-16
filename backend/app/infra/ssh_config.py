from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex


SUPPORTED_KEYS = {"host", "hostname", "user", "port", "include"}


@dataclass
class HostEntry:
    host_alias: str
    hostname: str
    user: str | None = None
    port: int = 22
    source: str = ""
    capability_warnings: list[str] = field(default_factory=list)


def _expand_include(value: str, current_file: Path) -> list[Path]:
    pattern = Path(value.replace("~", str(Path.home())))
    if not pattern.is_absolute():
        pattern = current_file.parent / pattern
    return list(pattern.parent.glob(pattern.name))


def _merge_defaults(base: dict[str, str], override: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    merged.update(override)
    return merged


def _parse_file(path: Path, visited: set[Path]) -> list[tuple[str, dict[str, str], str, list[str]]]:
    if path in visited or not path.exists():
        return []
    visited.add(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[str, dict[str, str], str, list[str]]] = []
    current_hosts: list[str] = []
    current_data: dict[str, str] = {}
    warnings: list[str] = []

    def flush() -> None:
        nonlocal current_hosts, current_data, warnings
        if current_hosts:
            for host in current_hosts:
                blocks.append((host, dict(current_data), str(path), list(warnings)))
        current_hosts = []
        current_data = {}
        warnings = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = shlex.split(line, comments=True)
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        value = " ".join(parts[1:])
        if key == "host":
            flush()
            current_hosts = value.split()
            continue
        if key == "include":
            for include_path in _expand_include(value, path):
                included_blocks = _parse_file(include_path, visited)
                if "*" in current_hosts and current_data:
                    merged_blocks: list[tuple[str, dict[str, str], str, list[str]]] = []
                    for host, data, source, include_warnings in included_blocks:
                        if host != "*":
                            data = _merge_defaults(current_data, data)
                        merged_blocks.append((host, data, source, include_warnings))
                    blocks.extend(merged_blocks)
                else:
                    blocks.extend(included_blocks)
            continue
        if key not in SUPPORTED_KEYS:
            warnings.append(f"Unsupported ssh config key: {parts[0]}")
            continue
        current_data[key] = value
    flush()
    return blocks


def discover_ssh_hosts(config_path: str) -> list[HostEntry]:
    visited: set[Path] = set()
    blocks = _parse_file(Path(config_path).expanduser(), visited)
    defaults: dict[str, str] = {}
    entries: list[HostEntry] = []
    for host, data, source, warnings in blocks:
        if host == "*":
            defaults = _merge_defaults(defaults, data)
            continue
        merged = _merge_defaults(defaults, data)
        hostname = merged.get("hostname", host)
        user = merged.get("user")
        try:
            port = int(merged.get("port", 22))
        except ValueError:
            port = 22
            warnings.append("Invalid port in ssh config, defaulted to 22")
        entries.append(
            HostEntry(
                host_alias=host,
                hostname=hostname,
                user=user,
                port=port,
                source=source,
                capability_warnings=warnings,
            )
        )
    return entries
