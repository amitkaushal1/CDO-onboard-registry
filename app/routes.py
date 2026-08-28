"""HTTP routes for agent onboarding."""
from fastapi import APIRouter, Depends, Header, HTTPException

from app.a365_manager import A365ProvisioningError
from app.auth import require_read_access, require_write_access
from app.models import AgentActionResult, AgentRegistration, RegistryRecord
from app.services import AgentRegistryService

router = APIRouter()
registry = AgentRegistryService()


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
        "agent_identity_id": response.agent_identity_id,
        "agent_registration_id": response.agent_registration_id,
        "provisioning_mode": response.provisioning_mode,
        "provisioning_status": response.provisioning_status,
    }


@router.post(
    "/agents/onboard",
    response_model=AgentActionResult,
    summary="Onboard an agent",
)
async def onboard_agent(
    registration: AgentRegistration,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    _: None = Depends(require_write_access),
):
    """Provision the agent through Microsoft Graph and save its record."""
    try:
        response = await registry.onboard_agent(registration, idempotency_key)
        return {"message": "Agent onboarding completed", **_agent_payload(response)}
    except A365ProvisioningError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Unable to complete agent onboarding") from error


@router.get(
    "/agents/registry",
    response_model=list[RegistryRecord],
    summary="List registered agents",
    dependencies=[Depends(require_read_access)],
)
async def get_registry_record():
    """Return all dynamically persisted agent registration records."""
    try:
        records = await registry.get_registry_records()
        return [_agent_payload(record) for record in records]
    except Exception as error:
        raise HTTPException(status_code=500, detail="Unable to read the agent registry") from error
