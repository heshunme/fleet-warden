from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex
import shutil
import subprocess


SUPPORTED_KEYS = {"host", "hostname", "user", "port", "include"}
SYSTEM_SSH_RESOLVED_WARNING = "Resolved via system ssh."


@dataclass
class HostEntry:
    host_alias: str
    hostname: str
    user: str | None = None
    port: int = 22
    source: str = ""
    capability_warnings: list[str] = field(default_factory=list)
    resolution_method: str = "fallback_parser"
    identity_files: list[str] = field(default_factory=list)
    proxy_jump: str | None = None
    proxy_command: str | None = None


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


def _parse_ssh_g_output(stdout: str) -> dict[str, list[str]]:
    resolved: dict[str, list[str]] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, _, value = line.partition(" ")
        key = key.lower()
        resolved.setdefault(key, []).append(value.strip())
    return resolved


def _first_value(resolved: dict[str, list[str]], key: str) -> str | None:
    values = resolved.get(key)
    return values[0] if values else None


def _port_from_value(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _with_fallback_warning(entry: HostEntry, message: str) -> HostEntry:
    warnings = list(entry.capability_warnings)
    warnings.append(message)
    return HostEntry(
        host_alias=entry.host_alias,
        hostname=entry.hostname,
        user=entry.user,
        port=entry.port,
        source=entry.source,
        capability_warnings=warnings,
        resolution_method="fallback_parser",
        identity_files=list(entry.identity_files),
        proxy_jump=entry.proxy_jump,
        proxy_command=entry.proxy_command,
    )


def _resolve_host_with_system_ssh(entry: HostEntry, config_path: Path) -> HostEntry | None:
    from app.config import get_settings

    settings = get_settings()
    try:
        result = subprocess.run(
            ["ssh", "-G", "-F", str(config_path), entry.host_alias],
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.ssh_command_timeout_seconds,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    resolved = _parse_ssh_g_output(result.stdout)
    return HostEntry(
        host_alias=entry.host_alias,
        hostname=_first_value(resolved, "hostname") or entry.hostname,
        user=_first_value(resolved, "user") or entry.user,
        port=_port_from_value(_first_value(resolved, "port"), entry.port),
        source=entry.source,
        capability_warnings=[SYSTEM_SSH_RESOLVED_WARNING],
        resolution_method="system_ssh",
        identity_files=resolved.get("identityfile", []),
        proxy_jump=_first_value(resolved, "proxyjump"),
        proxy_command=_first_value(resolved, "proxycommand"),
    )


def discover_ssh_hosts_with_fallback(
    config_path: str,
    *,
    discovery_mode: str | None = None,
) -> list[HostEntry]:
    from app.config import get_settings

    parser_entries = discover_ssh_hosts(config_path)
    if discovery_mode is None:
        discovery_mode = get_settings().ssh_discovery_mode
    if discovery_mode == "parser-only":
        return parser_entries

    expanded_config_path = Path(config_path).expanduser()
    if shutil.which("ssh") is None:
        return [
            _with_fallback_warning(entry, "Fallback parser used because system ssh is unavailable.")
            for entry in parser_entries
        ]

    resolved_entries: list[HostEntry] = []
    for entry in parser_entries:
        resolved_entry = _resolve_host_with_system_ssh(entry, expanded_config_path)
        if resolved_entry is not None:
            resolved_entries.append(resolved_entry)
            continue
        resolved_entries.append(
            _with_fallback_warning(entry, "Fallback parser used because ssh -G failed.")
        )
    return resolved_entries
