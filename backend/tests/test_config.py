"""Configuration loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

import app.config as config_module
from app.config import (
    AmapConfigurationError,
    AmapProviderSettings,
    ModelConfigurationError,
    Settings,
    StorageConfigurationError,
    StorageProviderSettings,
    load_settings,
)
from app.main import create_app
from app.storage_policy import MAX_STORAGE_MAX_FILE_SIZE_BYTES


def test_dotenv_loading_can_be_explicitly_disabled(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "APP_ENV=production\nDATABASE_URL=not-a-valid-database-url\n",
        encoding="utf-8",
    )

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_explicit_settings_override_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        app_timezone="UTC",
        database_url="sqlite+aiosqlite:///:memory:",
        log_level="WARNING",
    )

    assert settings.app_timezone == "UTC"
    assert settings.log_level == "WARNING"


def test_test_environment_skips_configured_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DATABASE_URL=not-a-valid-database-url\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "DEFAULT_ENV_FILE", dotenv_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = load_settings()

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_invalid_timezone_has_diagnostic_error() -> None:
    with pytest.raises(ValidationError, match="APP_TIMEZONE must be a valid IANA timezone"):
        Settings(
            _env_file=None,
            app_env="test",
            app_timezone="Mars/Olympus_Mons",
            database_url="sqlite+aiosqlite:///:memory:",
        )


def test_non_async_sqlite_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"must use sqlite\+aiosqlite during M0"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite:///./wrong-driver.db",
        )


def test_application_and_health_configuration_do_not_require_real_provider_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=None,
        model_api_key=None,
        model_name=None,
        model_timeout_seconds=None,
        amap_api_key=None,
    )

    app = create_app(settings)

    assert app.state.settings is settings


def test_local_private_storage_has_safe_non_secret_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )

    storage = settings.storage_provider_settings()

    assert storage.private_root == Path("data/private")
    assert storage.max_file_size_bytes == 10_000_000
    assert storage.allowed_content_types == frozenset(
        {"image/jpeg", "image/png", "image/webp"}
    )


def test_storage_configuration_is_normalized_and_hides_absolute_root(tmp_path: Path) -> None:
    private_root = tmp_path / "private-secret-root"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        storage_private_root=private_root,
        storage_max_file_size_bytes=4096,
        storage_allowed_content_types=" image/png,IMAGE/JPEG ",
    )

    storage = settings.storage_provider_settings()

    assert storage.private_root == private_root
    assert storage.max_file_size_bytes == 4096
    assert storage.allowed_content_types == frozenset({"image/jpeg", "image/png"})
    assert str(private_root) not in repr(settings)
    assert str(private_root) not in repr(storage)


@pytest.mark.parametrize(
    "maximum",
    [0, -1, MAX_STORAGE_MAX_FILE_SIZE_BYTES + 1, True],
)
def test_storage_size_limit_has_a_central_hard_boundary(maximum: object) -> None:
    with pytest.raises(StorageConfigurationError, match="STORAGE_MAX_FILE_SIZE_BYTES"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            storage_max_file_size_bytes=maximum,
        )


@pytest.mark.parametrize(
    "allowed",
    ["", "text/plain", "image/png,image/png", "image/png,text/html", ["image/png"]],
)
def test_storage_allowed_content_types_are_central_and_nonempty(allowed: object) -> None:
    with pytest.raises(StorageConfigurationError, match="STORAGE_ALLOWED_CONTENT_TYPES"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            storage_allowed_content_types=allowed,
        )


def test_direct_storage_provider_settings_revalidate_all_fields(tmp_path: Path) -> None:
    with pytest.raises(StorageConfigurationError, match="STORAGE_MAX_FILE_SIZE_BYTES"):
        StorageProviderSettings(
            private_root=tmp_path / "private",
            max_file_size_bytes=True,  # type: ignore[arg-type]
            allowed_content_types=frozenset({"image/png"}),
        )
    with pytest.raises(StorageConfigurationError, match="STORAGE_ALLOWED_CONTENT_TYPES"):
        StorageProviderSettings(
            private_root=tmp_path / "private",
            max_file_size_bytes=1024,
            allowed_content_types=frozenset({"text/plain"}),
        )


def test_complete_amap_configuration_is_deferred_and_secret_wrapped() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_timeout_seconds=8.5,
        amap_max_retries=1,
        amap_retry_after_max_seconds=2,
    )

    amap = settings.require_amap_provider()

    assert amap.base_url == "https://restapi.amap.com"
    assert isinstance(amap.api_key, SecretStr)
    assert amap.api_key.get_secret_value() == "fake-amap-key"
    assert amap.timeout_seconds == 8.5
    assert amap.max_retries == 1
    assert amap.retry_after_max_seconds == 2
    assert "fake-amap-key" not in repr(settings)
    assert "fake-amap-key" not in repr(amap)


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_missing_amap_key_is_required_only_when_real_adapter_is_requested(
    api_key: str | None,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key=api_key,
    )

    with pytest.raises(AmapConfigurationError, match="AMAP_API_KEY"):
        settings.require_amap_provider()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://restapi.amap.com",
        "https://example.com",
        "https://restapi.amap.com.evil.example",
        "https://user:password@restapi.amap.com",
        "https://restapi.amap.com:443",
        "https://restapi.amap.com:8443",
        "https://restapi.amap.com:",
        "https://restapi.amap.com:0",
        "https://restapi.amap.com/v3/place/text",
        "https://restapi.amap.com?key=unsafe",
        "https://restapi.amap.com?",
        "https://restapi.amap.com#unsafe",
        "https://restapi.amap.com#",
        "https://restapi.amap.com\n.evil.example",
        "https://restapi.amap.com\x00.evil.example",
        "https://restapi.amap.com\\@evil.example",
        "https://[broken",
        " https://restapi.amap.com",
        "not-a-url",
    ],
)
def test_invalid_amap_base_url_is_rejected_without_echoing_value(base_url: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_base_url=base_url,
    )

    with pytest.raises(AmapConfigurationError) as exc_info:
        settings.require_amap_provider()

    assert base_url not in str(exc_info.value)


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://restapi.amap.com", "https://restapi.amap.com"),
        ("https://restapi.amap.com/", "https://restapi.amap.com"),
        ("https://RESTAPI.AMAP.COM/", "https://restapi.amap.com"),
    ],
)
def test_official_amap_base_url_is_canonically_normalized(
    base_url: str,
    expected: str,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_base_url=base_url,
    )

    assert settings.require_amap_provider().base_url == expected


@pytest.mark.parametrize(
    "timeout",
    [0, 30.1, -1, float("nan"), float("inf"), "fake-timeout-secret", True],
)
def test_invalid_amap_timeout_is_rejected(timeout: object) -> None:
    with pytest.raises(AmapConfigurationError, match="AMAP_TIMEOUT_SECONDS"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_timeout_seconds=timeout,
        )


@pytest.mark.parametrize("retries", [-1, 2, 1.0, "fake-retry-secret", True])
def test_amap_retries_have_one_extra_attempt_hard_limit(retries: object) -> None:
    with pytest.raises(AmapConfigurationError, match="AMAP_MAX_RETRIES"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_max_retries=retries,
        )


@pytest.mark.parametrize(
    "cap",
    [-1, 5.1, float("nan"), float("inf"), "fake-retry-after-secret", True],
)
def test_amap_retry_after_cap_is_bounded(cap: object) -> None:
    with pytest.raises(AmapConfigurationError, match="AMAP_RETRY_AFTER_MAX_SECONDS"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_retry_after_max_seconds=cap,
        )


def direct_amap_settings(**overrides: object) -> AmapProviderSettings:
    values: dict[str, object] = {
        "api_key": SecretStr("fake-direct-amap-key"),
        "base_url": "https://restapi.amap.com",
        "timeout_seconds": 5.0,
        "max_retries": 1,
        "retry_after_max_seconds": 1.0,
        **overrides,
    }
    return AmapProviderSettings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("api_key", SecretStr("   "), "AMAP_API_KEY"),
        ("api_key", None, "AMAP_API_KEY"),
        ("api_key", "fake-unwrapped-key", "AMAP_API_KEY"),
        ("timeout_seconds", 0, "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", -1, "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", 30.1, "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", float("nan"), "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", float("inf"), "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", "1", "AMAP_TIMEOUT_SECONDS"),
        ("timeout_seconds", True, "AMAP_TIMEOUT_SECONDS"),
        ("max_retries", -1, "AMAP_MAX_RETRIES"),
        ("max_retries", 2, "AMAP_MAX_RETRIES"),
        ("max_retries", 1.0, "AMAP_MAX_RETRIES"),
        ("max_retries", "1", "AMAP_MAX_RETRIES"),
        ("max_retries", True, "AMAP_MAX_RETRIES"),
        ("retry_after_max_seconds", -1, "AMAP_RETRY_AFTER_MAX_SECONDS"),
        ("retry_after_max_seconds", 5.1, "AMAP_RETRY_AFTER_MAX_SECONDS"),
        ("retry_after_max_seconds", float("nan"), "AMAP_RETRY_AFTER_MAX_SECONDS"),
        ("retry_after_max_seconds", float("inf"), "AMAP_RETRY_AFTER_MAX_SECONDS"),
        ("retry_after_max_seconds", "1", "AMAP_RETRY_AFTER_MAX_SECONDS"),
        ("retry_after_max_seconds", True, "AMAP_RETRY_AFTER_MAX_SECONDS"),
    ],
)
def test_direct_amap_settings_reject_every_invalid_boundary_value(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(AmapConfigurationError, match=message):
        direct_amap_settings(**{field: value})


@pytest.mark.parametrize(
    ("timeout", "retries", "retry_after"),
    [(0.001, 0, 0), (30, 1, 5)],
)
def test_direct_and_settings_paths_accept_amap_boundary_values(
    timeout: float,
    retries: int,
    retry_after: float,
) -> None:
    direct = direct_amap_settings(
        timeout_seconds=timeout,
        max_retries=retries,
        retry_after_max_seconds=retry_after,
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-settings-amap-key",
        amap_timeout_seconds=timeout,
        amap_max_retries=retries,
        amap_retry_after_max_seconds=retry_after,
    ).require_amap_provider()

    assert (direct.timeout_seconds, direct.max_retries, direct.retry_after_max_seconds) == (
        timeout,
        retries,
        retry_after,
    )
    assert settings.timeout_seconds == direct.timeout_seconds
    assert settings.max_retries == direct.max_retries
    assert settings.retry_after_max_seconds == direct.retry_after_max_seconds


def test_amap_configuration_error_surface_never_exposes_key_or_invalid_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "fake-direct-secret-must-not-leak"

    with caplog.at_level("DEBUG"), pytest.raises(AmapConfigurationError) as exc_info:
        direct_amap_settings(
            api_key=SecretStr(secret),
            timeout_seconds=float("nan"),
        )

    exposed = "\n".join(
        (
            str(exc_info.value),
            repr(exc_info.value),
            repr(exc_info.value.args),
            repr(vars(exc_info.value)),
            caplog.text,
        )
    )
    assert secret not in exposed
    assert "nan" not in exposed.casefold()
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


def test_complete_model_configuration_is_returned_with_secret_type() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base="https://model.example.test/compatible-mode/v1",
        model_api_key="fake-test-key",
        model_name="configured-test-model",
        model_timeout_seconds=12.5,
    )

    model = settings.require_model_provider()

    assert model.api_base == "https://model.example.test/compatible-mode/v1"
    assert isinstance(model.api_key, SecretStr)
    assert model.api_key.get_secret_value() == "fake-test-key"
    assert model.model_name == "configured-test-model"
    assert model.timeout_seconds == 12.5


def test_missing_model_configuration_is_deferred_and_secret_safe() -> None:
    secret = "fake-key-that-must-not-leak"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=None,
        model_api_key=secret,
        model_name=" ",
        model_timeout_seconds=None,
    )

    with pytest.raises(ModelConfigurationError) as exc_info:
        settings.require_model_provider()

    error = str(exc_info.value)
    assert "MODEL_API_BASE" in error
    assert "MODEL_NAME" in error
    assert "MODEL_TIMEOUT_SECONDS" in error
    assert secret not in error


@pytest.mark.parametrize(
    "api_base",
    [
        "not-a-url",
        "ftp://model.example.test/v1",
        "https://user:password@model.example.test/v1",
        "https://model.example.test:invalid/v1",
        "https://model.example.test:0/v1",
        "https://model.example.test/v1?token=unsafe",
        "https://model.example.test/v1#fragment",
    ],
)
def test_invalid_model_api_base_is_rejected_without_echoing_value(api_base: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=api_base,
        model_api_key="fake-test-key",
        model_name="test-model",
        model_timeout_seconds=10,
    )

    with pytest.raises(ModelConfigurationError) as exc_info:
        settings.require_model_provider()

    assert api_base not in str(exc_info.value)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_model_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(
        ValidationError,
        match="MODEL_TIMEOUT_SECONDS must be a finite positive number",
    ):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            model_timeout_seconds=timeout,
        )


def test_settings_repr_masks_model_api_key() -> None:
    secret = "fake-repr-secret"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_key=secret,
    )

    rendered = repr(settings)

    assert secret not in rendered
    assert "**********" in rendered


def test_place_matching_policy_comes_from_one_server_settings_entry() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        place_match_unique_score=80,
        place_match_minimum_score_gap=15,
        place_match_candidate_score=40,
    )

    policy = settings.place_matching_policy()

    assert policy.unique_match_score == 80
    assert policy.minimum_score_gap == 15
    assert policy.candidate_score == 40


@pytest.mark.parametrize("value", [0, -1, 101, float("nan"), float("inf"), True])
@pytest.mark.parametrize(
    "field",
    [
        "place_match_unique_score",
        "place_match_minimum_score_gap",
        "place_match_candidate_score",
    ],
)
def test_invalid_place_matching_thresholds_are_rejected(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError, match="place matching thresholds"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            **{field: value},
        )


def test_candidate_threshold_cannot_exceed_unique_threshold() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            place_match_unique_score=50,
            place_match_candidate_score=50.001,
        )


@pytest.mark.parametrize(
    "environment_name",
    [
        "PLACE_MATCH_UNIQUE_SCORE",
        "PLACE_MATCH_MINIMUM_SCORE_GAP",
        "PLACE_MATCH_CANDIDATE_SCORE",
    ],
)
def test_zero_place_matching_thresholds_from_environment_are_rejected(
    environment_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(environment_name, "0")

    with pytest.raises(ValidationError, match="place matching thresholds"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
        )
