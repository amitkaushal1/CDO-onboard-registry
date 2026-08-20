"""Services for dynamic Agent 365 onboarding and registry records."""
import json
from pathlib import Path

from app.models import AgentRegistration, OnboardingResult, RegistryRecord


class AgentRegistryService:
    """Resolve an Agent 365 blueprint created by the CLI."""

    def __init__(self, generated_config_path: Path, registry_path: Path):
        self.generated_config_path = generated_config_path
        self.registry_path = registry_path

    async def onboard_agent(self, registration: AgentRegistration) -> OnboardingResult:
        if not self.generated_config_path.is_file():
            raise FileNotFoundError(
                f"{self.generated_config_path} not found. "
                f"Run 'a365 setup all --agent-name {registration.display_name}' first."
            )

        with self.generated_config_path.open(encoding="utf-8") as config_file:
            generated_config = json.load(config_file)

        blueprint_id = generated_config.get("agentBlueprintId")
        if not blueprint_id:
            raise ValueError(
                "agentBlueprintId not found. Complete 'a365 setup all' first."
            )

        result = OnboardingResult(
            blueprint_id=blueprint_id,
            agent_name=registration.display_name,
            sponsor_user_id=registration.sponsor_user_id,
            owner_user_id=registration.owner_user_id,
            description=registration.description,
            version=registration.version,
            category=registration.category,
            capabilities=registration.capabilities,
            environment=registration.environment,
            support_contact=registration.support_contact,
        )
        self._save_record(result)
        return result

    async def get_registry_records(self) -> list[RegistryRecord]:
        if not self.registry_path.is_file():
            return []

        with self.registry_path.open(encoding="utf-8") as registry_file:
            records = json.load(registry_file)
        return [RegistryRecord.model_validate(record) for record in records]

    def _save_record(self, result: OnboardingResult) -> None:
        records = []
        if self.registry_path.is_file():
            with self.registry_path.open(encoding="utf-8") as registry_file:
                records = json.load(registry_file)

        record = result.model_dump()
        records = [
            existing
            for existing in records
            if existing.get("blueprint_id") != result.blueprint_id
        ]
        records.append(record)
        self.registry_path.write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )
