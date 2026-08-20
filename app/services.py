"""Services for reading Agent 365 onboarding data."""
import json
from pathlib import Path

from app.models import AgentRegistration, OnboardingResult


AGENT_TEMPLATE = AgentRegistration(
    display_name="claims-support-agent",
    sponsor_user_id="sponsor-user-object-id",
    owner_user_id="owner-user-object-id",
    description="Assists claims teams with support and onboarding workflows.",
    version="1.0.0",
    category="claims-support",
    capabilities=["claims triage", "knowledge retrieval", "case handoff"],
    environment="development",
    support_contact="claims-platform-team@example.com",
)


class AgentRegistryService:
    """Resolve an Agent 365 blueprint created by the CLI."""

    def __init__(self, generated_config_path: Path):
        self.generated_config_path = generated_config_path

    async def register_agent(self) -> OnboardingResult:
        if not self.generated_config_path.is_file():
            raise FileNotFoundError(
                f"{self.generated_config_path} not found. "
                f"Run 'a365 setup all --agent-name {AGENT_TEMPLATE.display_name}' first."
            )

        with self.generated_config_path.open(encoding="utf-8") as config_file:
            generated_config = json.load(config_file)

        blueprint_id = generated_config.get("agentBlueprintId")
        if not blueprint_id:
            raise ValueError(
                "agentBlueprintId not found. Complete 'a365 setup all' first."
            )

        return OnboardingResult(
            blueprint_id=blueprint_id,
            agent_name=AGENT_TEMPLATE.display_name,
            sponsor_user_id=AGENT_TEMPLATE.sponsor_user_id,
            owner_user_id=AGENT_TEMPLATE.owner_user_id,
            description=AGENT_TEMPLATE.description,
            version=AGENT_TEMPLATE.version,
            category=AGENT_TEMPLATE.category,
            capabilities=AGENT_TEMPLATE.capabilities,
            environment=AGENT_TEMPLATE.environment,
            support_contact=AGENT_TEMPLATE.support_contact,
        )
