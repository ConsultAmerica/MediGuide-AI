"""Durable copies of per-record folders for serverless hosting.

Each document, imaging report and medication session keeps everything in one
local folder (``<root>/<record id>/``): the original upload, page previews,
review state, extracted lines. On a single long-running server that folder
simply persists. On serverless hosts (Vercel Functions) the filesystem is
per-instance scratch space, so the next request may land on an instance that
has never seen the folder.

With ``MEDIGUIDE_FILE_STORE=vercel-blob`` this module mirrors those folders
in a private Vercel Blob store:

* ``folder()`` — the single place modules resolve a record folder — first
  pulls the folder's current files from the store into local scratch space.
* Before the response leaves, ``persist_touched()`` (called by the API
  middleware) pushes whatever the request created, changed or deleted.

Every file version is stored under its own content-hashed pathname
(``<ns>/<id>/<relpath>~<sha12>``) and the old version is deleted after the
new one is written. Blob reads go through a CDN cache that can serve an
overwritten pathname's previous content for up to a minute, and the Python
SDK cannot bypass it; a pathname that is never overwritten can't be stale.
The store's listing (not cached) is the source of truth for which version
is current.

Without the environment variable nothing here touches the network and
``folder()`` is plain path arithmetic, so local development and tests are
unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.observability.logging import get_logger

logger = get_logger(__name__)

INDEX_NAME = ".store-index.json"
_VERSION_SEP = "~"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BlobBackend(Protocol):
    def list(self, prefix: str) -> list[tuple[str, float]]:
        """(pathname, uploaded_at epoch seconds) for every blob under prefix."""

    def get(self, pathname: str) -> bytes: ...

    def put(self, pathname: str, data: bytes) -> None: ...

    def delete(self, pathnames: list[str]) -> None: ...


class VercelBlobBackend:
    """Private Vercel Blob store via the official SDK (``vercel.blob.sync``).

    Credentials resolve the SDK's way: the request's OIDC token plus
    BLOB_STORE_ID on Vercel, or BLOB_READ_WRITE_TOKEN elsewhere.
    """

    def __init__(self) -> None:
        from vercel.blob import sync as blob  # imported only when enabled

        self._blob = blob

    def list(self, prefix: str) -> list[tuple[str, float]]:
        return [(item.pathname, item.uploaded_at.timestamp()) for item in self._blob.query_blobs(prefix=prefix)]

    def get(self, pathname: str) -> bytes:
        return self._blob.get_blob(pathname, access="private").body

    def put(self, pathname: str, data: bytes) -> None:
        self._blob.put_blob(pathname, data, access="private", allow_overwrite=True)

    def delete(self, pathnames: list[str]) -> None:
        for start in range(0, len(pathnames), 1000):
            self._blob.delete_blob(pathnames[start:start + 1000])


_backend: BlobBackend | None = None
_backend_lock = threading.Lock()


def enabled() -> bool:
    return _backend is not None or os.getenv("MEDIGUIDE_FILE_STORE", "").strip().lower() == "vercel-blob"


def set_backend(backend: BlobBackend | None) -> None:
    """Install a backend explicitly (tests), or clear it."""
    global _backend
    _backend = backend


def _get_backend() -> BlobBackend:
    global _backend
    with _backend_lock:
        if _backend is None:
            _backend = VercelBlobBackend()
        return _backend


# The SDK's synchronous API must not run on a thread with an active event
# loop, and async endpoints resolve folders on the loop thread. Blob calls
# from there run on this worker instead (blocking that request briefly).
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file-store")


def _call(fn, *args):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(*args)
    return _executor.submit(fn, *args).result()


@dataclass
class _Tracked:
    namespace: str
    record_id: str
    path: Path
    # relpath -> {"blob": pathname, "sha": content hash} as of hydration.
    index: dict[str, dict[str, str]] = field(default_factory=dict)


# Folders resolved during the current request, keyed by local path. The dict
# is created per request and shared (by reference) with the endpoint's task
# or worker thread, which run in copies of the middleware's context.
_touched: ContextVar[dict[str, _Tracked] | None] = ContextVar("file_store_touched", default=None)

_folder_locks: dict[str, threading.Lock] = {}
_folder_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _folder_locks_guard:
        return _folder_locks.setdefault(str(path), threading.Lock())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_files(path: Path) -> dict[str, Path]:
    if not path.is_dir():
        return {}
    return {
        file.relative_to(path).as_posix(): file
        for file in path.rglob("*")
        if file.is_file() and file.name != INDEX_NAME
    }


def _read_index(path: Path) -> dict[str, dict[str, str]]:
    try:
        return json.loads((path / INDEX_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_index(path: Path, index: dict[str, dict[str, str]]) -> None:
    if path.is_dir():
        (path / INDEX_NAME).write_text(json.dumps(index), encoding="utf-8")


def _split_version(relative: str) -> tuple[str, str] | None:
    if _VERSION_SEP not in relative:
        return None
    name, version = relative.rsplit(_VERSION_SEP, 1)
    return (name, version) if name else None


def _hydrate(tracked: _Tracked) -> None:
    backend = _get_backend()
    prefix = f"{tracked.namespace}/{tracked.record_id}/"
    newest: dict[str, tuple[str, float]] = {}
    for pathname, uploaded_at in _call(backend.list, prefix):
        parts = _split_version(pathname[len(prefix):])
        if parts is None:
            continue
        relative = parts[0]
        if relative not in newest or uploaded_at > newest[relative][1]:
            newest[relative] = (pathname, uploaded_at)

    index = _read_index(tracked.path)
    for relative, (pathname, _) in newest.items():
        target = tracked.path / relative
        if index.get(relative, {}).get("blob") == pathname and target.is_file():
            continue
        data = _call(backend.get, pathname)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        index[relative] = {"blob": pathname, "sha": _sha(data)}

    # Removed on another instance since this copy was taken.
    for relative in [name for name in index if name not in newest]:
        (tracked.path / relative).unlink(missing_ok=True)
        del index[relative]

    if newest:
        tracked.path.mkdir(parents=True, exist_ok=True)
    _write_index(tracked.path, index)
    tracked.index = {name: dict(entry) for name, entry in index.items()}


def folder(namespace: str, root: Path, record_id: str) -> Path:
    """The local folder for a record, brought up to date from the store
    (once per request) when durable storage is enabled."""
    path = root / record_id
    if not enabled() or not _SAFE_ID.match(record_id):
        return path

    touched = _touched.get()
    key = str(path)
    if touched is not None and key in touched:
        return path

    tracked = _Tracked(namespace=namespace, record_id=record_id, path=path)
    with _lock_for(path):
        try:
            _hydrate(tracked)
        except Exception as error:  # noqa: BLE001 — serve what is local, log the failure
            logger.error(
                "file_store_hydrate_failed",
                extra={"namespace": namespace, "error_type": type(error).__name__},
            )
            tracked.index = _read_index(path)
    if touched is not None:
        touched[key] = tracked
    return path


def _persist(tracked: _Tracked) -> None:
    backend = _get_backend()
    prefix = f"{tracked.namespace}/{tracked.record_id}/"
    index = {name: dict(entry) for name, entry in tracked.index.items()}
    stale: list[str] = []

    for relative, file in _local_files(tracked.path).items():
        data = file.read_bytes()
        digest = _sha(data)
        previous = index.get(relative)
        if previous and previous.get("sha") == digest:
            continue
        pathname = f"{prefix}{relative}{_VERSION_SEP}{digest[:12]}"
        _call(backend.put, pathname, data)
        if previous and previous.get("blob") and previous["blob"] != pathname:
            stale.append(previous["blob"])
        index[relative] = {"blob": pathname, "sha": digest}

    present = set(_local_files(tracked.path))
    for relative in [name for name in index if name not in present]:
        if index[relative].get("blob"):
            stale.append(index[relative]["blob"])
        del index[relative]

    if stale:
        _call(backend.delete, stale)
    _write_index(tracked.path, index)
    tracked.index = index


def begin_request() -> Token | None:
    return _touched.set({}) if enabled() else None


def end_request(token: Token | None) -> None:
    if token is not None:
        _touched.reset(token)


def persist_touched() -> None:
    """Push every folder this request resolved. Called before the response
    is returned: a serverless instance may be frozen right after it."""
    touched = _touched.get()
    if not touched:
        return
    for tracked in touched.values():
        with _lock_for(tracked.path):
            try:
                _persist(tracked)
            except Exception as error:  # noqa: BLE001 — logged; the local copy stays
                logger.error(
                    "file_store_persist_failed",
                    extra={"namespace": tracked.namespace, "error_type": type(error).__name__},
                )
                raise
