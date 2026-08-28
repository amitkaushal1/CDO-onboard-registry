"""Services for Graph-backed Agent 365 onboarding and registry records."""

import hashlib
import json
import os

from app.a365_manager import A365Manager
from app.config import require_graph_configuration
from app.models import AgentRegistration, RegistryRecord
from app.mongo_repository import MongoRegistryRepository


class AgentRegistryService:
    """Provision Agent 365 resources through Microsoft Graph."""

    def __init__(self):
        require_graph_configuration()
        self.provisioner = A365Manager()
        self.mongo_repository = MongoRegistryRepository()

    async def onboard_agent(self, registration: AgentRegistration, idempotency_key: str) -> RegistryRecord:
        """Provision in Graph and persist the result."""
        workflow_id = registration.workflow_id or registration.usecase_id
        request_fingerprint = hashlib.sha256(
            json.dumps(registration.model_dump(), sort_keys=True).encode("utf-8")
        ).hexdigest()
        existing = self.mongo_repository.claim_idempotency(idempotency_key, request_fingerprint)
        if existing is not None:
            if existing.get("request_fingerprint") != request_fingerprint:
                raise ValueError("Idempotency-Key was already used with a different request")
            if existing.get("provisioning_status") == "ready":
                return RegistryRecord.model_validate(existing)
            raise RuntimeError("This Idempotency-Key is already being processed")
        existing_workflow = self.mongo_repository.get_workflow_record(
            registration.usecase_id, workflow_id
        )
        if existing_workflow is not None:
            return RegistryRecord.model_validate(existing_workflow)
        if not registration.sponsor_user_id:
            registration = registration.model_copy(
                update={"sponsor_user_id": os.environ.get("A365_DEFAULT_SPONSOR_USER_ID", "")}
            )
        if not registration.sponsor_user_id:
            raise ValueError("sponsor_user_id or A365_DEFAULT_SPONSOR_USER_ID is required")
        graph_result = self.provisioner.onboard(registration)
        return self._save_registration(registration, graph_result, idempotency_key)

    def _save_registration(
        self, registration: AgentRegistration, graph_result: dict[str, str], idempotency_key: str
    ) -> RegistryRecord:
        blueprint_id = graph_result.get("blueprint_id")
        if not blueprint_id:
            raise ValueError("Graph response did not include blueprint_id")
        record = RegistryRecord(
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
            agent_identity_id=graph_result.get("agent_identity_id"),
            agent_registration_id=graph_result.get("agent_registration_id"),
            provisioning_mode="graph",
            usecase_id=registration.usecase_id,
            workflow_id=registration.workflow_id or registration.usecase_id,
            idempotency_key=idempotency_key,
        )
        self._save_record(record)
        return record

    async def get_registry_records(self) -> list[RegistryRecord]:
        return self.mongo_repository.list_records()

    def _save_record(self, result: RegistryRecord) -> None:
        self.mongo_repository.save(result)

    def close(self) -> None:
        self.mongo_repository.close()
