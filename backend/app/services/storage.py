"""Stockage privé des fichiers, interchangeable via STORAGE_PROVIDER.

* local : système de fichiers (développement ; disque éphémère sur Render !)
* s3    : tout stockage compatible S3 (Cloudflare R2, AWS S3, Backblaze B2…) avec URL signées
* none  : téléversement désactivé, l'application reste fonctionnelle
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable

SIGNED_URL_TTL = 300


class StorageBackend(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def open(self, key: str) -> Iterator[bytes]: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str, ttl: int = SIGNED_URL_TTL) -> str | None: ...


class DisabledStorage:
    name = "none"

    def _fail(self) -> None:
        raise ServiceUnavailable(
            "Stockage de documents non configuré (STORAGE_PROVIDER). Voir docs/ENVIRONMENT.md.",
            code="storage_disabled",
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._fail()

    def open(self, key: str) -> Iterator[bytes]:
        self._fail()
        return iter(())

    def delete(self, key: str) -> None:
        return None

    def signed_url(self, key: str, filename: str, ttl: int = SIGNED_URL_TTL) -> str | None:
        self._fail()
        return None


class LocalStorage:
    name = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Clé de stockage invalide.")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def open(self, key: str) -> Iterator[bytes]:
        with self._path(key).open("rb") as fh:
            while chunk := fh.read(64 * 1024):
                yield chunk

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def signed_url(self, key: str, filename: str, ttl: int = SIGNED_URL_TTL) -> str | None:
        return None  # téléchargement via l'API authentifiée (mode « proxy »)


class S3Storage:
    name = "s3"

    def __init__(self, bucket: str, endpoint_url: str | None, region: str, access_key: str, secret_key: str):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def open(self, key: str) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        yield from body.iter_chunks(64 * 1024)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, filename: str, ttl: int = SIGNED_URL_TTL) -> str | None:
        safe = filename.replace('"', "")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentDisposition": f'attachment; filename="{safe}"'},
            ExpiresIn=ttl,
        )


@lru_cache
def get_storage() -> StorageBackend:
    s = get_settings()
    if s.storage_provider == "s3":
        if not (s.storage_bucket and s.storage_access_key and s.storage_secret_key):
            return DisabledStorage()
        return S3Storage(
            s.storage_bucket, s.storage_endpoint_url, s.storage_region, s.storage_access_key, s.storage_secret_key
        )
    if s.storage_provider == "local":
        return LocalStorage(s.storage_local_dir)
    return DisabledStorage()
