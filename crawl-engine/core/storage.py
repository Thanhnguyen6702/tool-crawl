"""
Storage Module — Abstraction for local filesystem and Cloudflare R2.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class LocalStorage:
    """Save files to local filesystem."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, key: str) -> Path:
        return self.base_dir / key

    async def save(self, key: str, data: bytes, metadata: dict | None = None) -> str:
        fp = self._filepath(key)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
        log.debug(f"Saved {len(data)} bytes → {fp}")
        return str(fp)

    async def exists(self, key: str) -> bool:
        return self._filepath(key).exists()

    async def delete(self, key: str) -> bool:
        fp = self._filepath(key)
        if fp.exists():
            fp.unlink()
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        results = []
        search_dir = self.base_dir / prefix if prefix else self.base_dir
        if search_dir.exists():
            for f in search_dir.rglob("*"):
                if f.is_file():
                    results.append(str(f.relative_to(self.base_dir)))
        return results


class R2Storage:
    """Save files to Cloudflare R2 (S3-compatible)."""

    def __init__(
        self,
        bucket: str,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "",
        public_url: str | None = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.public_url = public_url

        import boto3
        self.s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def _full_key(self, key: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    async def save(self, key: str, data: bytes, metadata: dict | None = None) -> str:
        full_key = self._full_key(key)
        content_type = "image/jpeg"
        if key.endswith(".png"):
            content_type = "image/png"
        elif key.endswith(".webp"):
            content_type = "image/webp"

        extra = {}
        if metadata:
            extra["Metadata"] = {k: str(v) for k, v in metadata.items()}

        self.s3.put_object(
            Bucket=self.bucket,
            Key=full_key,
            Body=data,
            ContentType=content_type,
            **extra,
        )
        log.debug(f"Uploaded {len(data)} bytes → r2://{self.bucket}/{full_key}")

        if self.public_url:
            return f"{self.public_url}/{full_key}"
        return f"r2://{self.bucket}/{full_key}"

    async def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._full_key(key))
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=self._full_key(key))
            return True
        except Exception:
            return False


def create_storage(config: dict):
    """Factory: create storage backend from config dict."""
    storage_type = config.get("type", "local")

    if storage_type == "local":
        return LocalStorage(config["path"])

    elif storage_type == "r2":
        return R2Storage(
            bucket=config["bucket"],
            account_id=config.get("account_id") or os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            access_key_id=config.get("access_key_id") or os.getenv("R2_ACCESS_KEY_ID", ""),
            secret_access_key=config.get("secret_access_key") or os.getenv("R2_SECRET_ACCESS_KEY", ""),
            prefix=config.get("prefix", ""),
            public_url=config.get("public_url"),
        )

    raise ValueError(f"Unknown storage type: {storage_type}")
