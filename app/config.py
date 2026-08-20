"""Application configuration."""
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def generated_config_path() -> Path:
    """Return the path to the Agent 365 generated configuration."""
    return Path(
        os.environ.get("A365_GENERATED_CONFIG", "a365.generated.config.json")
    )
