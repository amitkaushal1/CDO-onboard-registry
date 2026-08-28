"""Data models used by the onboarding service."""
from pydantic import BaseModel, Field


class AgentRegistration(BaseModel):
    display_name: str
    sponsor_user_id: str = ""
    usecase_id: str = "agent-usecase"
    workflow_id: str | None = None
    owner_ids: list[str] = Field(default_factory=list)
    owner_user_id: str | None = None
    description: str = ""
    version: str = "1.0.0"
    category: str = "business-assistant"
    capabilities: list[str] = Field(default_factory=list)
    environment: str = "development"
    support_contact: str = ""
    agent_endpoint_url: str | None = None
    originating_store: str | None = None
    source_agent_id: str | None = None


class BlueprintRegistration(BaseModel):
    blueprint_id: str


class OnboardingResult(BaseModel):
    blueprint_id: str
    agent_name: str
    sponsor_user_id: str
    owner_user_id: str | None = None
    description: str = ""
    version: str = "1.0.0"
    category: str = "business-assistant"
    capabilities: list[str] = Field(default_factory=list)
    environment: str = "development"
    support_contact: str = ""
    agent_identity_id: str | None = None
    agent_registration_id: str | None = None
    provisioning_mode: str = "graph"
    provisioning_status: str = "ready"


class AgentActionResult(OnboardingResult):
    message: str


class RegistryRecord(OnboardingResult):
    """Persisted registration record for an onboarded agent."""
    usecase_id: str = "agent-usecase"
    workflow_id: str | None = None
    idempotency_key: str | None = None
