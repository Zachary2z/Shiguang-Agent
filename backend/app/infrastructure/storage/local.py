"""Filesystem-backed private storage with atomic, exclusive publication."""

from __future__ import annotations

import asyncio
import os
import secrets
import stat
from collections.abc import AsyncIterable, Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from app.config import Settings, StorageConfigurationError, StorageProviderSettings
from app.providers.storage import (
    PrivateAccessMethod,
    PrivateFileAccess,
    PrivateFileDeleteResult,
    PrivateFileMetadata,
    RetentionPolicy,
    StorageProvider,
    StorageProviderError,
    StorageProviderErrorCode,
    validate_storage_file_key,
)
from app.storage_policy import STORAGE_SIGNATURE_PROBE_BYTES, content_signature_matches

_DIRECTORY_MODE: Final = 0o700
_FILE_MODE: Final = 0o600
_MAX_KEY_ATTEMPTS: Final = 16
_MAX_METADATA_BYTES: Final = 4096
_DIRECTORY_FLAGS: Final = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
    os, "O_NOFOLLOW", 0
)
_CREATE_FLAGS: Final = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
)
_READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class LocalPrivateStorageProvider(StorageProvider):
    """The only local private-directory adapter; it never returns filesystem paths."""

    def __init__(
        self,
        *,
        config: StorageProviderSettings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        key_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        self._root = _prepare_private_root(config.private_root)
        self._objects = _prepare_child_directory(self._root, "objects")
        self._metadata = _prepare_child_directory(self._root, "metadata")
        self._temporary = _prepare_child_directory(self._root, ".tmp")
        self._reservations = _prepare_child_directory(self._root, ".reservations")
        self._max_file_size_bytes = config.max_file_size_bytes
        self._allowed_content_types = config.allowed_content_types
        self._clock = clock
        self._key_factory = key_factory

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        key_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> LocalPrivateStorageProvider:
        return cls(
            config=settings.storage_provider_settings(),
            clock=clock,
            key_factory=key_factory,
        )

    async def put_private(
        self,
        file: AsyncIterable[bytes],
        *,
        content_type: str,
        retention_policy: RetentionPolicy,
        expires_at: datetime | None = None,
        original_filename: str | None = None,
    ) -> PrivateFileMetadata:
        del original_filename  # Explicitly untrusted and never persisted, logged, or inspected.
        if not isinstance(retention_policy, RetentionPolicy):
            raise StorageProviderError(code=StorageProviderErrorCode.INVALID_REQUEST)
        if not isinstance(content_type, str) or content_type not in self._allowed_content_types:
            raise StorageProviderError(
                code=StorageProviderErrorCode.CONTENT_TYPE_NOT_ALLOWED
            )
        created_at = _safe_clock_value(self._clock)
        normalized_expiration = _normalize_expiration(expires_at, created_at=created_at)
        file_key, reservation_name = self._reserve_file_key()
        data_temp_name = _new_temporary_name()
        metadata_temp_name = _new_temporary_name()
        data_published = False
        metadata_published = False
        public_error: StorageProviderError | None = None
        unexpected_failure = False
        stored_metadata: PrivateFileMetadata | None = None

        try:
            byte_size, digest, signature_prefix = await self._write_stream(
                file,
                temporary_name=data_temp_name,
            )
            if byte_size == 0:
                raise StorageProviderError(code=StorageProviderErrorCode.FILE_EMPTY)
            if not content_signature_matches(
                content_type=content_type,
                prefix=signature_prefix,
            ):
                raise StorageProviderError(
                    code=StorageProviderErrorCode.CONTENT_SIGNATURE_MISMATCH
                )
            stored_metadata = PrivateFileMetadata(
                file_key=file_key,
                created_at=created_at,
                byte_size=byte_size,
                content_type=content_type,
                retention_policy=retention_policy,
                expires_at=normalized_expiration,
                content_sha256=digest,
            )
            self._write_metadata_temp(
                metadata_temp_name,
                metadata=stored_metadata,
            )
            self._publish_temp(
                data_temp_name,
                destination_name=file_key,
                destination_directory=self._objects,
            )
            data_published = True
            self._publish_temp(
                metadata_temp_name,
                destination_name=file_key,
                destination_directory=self._metadata,
            )
            metadata_published = True
        except asyncio.CancelledError:
            raise
        except StorageProviderError as error:
            public_error = error
        except Exception:
            unexpected_failure = True
        finally:
            if not metadata_published and data_published:
                _safe_unlink(self._objects, file_key)
            _safe_unlink(self._temporary, data_temp_name)
            _safe_unlink(self._temporary, metadata_temp_name)
            _safe_unlink(self._reservations, reservation_name)

        if public_error is not None:
            raise public_error
        if unexpected_failure:
            raise StorageProviderError(code=StorageProviderErrorCode.WRITE_FAILED)
        assert stored_metadata is not None and data_published and metadata_published
        return stored_metadata

    async def get_private_access(self, file_key: str) -> PrivateFileAccess:
        validate_storage_file_key(file_key)
        metadata: PrivateFileMetadata | None = None
        not_found = False
        corrupt = False
        try:
            object_stat = _safe_regular_file_stat(self._objects, file_key)
            metadata_stat = _safe_regular_file_stat(self._metadata, file_key)
            if object_stat is None and metadata_stat is None:
                not_found = True
            elif object_stat is None or metadata_stat is None:
                corrupt = True
            else:
                raw_metadata = _read_small_file(self._metadata, file_key)
                metadata = PrivateFileMetadata.model_validate_json(raw_metadata, strict=True)
                corrupt = (
                    metadata.file_key != file_key
                    or metadata.byte_size != object_stat.st_size
                )
        except StorageProviderError:
            raise
        except (OSError, ValidationError, ValueError, TypeError):
            corrupt = True
        if not_found:
            raise StorageProviderError(code=StorageProviderErrorCode.NOT_FOUND)
        if corrupt or metadata is None:
            raise StorageProviderError(code=StorageProviderErrorCode.CORRUPT_OBJECT)
        now = _safe_clock_value(self._clock)
        method = (
            PrivateAccessMethod.EXPIRED
            if metadata.expires_at is not None and metadata.expires_at <= now
            else PrivateAccessMethod.APPLICATION_DOWNLOAD_ROUTE_REQUIRED
        )
        return PrivateFileAccess(file=metadata, method=method)

    async def delete(self, file_key: str) -> PrivateFileDeleteResult:
        validate_storage_file_key(file_key)
        delete_failed = False
        existed = False
        try:
            object_stat = _safe_regular_file_stat(self._objects, file_key)
            metadata_stat = _safe_regular_file_stat(self._metadata, file_key)
            if object_stat is None and metadata_stat is None:
                return PrivateFileDeleteResult(file_key=file_key, deleted=False)
            existed = True
            if metadata_stat is not None:
                _unlink_name(self._metadata, file_key)
            if object_stat is not None:
                _unlink_name(self._objects, file_key)
        except StorageProviderError:
            raise
        except OSError:
            delete_failed = True
        if delete_failed:
            raise StorageProviderError(code=StorageProviderErrorCode.DELETE_FAILED)
        return PrivateFileDeleteResult(file_key=file_key, deleted=existed)

    def _reserve_file_key(self) -> tuple[str, str]:
        reservations_fd = -1
        objects_fd = -1
        metadata_fd = -1
        reservation: tuple[str, str] | None = None
        public_error: StorageProviderError | None = None
        unexpected_failure = False
        try:
            reservations_fd = _open_directory(self._reservations)
            objects_fd = _open_directory(self._objects)
            metadata_fd = _open_directory(self._metadata)
            for _ in range(_MAX_KEY_ATTEMPTS):
                file_key = self._key_factory()
                validate_storage_file_key(file_key)
                try:
                    reservation_fd = os.open(
                        file_key,
                        _CREATE_FLAGS,
                        _FILE_MODE,
                        dir_fd=reservations_fd,
                    )
                except FileExistsError:
                    continue
                os.close(reservation_fd)
                if _name_exists(objects_fd, file_key) or _name_exists(metadata_fd, file_key):
                    os.unlink(file_key, dir_fd=reservations_fd)
                    continue
                reservation = (file_key, file_key)
                break
        except StorageProviderError as error:
            public_error = error
        except Exception:
            unexpected_failure = True
        finally:
            for descriptor in (reservations_fd, objects_fd, metadata_fd):
                if descriptor >= 0:
                    os.close(descriptor)
        if public_error is not None:
            raise public_error
        if unexpected_failure or reservation is None:
            raise StorageProviderError(code=StorageProviderErrorCode.WRITE_FAILED)
        return reservation

    async def _write_stream(
        self,
        file: AsyncIterable[bytes],
        *,
        temporary_name: str,
    ) -> tuple[int, str, bytes]:
        temporary_fd = _open_directory(self._temporary)
        output_fd = -1
        byte_size = 0
        digest = sha256()
        signature_prefix = bytearray()
        try:
            output_fd = os.open(
                temporary_name,
                _CREATE_FLAGS,
                _FILE_MODE,
                dir_fd=temporary_fd,
            )
            async for chunk in file:
                if not isinstance(chunk, bytes):
                    raise StorageProviderError(
                        code=StorageProviderErrorCode.INVALID_REQUEST
                    )
                if byte_size + len(chunk) > self._max_file_size_bytes:
                    raise StorageProviderError(
                        code=StorageProviderErrorCode.FILE_TOO_LARGE
                    )
                if not chunk:
                    continue
                if len(signature_prefix) < STORAGE_SIGNATURE_PROBE_BYTES:
                    needed = STORAGE_SIGNATURE_PROBE_BYTES - len(signature_prefix)
                    signature_prefix.extend(chunk[:needed])
                _write_all(output_fd, chunk)
                digest.update(chunk)
                byte_size += len(chunk)
            os.fsync(output_fd)
        finally:
            if output_fd >= 0:
                os.close(output_fd)
            os.close(temporary_fd)
        return byte_size, digest.hexdigest(), bytes(signature_prefix)

    def _write_metadata_temp(
        self,
        temporary_name: str,
        *,
        metadata: PrivateFileMetadata,
    ) -> None:
        payload = metadata.model_dump_json().encode("utf-8")
        temporary_fd = _open_directory(self._temporary)
        output_fd = -1
        try:
            output_fd = os.open(
                temporary_name,
                _CREATE_FLAGS,
                _FILE_MODE,
                dir_fd=temporary_fd,
            )
            _write_all(output_fd, payload)
            os.fsync(output_fd)
        finally:
            if output_fd >= 0:
                os.close(output_fd)
            os.close(temporary_fd)

    def _publish_temp(
        self,
        temporary_name: str,
        *,
        destination_name: str,
        destination_directory: Path,
    ) -> None:
        source_fd = _open_directory(self._temporary)
        destination_fd = _open_directory(destination_directory)
        try:
            os.link(
                temporary_name,
                destination_name,
                src_dir_fd=source_fd,
                dst_dir_fd=destination_fd,
                follow_symlinks=False,
            )
            os.fsync(destination_fd)
        finally:
            os.close(source_fd)
            os.close(destination_fd)


def _prepare_private_root(configured_root: Path) -> Path:
    prepared: Path | None = None
    unavailable = False
    try:
        candidate = (
            configured_root
            if configured_root.is_absolute()
            else Path.cwd() / configured_root
        )
        if any(part.casefold() in {"public", "static"} for part in candidate.parts):
            raise StorageConfigurationError("private storage root is unsafe")
        if candidate.is_symlink():
            raise StorageConfigurationError("private storage root is unsafe")
        candidate.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
        if candidate.is_symlink() or not candidate.is_dir():
            raise StorageConfigurationError("private storage root is unsafe")
        os.chmod(candidate, _DIRECTORY_MODE)
        prepared = candidate.resolve(strict=True)
    except StorageConfigurationError:
        raise
    except OSError:
        unavailable = True
    if unavailable or prepared is None:
        raise StorageConfigurationError("private storage root is unavailable")
    return prepared


def _prepare_child_directory(root: Path, name: str) -> Path:
    path = root / name
    prepared = False
    try:
        if path.is_symlink():
            raise StorageConfigurationError("private storage directory is unsafe")
        path.mkdir(mode=_DIRECTORY_MODE, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise StorageConfigurationError("private storage directory is unsafe")
        os.chmod(path, _DIRECTORY_MODE)
        prepared = True
    except StorageConfigurationError:
        raise
    except OSError:
        prepared = False
    if not prepared:
        raise StorageConfigurationError("private storage directory is unavailable")
    return path


def _open_directory(path: Path) -> int:
    descriptor = -1
    directory_stat: os.stat_result | None = None
    try:
        descriptor = os.open(path, _DIRECTORY_FLAGS)
        directory_stat = os.fstat(descriptor)
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
    if descriptor < 0 or directory_stat is None:
        raise StorageProviderError(code=StorageProviderErrorCode.CORRUPT_OBJECT)
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_IMODE(directory_stat.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise StorageProviderError(code=StorageProviderErrorCode.CORRUPT_OBJECT)
    return descriptor


def _new_temporary_name() -> str:
    return f"tmp_{secrets.token_urlsafe(24)}"


def _safe_clock_value(clock: Callable[[], datetime]) -> datetime:
    normalized: datetime | None = None
    try:
        value = clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        normalized = value.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        pass
    if normalized is None:
        raise StorageProviderError(code=StorageProviderErrorCode.INVALID_REQUEST)
    return normalized


def _normalize_expiration(
    expires_at: datetime | None,
    *,
    created_at: datetime,
) -> datetime | None:
    if expires_at is None:
        return None
    normalized: datetime | None = None
    try:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError
        normalized = expires_at.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        pass
    if normalized is None or normalized <= created_at:
        raise StorageProviderError(code=StorageProviderErrorCode.INVALID_REQUEST)
    return normalized


def _write_all(file_descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(file_descriptor, view)
        if written <= 0:
            raise OSError
        view = view[written:]


def _name_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _safe_unlink(directory: Path, name: str) -> None:
    directory_fd = -1
    try:
        directory_fd = os.open(directory, _DIRECTORY_FLAGS)
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        pass
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)


def _unlink_name(directory: Path, name: str) -> None:
    directory_fd = _open_directory(directory)
    try:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(directory_fd)


def _safe_regular_file_stat(directory: Path, name: str) -> os.stat_result | None:
    directory_fd = _open_directory(directory)
    try:
        try:
            result = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(result.st_mode):
            raise StorageProviderError(code=StorageProviderErrorCode.CORRUPT_OBJECT)
        if stat.S_IMODE(result.st_mode) & 0o077:
            raise StorageProviderError(code=StorageProviderErrorCode.CORRUPT_OBJECT)
        return result
    finally:
        os.close(directory_fd)


def _read_small_file(directory: Path, name: str) -> bytes:
    directory_fd = _open_directory(directory)
    file_descriptor = -1
    try:
        file_descriptor = os.open(name, _READ_FLAGS, dir_fd=directory_fd)
        payload = os.read(file_descriptor, _MAX_METADATA_BYTES + 1)
        if len(payload) > _MAX_METADATA_BYTES:
            raise ValueError
        return payload
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        os.close(directory_fd)
