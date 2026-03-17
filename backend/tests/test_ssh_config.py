import subprocess
from pathlib import Path

from app.infra.ssh_config import discover_ssh_hosts, discover_ssh_hosts_with_fallback


def test_discover_ssh_hosts_supports_include_and_defaults(tmp_path: Path) -> None:
    included = tmp_path / "fleet.extra"
    included.write_text(
        "\n".join(
            [
                "Host db-1",
                "  HostName 10.0.0.11",
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config"
    config.write_text(
        "\n".join(
            [
                "Host *",
                "  User ops",
                "  Port 2200",
                f"Include {included.name}",
                "Host web-1",
                "  HostName 10.0.0.10",
            ]
        ),
        encoding="utf-8",
    )

    hosts = discover_ssh_hosts(str(config))

    assert [host.host_alias for host in hosts] == ["db-1", "web-1"]
    assert hosts[0].user == "ops"
    assert hosts[0].port == 2200
    assert hosts[1].hostname == "10.0.0.10"


def test_include_keeps_active_host_block_after_include(tmp_path: Path) -> None:
    included = tmp_path / "fleet.extra"
    included.write_text(
        "\n".join(
            [
                "Host db-2",
                "  HostName 10.0.0.22",
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config"
    config.write_text(
        "\n".join(
            [
                "Host *",
                "  User ops",
                f"  Include {included.name}",
                "  Port 2222",
                "Host web-2",
                "  HostName 10.0.0.21",
            ]
        ),
        encoding="utf-8",
    )

    hosts = discover_ssh_hosts(str(config))
    by_alias = {host.host_alias: host for host in hosts}

    assert by_alias["db-2"].user == "ops"
    assert by_alias["db-2"].port == 22
    assert by_alias["web-2"].user == "ops"
    assert by_alias["web-2"].port == 2222


def test_discover_ssh_hosts_with_fallback_prefers_system_ssh(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.write_text(
        "\n".join(
            [
                "Host web-3",
                "  HostName 10.0.0.30",
                "  User ops",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("app.infra.ssh_config.shutil.which", lambda _: "/usr/bin/ssh")
    monkeypatch.setattr(
        "app.infra.ssh_config.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="\n".join(
                [
                    "hostname 203.0.113.30",
                    "user ubuntu",
                    "port 2201",
                    "identityfile ~/.ssh/id_ed25519",
                    "proxyjump bastion",
                    "proxycommand ssh -W %h:%p bastion",
                ]
            ),
            stderr="",
        ),
    )

    hosts = discover_ssh_hosts_with_fallback(str(config), discovery_mode="system-first")

    assert len(hosts) == 1
    assert hosts[0].hostname == "203.0.113.30"
    assert hosts[0].user == "ubuntu"
    assert hosts[0].port == 2201
    assert hosts[0].identity_files == ["~/.ssh/id_ed25519"]
    assert hosts[0].proxy_jump == "bastion"
    assert hosts[0].proxy_command == "ssh -W %h:%p bastion"
    assert hosts[0].resolution_method == "system_ssh"
    assert hosts[0].capability_warnings == ["Resolved via system ssh."]


def test_discover_ssh_hosts_with_fallback_drops_to_parser_per_host(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.write_text(
        "\n".join(
            [
                "Host web-4",
                "  HostName 10.0.0.40",
                "Host db-4",
                "  HostName 10.0.0.41",
            ]
        ),
        encoding="utf-8",
    )

    def fake_run(args, **kwargs):
        alias = args[-1]
        if alias == "web-4":
            return subprocess.CompletedProcess(args=args, returncode=255, stdout="", stderr="bad config")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="\n".join(["hostname 203.0.113.41", "user root", "port 2222"]),
            stderr="",
        )

    monkeypatch.setattr("app.infra.ssh_config.shutil.which", lambda _: "/usr/bin/ssh")
    monkeypatch.setattr("app.infra.ssh_config.subprocess.run", fake_run)

    hosts = discover_ssh_hosts_with_fallback(str(config), discovery_mode="system-first")
    by_alias = {host.host_alias: host for host in hosts}

    assert by_alias["web-4"].hostname == "10.0.0.40"
    assert by_alias["web-4"].resolution_method == "fallback_parser"
    assert "Fallback parser used because ssh -G failed." in by_alias["web-4"].capability_warnings
    assert by_alias["db-4"].hostname == "203.0.113.41"
    assert by_alias["db-4"].port == 2222
    assert by_alias["db-4"].resolution_method == "system_ssh"


def test_discover_ssh_hosts_with_fallback_uses_parser_when_ssh_missing(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.write_text(
        "\n".join(
            [
                "Host web-5",
                "  HostName 10.0.0.50",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("app.infra.ssh_config.shutil.which", lambda _: None)

    hosts = discover_ssh_hosts_with_fallback(str(config), discovery_mode="system-first")

    assert len(hosts) == 1
    assert hosts[0].hostname == "10.0.0.50"
    assert hosts[0].resolution_method == "fallback_parser"
    assert "Fallback parser used because system ssh is unavailable." in hosts[0].capability_warnings
