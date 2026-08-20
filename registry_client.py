# registry_client.py
"""Backward-compatible exports for the registry service."""

from app.models import AgentRegistration, OnboardingResult
from app.services import AGENT_TEMPLATE, AgentRegistryService

FIXED_AGENT_TEMPLATE = AGENT_TEMPLATE
AgentRegistryClient = AgentRegistryService

__all__ = [
    "AgentRegistration",
    "AgentRegistryClient",
    "FIXED_AGENT_TEMPLATE",
    "OnboardingResult",
]
        