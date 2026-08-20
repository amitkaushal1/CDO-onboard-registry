# registry_client.py
"""Backward-compatible exports for the registry service."""

from app.models import AgentRegistration, OnboardingResult
from app.services import AgentRegistryService

AgentRegistryClient = AgentRegistryService

__all__ = [
    "AgentRegistration",
    "AgentRegistryClient",
    "OnboardingResult",
]
        