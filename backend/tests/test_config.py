from app.config import DEFAULT_DATABASE_URL, Settings


def test_settings_load_values_from_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FLEETWARDEN_DATABASE_URL=sqlite:////tmp/from-env.db",
                "FLEETWARDEN_LLM_TASKSPEC_MODEL=openai/gpt-4o-mini",
                "FLEETWARDEN_LLM_PROPOSAL_MODEL=anthropic/claude-3-5-sonnet",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    settings = Settings(_env_file=env_file)

    assert settings.database_url == "sqlite:////tmp/from-env.db"
    assert settings.llm_taskspec_model == "openai/gpt-4o-mini"
    assert settings.llm_proposal_model == "anthropic/claude-3-5-sonnet"


def test_environment_variables_override_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FLEETWARDEN_DATABASE_URL=sqlite:////tmp/from-file.db\n", encoding="utf-8")
    monkeypatch.setenv("FLEETWARDEN_DATABASE_URL", "sqlite:////tmp/from-env-var.db")
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    settings = Settings(_env_file=env_file)

    assert settings.database_url == "sqlite:////tmp/from-env-var.db"


def test_settings_use_defaults_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("FLEETWARDEN_DATABASE_URL", raising=False)
    monkeypatch.delenv("FLEETWARDEN_LLM_TASKSPEC_MODEL", raising=False)
    monkeypatch.delenv("FLEETWARDEN_LLM_PROPOSAL_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.llm_taskspec_model is None
    assert settings.llm_proposal_model is None
