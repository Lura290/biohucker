from biohucker.config import DEFAULT_DATABASE_URL, DEFAULT_MODEL, load_settings


def test_defaults_when_env_is_empty(monkeypatch) -> None:
    monkeypatch.setattr("biohucker.config.load_dotenv", lambda: None)
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.openrouter_api_key is None
    assert settings.openrouter_model == DEFAULT_MODEL
    assert settings.database_url == DEFAULT_DATABASE_URL


def test_env_overrides_defaults(monkeypatch) -> None:
    monkeypatch.setattr("biohucker.config.load_dotenv", lambda: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "some/model")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")

    settings = load_settings()

    assert settings.openrouter_api_key == "sk-test"
    assert settings.openrouter_model == "some/model"
    assert settings.database_url == "sqlite:///tmp.db"
