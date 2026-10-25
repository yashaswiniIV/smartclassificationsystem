import asyncio
from typing import Any

import boto3
from botocore.client import Config

from app.core.config import get_settings

settings = get_settings()

# MinIO (and R2) need SigV4 + path-style addressing. generate_presigned_url is pure
# local signing (no network), so it's safe to call directly from async handlers.
_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

# image-only uploads; map mime -> file extension
ALLOWED_MIME: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_BYTES = 8 * 1024 * 1024


def presign_put(object_key: str, content_type: str, expires: int = 900) -> str:
    return _client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presign_get(object_key: str, expires: int = 3600) -> str:
    return _client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key},
        ExpiresIn=expires,
    )


async def head(object_key: str) -> dict[str, Any]:
    """Verify an uploaded object exists; raises botocore ClientError if not."""
    return await asyncio.to_thread(_client.head_object, Bucket=settings.s3_bucket, Key=object_key)


async def get_bytes(object_key: str) -> bytes:
    """Download an object's bytes (used to feed photos to Gemini Vision)."""

    def _read() -> bytes:
        obj = _client.get_object(Bucket=settings.s3_bucket, Key=object_key)
        return obj["Body"].read()

    return await asyncio.to_thread(_read)
