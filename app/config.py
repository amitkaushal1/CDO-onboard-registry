"""Application configuration."""
import os

from dotenv import load_dotenv

load_dotenv()


def require_graph_configuration() -> None:
    """Fail fast when the service is started without Graph provisioning."""
    if os.environ.get("A365_GRAPH_ENABLED", "false").lower() != "true":
        raise RuntimeError("A365_GRAPH_ENABLED=true is required; local mode is disabled")
    required = ("AGENT365_TENANT_ID", "A365_GRANT_CLIENT_ID", "A365_GRANT_CLIENT_SECRET")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required Graph configuration: {', '.join(missing)}")


def require_api_configuration() -> None:
    """Fail fast when API authentication keys are not configured."""
    required = ("A365_READ_API_KEY", "A365_WRITE_API_KEY")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required API authentication configuration: {', '.join(missing)}")
