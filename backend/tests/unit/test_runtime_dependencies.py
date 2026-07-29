"""Runtime composition guards shared by the API and durable Worker."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.config import Settings
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.runtime_dependencies import build_runtime_storage_providers
from app.worker import __main__ as worker_main


def test_api_and_worker_use_the_one_runtime_storage_construction_entry(
    tmp_path: Path,
) -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'real.db'}",
        demo_database_url=f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}",
        storage_private_root=tmp_path / "private",
        demo_storage_private_root=tmp_path / "demo-private",
    )

    providers = build_runtime_storage_providers(settings)
    api = create_app(settings)

    assert isinstance(providers.real, LocalPrivateStorageProvider)
    assert isinstance(providers.demo, LocalPrivateStorageProvider)
    assert isinstance(api.state.storage_provider, LocalPrivateStorageProvider)
    assert isinstance(api.state.demo_storage_provider, LocalPrivateStorageProvider)
    assert "build_runtime_storage_providers(" in inspect.getsource(create_app)
    assert "build_runtime_storage_providers(" in inspect.getsource(worker_main._run)
