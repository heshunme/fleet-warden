from pathlib import Path

from app.infra.ssh_config import discover_ssh_hosts


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
