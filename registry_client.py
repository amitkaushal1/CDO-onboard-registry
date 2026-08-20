# registry_client.py
"""Read the Agent 365 CLI-generated blueprint configuration."""
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

class AgentRegistration(BaseModel):
    display_name: str
    sponsor_user_id: str
    owner_user_id: str | None = None


FIXED_AGENT_TEMPLATE = AgentRegistration(
    display_name="claims-support-agent",
    sponsor_user_id="sponsor-user-object-id",
    owner_user_id="owner-user-object-id",
)


class AgentRegistryClient:
    def __init__(self, generated_config_path: Path):
        self.generated_config_path = generated_config_path

    async def register_agent(self) -> dict[str, Any]:
        """
        Resolve the blueprint provisioned by `a365 setup all`.

        Blueprint creation and permission setup are intentionally owned by the
        Agent 365 CLI so the required platform metadata is configured.
        """
        agent_registration = FIXED_AGENT_TEMPLATE

        if not self.generated_config_path.is_file():
            raise FileNotFoundError(
                f"{self.generated_config_path} not found. "
                f"Run 'a365 setup all --agent-name {agent_registration.display_name}' first."
            )

        with self.generated_config_path.open(encoding="utf-8") as config_file:
            generated_config = json.load(config_file)

        blueprint_id = generated_config.get("agentBlueprintId")
        if not blueprint_id:
            raise ValueError(
                "agentBlueprintId not found. Complete 'a365 setup all' first."
            )

        return {
            "blueprint_id": blueprint_id,
            "agent_name": agent_registration.display_name,
            "sponsor_user_id": agent_registration.sponsor_user_id,
            "owner_user_id": agent_registration.owner_user_id,
        }
        