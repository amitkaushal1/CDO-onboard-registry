"""API key authentication and endpoint authorization."""
import hmac
import os

from fastapi import Header, HTTPException, status


def _require_key(provided_key: str | None, configured_name: str) -> None:
    configured_key = os.environ.get(configured_name, "").strip()
    if not configured_key:
        raise RuntimeError(f"{configured_name} must be configured")
    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_read_access(x_api_key: str | None = Header(default=None)) -> None:
    """Authorize registry reads with the read key or the write key."""
    read_key = os.environ.get("A365_READ_API_KEY", "").strip()
    write_key = os.environ.get("A365_WRITE_API_KEY", "").strip()
    if not read_key and not write_key:
        raise RuntimeError("A365_READ_API_KEY or A365_WRITE_API_KEY must be configured")
    if not x_api_key or not any(
        hmac.compare_digest(x_api_key, key) for key in (read_key, write_key) if key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_write_access(x_api_key: str | None = Header(default=None)) -> None:
    """Authorize provisioning with the write key."""
    _require_key(x_api_key, "A365_WRITE_API_KEY")
