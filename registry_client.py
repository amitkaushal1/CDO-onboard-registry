# registry_client.py
"""Backward-compatible exports for the registry service."""

from app.models import AgentRegistration, BlueprintRegistration
from app.a365_manager import A365Manager, get_a365_manager
from app.services import AgentRegistryService

AgentRegistryClient = AgentRegistryService

__all__ = [
    "AgentRegistration",
    "A365Manager",
    "AgentRegistryClient",
    "BlueprintRegistration",
    "get_a365_manager",
]
        