"""Data models used by the onboarding service."""
from pydantic import BaseModel, Field


class AgentRegistration(BaseModel):
    display_name: str
    sponsor_user_id: str
    owner_user_id: str | None = None
    description: str = ""
    version: str = "1.0.0"
    category: str = "business-assistant"
    capabilities: list[str] = Field(default_factory=list)
    environment: str = "development"
    support_contact: str = ""


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
