from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class StoredObject:
    provider: str
    object_key: str
    canonical_url: str


class LocalObjectStorage:
    provider = "local"

    def __init__(self, root: str, public_base_url: str = ""):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/")

    def put(self, object_key: str, payload: bytes, mime_type: str) -> StoredObject:
        del mime_type
        target = self._target(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return StoredObject(self.provider, object_key, self.public_url(object_key))

    def exists(self, object_key: str) -> bool:
        return self._target(object_key).is_file()

    def open(self, object_key: str):
        return self._target(object_key).open("rb")

    def delete(self, object_key: str) -> None:
        self._target(object_key).unlink(missing_ok=True)

    def public_url(self, object_key: str) -> str:
        encoded = quote(object_key.lstrip("/"), safe="/")
        return f"{self.public_base_url}/{encoded}" if self.public_base_url else encoded

    def sign_get(self, object_key: str, expires_seconds: int) -> str:
        del expires_seconds
        return self.public_url(object_key)

    def _target(self, object_key: str) -> Path:
        target = (self.root / object_key).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("object key escapes storage root")
        return target


class InMemoryObjectStorage:
    """Unit-test fake. Runtime configuration never selects this provider."""

    provider = "memory"

    def __init__(self, public_base_url: str = "https://cdn.test.invalid"):
        self.public_base_url = public_base_url.rstrip("/")
        self.objects: dict[str, bytes] = {}

    def put(self, object_key: str, payload: bytes, mime_type: str) -> StoredObject:
        del mime_type
        if object_key in self.objects:
            raise ValueError("object already exists")
        self.objects[object_key] = payload
        return StoredObject(self.provider, object_key, self.public_url(object_key))

    def exists(self, object_key: str) -> bool:
        return object_key in self.objects

    def open(self, object_key: str):
        return BytesIO(self.objects[object_key])

    def delete(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def public_url(self, object_key: str) -> str:
        return f"{self.public_base_url}/{quote(object_key, safe='/')}"

    def sign_get(self, object_key: str, expires_seconds: int) -> str:
        del expires_seconds
        return self.public_url(object_key)


class AlibabaOssObjectStorage:
    provider = "oss"

    def __init__(
        self,
        *,
        region: str,
        bucket: str,
        endpoint: str,
        public_base_url: str,
        access_key_id: str = "",
        access_key_secret: str = "",
    ):
        import alibabacloud_oss_v2 as oss
        from alibabacloud_oss_v2.credentials import (
            EnvironmentVariableCredentialsProvider,
            StaticCredentialsProvider,
        )

        credentials = (
            StaticCredentialsProvider(access_key_id, access_key_secret)
            if access_key_id and access_key_secret
            else EnvironmentVariableCredentialsProvider()
        )
        config = oss.Config(
            region=region,
            endpoint=endpoint or None,
            signature_version="v4",
            credentials_provider=credentials,
        )
        self.oss = oss
        self.client = oss.Client(config)
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")

    def put(self, object_key: str, payload: bytes, mime_type: str) -> StoredObject:
        self.client.put_object(
            self.oss.PutObjectRequest(
                bucket=self.bucket,
                key=object_key,
                body=payload,
                content_type=mime_type,
                forbid_overwrite=True,
            )
        )
        return StoredObject(self.provider, object_key, self.public_url(object_key))

    def exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(
                self.oss.HeadObjectRequest(bucket=self.bucket, key=object_key)
            )
            return True
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return False
            raise

    def open(self, object_key: str):
        response = self.client.get_object(
            self.oss.GetObjectRequest(bucket=self.bucket, key=object_key)
        )
        body = (
            response.body.read()
            if hasattr(response.body, "read")
            else bytes(response.body)
        )
        return BytesIO(body)

    def delete(self, object_key: str) -> None:
        self.client.delete_object(
            self.oss.DeleteObjectRequest(bucket=self.bucket, key=object_key)
        )

    def public_url(self, object_key: str) -> str:
        if not self.public_base_url:
            raise ValueError("OSS_PUBLIC_BASE_URL 未配置")
        return f"{self.public_base_url}/{quote(object_key, safe='/')}"

    def sign_get(self, object_key: str, expires_seconds: int) -> str:
        result = self.client.presign(
            self.oss.GetObjectRequest(bucket=self.bucket, key=object_key),
            expires=timedelta(seconds=expires_seconds),
        )
        return result.url
