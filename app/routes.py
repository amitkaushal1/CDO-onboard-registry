"""HTTP routes for agent onboarding."""
from fastapi import APIRouter, HTTPException

from app.config import generated_config_path
from app.services import AgentRegistryService

router = APIRouter()
registry = AgentRegistryService(generated_config_path())


def _agent_payload(response):
    return {
        "blueprint_id": response.blueprint_id,
        "agent_name": response.agent_name,
        "sponsor_user_id": response.sponsor_user_id,
        "owner_user_id": response.owner_user_id,
        "description": response.description,
        "version": response.version,
        "category": response.category,
        "capabilities": response.capabilities,
        "environment": response.environment,
        "support_contact": response.support_contact,
    }


@router.post("/agents/onboard")
async def onboard_agent():
    try:
        response = await registry.register_agent()
        return {
            "message": "Agent blueprint is ready for publishing",
            **_agent_payload(response),
            "next_step": (
                f"Run 'a365 publish --agent-name {response.agent_name}' and upload "
                "manifest/manifest.zip in the Microsoft 365 admin center."
            ),
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/agents/registry")
async def get_registry_record():
    """Return the current registered agent metadata without onboarding it."""
    try:
        response = await registry.register_agent()
        return _agent_payload(response)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
