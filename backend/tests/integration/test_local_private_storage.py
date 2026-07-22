"""Offline integration coverage for the only local private storage adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import stat
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import pytest

import app.infrastructure.storage.local as local_module
from app.config import StorageConfigurationError, StorageProviderSettings
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.providers import (
    PrivateAccessMethod,
    RetentionPolicy,
    StorageProviderError,
    StorageProviderErrorCode,
)

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff\xe0"
WEBP = b"RIFF\x04\x00\x00\x00WEBP"
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$", flags=re.ASCII)


class ChunkStream:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


async def _chunks(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _settings(
    root: Path,
    *,
    maximum: int = 64,
    allowed: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"}),
) -> StorageProviderSettings:
    return StorageProviderSettings(
        private_root=root,
        max_file_size_bytes=maximum,
        allowed_content_types=allowed,
    )


def _provider(
    tmp_path: Path,
    *,
    maximum: int = 64,
    allowed: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"}),
    key_factory: object | None = None,
) -> LocalPrivateStorageProvider:
    kwargs: dict[str, object] = {
        "config": _settings(tmp_path / "private", maximum=maximum, allowed=allowed),
        "clock": lambda: NOW,
    }
    if key_factory is not None:
        kwargs["key_factory"] = key_factory
    return LocalPrivateStorageProvider(**kwargs)  # type: ignore[arg-type]


def _private_entries(root: Path) -> dict[str, list[str]]:
    return {
        name: sorted(path.name for path in (root / name).iterdir())
        for name in ("objects", "metadata", ".tmp", ".reservations")
    }


def _assert_no_transient_files(root: Path) -> None:
    entries = _private_entries(root)
    assert entries[".tmp"] == []
    assert entries[".reservations"] == []


def _assert_no_database_files(root: Path) -> None:
    assert not list(root.rglob("*.db"))
    assert not list(root.rglob("*.sqlite*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "payload"),
    [("image/png", PNG + b"ok"), ("image/jpeg", JPEG + b"ok"), ("image/webp", WEBP)],
)
async def test_allowed_small_files_are_private_and_retrievable(
    tmp_path: Path,
    content_type: str,
    payload: bytes,
) -> None:
    provider = _provider(tmp_path)

    stored = await provider.put_private(
        _chunks(payload),
        content_type=content_type,
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
    )
    access = await provider.get_private_access(stored.file_key)
    root = tmp_path / "private"

    assert stored.byte_size == len(payload)
    assert stored.created_at == NOW
    assert access.file == stored
    assert access.method is PrivateAccessMethod.APPLICATION_DOWNLOAD_ROUTE_REQUIRED
    assert (root / "objects" / stored.file_key).read_bytes() == payload
    assert not (root / "objects" / f"{stored.file_key}.png").exists()
    assert stat.S_IMODE((root / "objects" / stored.file_key).stat().st_mode) == 0o600
    assert all(
        stat.S_IMODE((root / name).stat().st_mode) == 0o700
        for name in ("objects", "metadata", ".tmp", ".reservations")
    )
    _assert_no_transient_files(root)


@pytest.mark.asyncio
async def test_zero_byte_file_is_rejected_without_residue(tmp_path: Path) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            _chunks(),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )

    assert raised.value.code is StorageProviderErrorCode.FILE_EMPTY
    assert _private_entries(tmp_path / "private") == {
        "objects": [],
        "metadata": [],
        ".tmp": [],
        ".reservations": [],
    }


@pytest.mark.asyncio
async def test_exact_size_limit_is_accepted(tmp_path: Path) -> None:
    payload = PNG + b"12345678"
    provider = _provider(tmp_path, maximum=len(payload))

    stored = await provider.put_private(
        _chunks(PNG, b"12345678"),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
    )

    assert stored.byte_size == len(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [(PNG + b"123456789",), (PNG, b"1234", b"56789")])
async def test_limit_is_enforced_before_writing_the_excess_byte(
    tmp_path: Path,
    chunks: tuple[bytes, ...],
) -> None:
    provider = _provider(tmp_path, maximum=len(PNG) + 8)

    with pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            _chunks(*chunks),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )

    assert raised.value.code is StorageProviderErrorCode.FILE_TOO_LARGE
    assert _private_entries(tmp_path / "private")["objects"] == []
    assert _private_entries(tmp_path / "private")["metadata"] == []
    _assert_no_transient_files(tmp_path / "private")


@pytest.mark.asyncio
async def test_disallowed_type_is_rejected_before_stream_consumption(tmp_path: Path) -> None:
    consumed = False

    async def stream() -> AsyncIterator[bytes]:
        nonlocal consumed
        consumed = True
        yield b"secret"

    provider = _provider(tmp_path, allowed=frozenset({"image/png"}))
    with pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            stream(),
            content_type="text/plain",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )

    assert raised.value.code is StorageProviderErrorCode.CONTENT_TYPE_NOT_ALLOWED
    assert consumed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("declared", "payload"),
    [("image/png", JPEG + b"secret"), ("image/jpeg", PNG + b"secret"), ("image/webp", PNG)],
)
async def test_declared_type_must_match_central_signature_policy(
    tmp_path: Path,
    declared: str,
    payload: bytes,
) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            _chunks(payload),
            content_type=declared,
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )

    assert raised.value.code is StorageProviderErrorCode.CONTENT_SIGNATURE_MISMATCH
    _assert_no_transient_files(tmp_path / "private")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original_filename",
    [
        "../private.png",
        "/absolute/private.png",
        "folder/private.png",
        "folder\\private.png",
        "..\u2024/private.png",
        "ＰＮＧ.png",
    ],
)
async def test_original_filename_never_affects_key_or_disk_path(
    tmp_path: Path,
    original_filename: str,
) -> None:
    provider = _provider(tmp_path)

    stored = await provider.put_private(
        _chunks(PNG),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        original_filename=original_filename,
    )

    names = [path.name for path in (tmp_path / "private").rglob("*")]
    assert KEY_PATTERN.fullmatch(stored.file_key)
    assert original_filename not in names
    assert ".png" not in stored.file_key.lower()


@pytest.mark.asyncio
async def test_random_keys_are_unique_and_opaque(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    stored = [
        await provider.put_private(
            _chunks(PNG, index.to_bytes(2, "big")),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )
        for index in range(32)
    ]
    keys = {item.file_key for item in stored}

    assert len(keys) == 32
    assert all(KEY_PATTERN.fullmatch(key) for key in keys)
    assert all("." not in key for key in keys)


@pytest.mark.asyncio
async def test_key_collision_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    collision_key = "C" * 43
    next_key = "N" * 43
    generated: Iterator[str] = iter((collision_key, next_key))
    provider = _provider(tmp_path, key_factory=generated.__next__)
    existing = tmp_path / "private" / "objects" / collision_key
    existing.write_bytes(b"existing-secret")

    stored = await provider.put_private(
        _chunks(PNG + b"new"),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
    )

    assert stored.file_key == next_key
    assert existing.read_bytes() == b"existing-secret"
    _assert_no_transient_files(tmp_path / "private")


@pytest.mark.asyncio
async def test_two_concurrent_writes_do_not_overlap(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    first_payload = PNG + b"first"
    second_payload = PNG + b"second"

    first, second = await asyncio.gather(
        provider.put_private(
            ChunkStream((PNG, b"first")),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        ),
        provider.put_private(
            ChunkStream((PNG, b"second")),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        ),
    )

    assert first.file_key != second.file_key
    root = tmp_path / "private" / "objects"
    assert (root / first.file_key).read_bytes() == first_payload
    assert (root / second.file_key).read_bytes() == second_payload


@pytest.mark.asyncio
async def test_write_exception_is_safe_and_leaves_no_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "raw-content-secret"
    original_write = local_module._write_all

    def broken_write(file_descriptor: int, content: bytes) -> NoReturn:
        os.write(file_descriptor, content[:4])
        raise RuntimeError(secret)

    monkeypatch.setattr(local_module, "_write_all", broken_write)
    provider = _provider(tmp_path)

    with pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            _chunks(PNG + secret.encode()),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
            original_filename="../private-secret.png",
        )

    monkeypatch.setattr(local_module, "_write_all", original_write)
    assert raised.value.code is StorageProviderErrorCode.WRITE_FAILED
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None
    assert secret not in str(raised.value)
    assert _private_entries(tmp_path / "private") == {
        "objects": [],
        "metadata": [],
        ".tmp": [],
        ".reservations": [],
    }


@pytest.mark.asyncio
async def test_cancelled_error_propagates_and_cleans_temporary_files(tmp_path: Path) -> None:
    provider = _provider(tmp_path)

    async def cancelled_stream() -> AsyncIterator[bytes]:
        yield PNG
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await provider.put_private(
            cancelled_stream(),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        )

    assert _private_entries(tmp_path / "private") == {
        "objects": [],
        "metadata": [],
        ".tmp": [],
        ".reservations": [],
    }


@pytest.mark.asyncio
async def test_delete_is_successful_and_repeated_delete_is_idempotent(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    stored = await provider.put_private(
        _chunks(PNG),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
    )

    first = await provider.delete(stored.file_key)
    second = await provider.delete(stored.file_key)

    assert first.deleted is True
    assert second.deleted is False
    assert first.file_key == second.file_key == stored.file_key
    assert _private_entries(tmp_path / "private")["objects"] == []
    assert _private_entries(tmp_path / "private")["metadata"] == []


@pytest.mark.asyncio
async def test_valid_missing_key_has_explicit_access_and_delete_semantics(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    missing = "M" * 43

    with pytest.raises(StorageProviderError) as raised:
        await provider.get_private_access(missing)
    deleted = await provider.delete(missing)

    assert raised.value.code is StorageProviderErrorCode.NOT_FOUND
    assert deleted.deleted is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_key",
    ["", "../" + "A" * 32, "/" + "A" * 32, "A/B" + "C" * 32, "Ａ" * 43, "A" * 129],
)
async def test_illegal_keys_are_rejected_before_filesystem_access(
    tmp_path: Path,
    file_key: str,
) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(StorageProviderError) as access_error:
        await provider.get_private_access(file_key)
    with pytest.raises(StorageProviderError) as delete_error:
        await provider.delete(file_key)

    assert access_error.value.code is StorageProviderErrorCode.INVALID_FILE_KEY
    assert delete_error.value.code is StorageProviderErrorCode.INVALID_FILE_KEY


@pytest.mark.asyncio
async def test_symbolic_link_cannot_escape_private_root(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    file_key = "S" * 43
    outside = tmp_path / "outside-secret"
    outside.write_bytes(b"must-survive")
    (tmp_path / "private" / "objects" / file_key).symlink_to(outside)

    with pytest.raises(StorageProviderError) as access_error:
        await provider.get_private_access(file_key)
    with pytest.raises(StorageProviderError) as delete_error:
        await provider.delete(file_key)

    assert access_error.value.code is StorageProviderErrorCode.CORRUPT_OBJECT
    assert delete_error.value.code is StorageProviderErrorCode.CORRUPT_OBJECT
    assert outside.read_bytes() == b"must-survive"


@pytest.mark.parametrize("name", ["public", "static"])
def test_private_root_cannot_be_inside_a_public_directory(tmp_path: Path, name: str) -> None:
    root = tmp_path / name / "private"
    with pytest.raises(StorageConfigurationError) as raised:
        LocalPrivateStorageProvider(config=_settings(root))

    assert str(root) not in str(raised.value)


def test_private_root_itself_cannot_be_a_symbolic_link(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    configured = tmp_path / "configured"
    configured.symlink_to(actual, target_is_directory=True)

    with pytest.raises(StorageConfigurationError) as raised:
        LocalPrivateStorageProvider(config=_settings(configured))

    assert str(actual) not in str(raised.value)
    assert str(configured) not in str(raised.value)


@pytest.mark.asyncio
async def test_lifecycle_metadata_is_persisted_and_expiration_is_enforced(
    tmp_path: Path,
) -> None:
    current = NOW
    expires_at = NOW + timedelta(days=30)
    provider = LocalPrivateStorageProvider(
        config=_settings(tmp_path / "private"),
        clock=lambda: current,
    )
    stored = await provider.put_private(
        _chunks(PNG + b"lifecycle"),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        expires_at=expires_at,
    )

    active = await provider.get_private_access(stored.file_key)
    current = expires_at
    expired = await provider.get_private_access(stored.file_key)

    assert active.file.created_at == NOW
    assert active.file.byte_size == len(PNG + b"lifecycle")
    assert active.file.content_type == "image/png"
    assert active.file.retention_policy is RetentionPolicy.ORIGINAL_SCREENSHOT
    assert active.file.expires_at == expires_at
    assert active.method is PrivateAccessMethod.APPLICATION_DOWNLOAD_ROUTE_REQUIRED
    assert expired.method is PrivateAccessMethod.EXPIRED


@pytest.mark.asyncio
async def test_input_container_is_not_modified_and_repeated_calls_do_not_share_state(
    tmp_path: Path,
) -> None:
    provider = _provider(tmp_path)
    chunks = (PNG, b"unchanged")
    first_input = ChunkStream(chunks)
    second_input = ChunkStream(chunks)

    first = await provider.put_private(
        first_input,
        content_type="image/png",
        retention_policy=RetentionPolicy.USER_CONTROLLED,
    )
    second = await provider.put_private(
        second_input,
        content_type="image/png",
        retention_policy=RetentionPolicy.DEMO_SESSION,
    )

    assert first_input.chunks == chunks
    assert second_input.chunks == chunks
    assert first.retention_policy is RetentionPolicy.USER_CONTROLLED
    assert second.retention_policy is RetentionPolicy.DEMO_SESSION
    assert first.file_key != second.file_key


@pytest.mark.asyncio
async def test_content_filename_and_path_never_enter_public_objects_or_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = tmp_path / "very-private-root"
    filename = "../original-private-name.png"
    content = b"raw-private-content"
    provider = LocalPrivateStorageProvider(config=_settings(root), clock=lambda: NOW)

    with caplog.at_level(logging.DEBUG), pytest.raises(StorageProviderError) as raised:
        await provider.put_private(
            _chunks(content),
            content_type="image/png",
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
            original_filename=filename,
        )

    public_text = " ".join(
        (
            str(raised.value),
            repr(raised.value),
            str(raised.value.to_public_dict()),
            repr(provider),
            repr(_settings(root)),
            caplog.text,
        )
    )
    assert content.decode() not in public_text
    assert filename not in public_text
    assert str(root) not in public_text
    assert not caplog.records


@pytest.mark.asyncio
async def test_storage_has_no_network_database_or_message_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def network_forbidden(*_: object, **__: object) -> NoReturn:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    provider = _provider(tmp_path)
    stored = await provider.put_private(
        _chunks(PNG + b"offline"),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
    )

    assert (await provider.get_private_access(stored.file_key)).file == stored
    _assert_no_database_files(tmp_path)


@pytest.mark.asyncio
async def test_all_provider_created_files_are_removed_after_delete(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    stored = await provider.put_private(
        _chunks(PNG + b"cleanup"),
        content_type="image/png",
        retention_policy=RetentionPolicy.DEMO_SESSION,
    )

    await provider.delete(stored.file_key)

    assert _private_entries(tmp_path / "private") == {
        "objects": [],
        "metadata": [],
        ".tmp": [],
        ".reservations": [],
    }
