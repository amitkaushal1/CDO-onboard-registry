"""Direct Microsoft Graph manager for Agent 365 provisioning."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

GRAPH = "https://graph.microsoft.com"
_AGENT_IDENTITY_PATH = "/beta/serviceprincipals/Microsoft.Graph.AgentIdentity"
_AGENT_REGISTRATION_PATH = "/beta/copilot/agentRegistrations"
_RETRIABLE = (ConnectionError, requests.exceptions.RequestException)


class A365ProvisioningError(RuntimeError):
    """Raised when Microsoft Graph cannot complete provisioning."""


class A365Manager:
    """Own the reusable, Graph-backed Agent 365 provisioning workflow."""

    def __init__(self) -> None:
        # These caches prevent duplicate Graph objects during redeploys.
        self._blueprint_cache: dict[str, tuple[str, str, str, str]] = {}
        self._instance_cache: dict[str, str] = {}
        self._registration_cache: dict[str, str] = {}
        self._bp_token: dict[str, tuple[str, float]] = {}
        self._locks_guard = threading.Lock()
        self._usecase_locks: dict[str, threading.Lock] = {}
        self._workflow_locks: dict[str, threading.Lock] = {}

    @staticmethod
    def _tenant_id() -> str:
        tenant_id = (os.environ.get("AGENT365_TENANT_ID") or os.environ.get("AZURE_TENANT_ID") or "").strip()
        if not tenant_id:
            raise A365ProvisioningError("A365 tenant id is not configured. Set AGENT365_TENANT_ID.")
        return tenant_id

    def _admin_token(self) -> str:
        import msal

        client_id = str(os.environ.get("A365_GRANT_CLIENT_ID") or "").strip()
        client_secret = str(os.environ.get("A365_GRANT_CLIENT_SECRET") or "").strip()
        tenant_id = self._tenant_id()
        if not client_id or not client_secret:
            raise A365ProvisioningError(
                "A365 grant credentials are not configured. Set A365_GRANT_CLIENT_ID and A365_GRANT_CLIENT_SECRET."
            )
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"]) or {}
        token = result.get("access_token")
        if token:
            return token
        raise A365ProvisioningError(
            f"Failed to get admin token from client credentials: {result.get('error')} - "
            f"{str(result.get('error_description', ''))[:300]}"
        )

    @staticmethod
    def _graph_error_details(payload: dict, text: str) -> tuple[str, str]:
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            return str(err.get("code") or ""), str(err.get("message") or text or "")
        return "", text or ""

    def _post(self, token: str, path: str, body: dict) -> tuple[int, dict, str]:
        response = requests.post(
            f"{GRAPH}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        text = response.text or ""
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload, text

    @staticmethod
    def _sponsor_bind_ref(sponsor_id: str, kind: str = "user") -> str:
        raw = str(sponsor_id or "").strip()
        if not raw:
            raise A365ProvisioningError("sponsor_id is required")
        if raw.lower().startswith(("user:", "group:")):
            raw = raw.split(":", 1)[1].strip()
        segment = "groups" if kind == "group" else "users"
        return f"{GRAPH}/v1.0/{segment}/{raw}"

    @classmethod
    def _is_authorization_denied(cls, status: int, payload: dict, text: str) -> bool:
        code, message = cls._graph_error_details(payload, text)
        blob = f"{code} {message}".lower()
        return status == 403 and ("authorization_requestdenied" in blob or "insufficient privileges" in blob)

    def resolve_blueprint(self, usecase_id: str, blueprint_client_id: str = "", blueprint_id: str = "") -> tuple[str, str, str, str]:
        """Reuse a registry blueprint when its secret is supplied by configuration."""
        if not usecase_id:
            raise A365ProvisioningError("usecase_id is required")
        cached = self._blueprint_cache.get(usecase_id)
        if cached:
            return cached
        if blueprint_client_id and blueprint_id:
            secret = os.environ.get(f"A365_BLUEPRINT_SECRET_{usecase_id}", "").strip()
            if secret:
                result = (blueprint_client_id, secret, self._tenant_id(), blueprint_id)
                self._blueprint_cache[usecase_id] = result
                return result
        return self.create_blueprint_if_not_exists(usecase_id)

    def create_blueprint_if_not_exists(self, usecase_id: str, sponsor_id: Optional[str] = None, agent_name: Optional[str] = None) -> tuple[str, str, str, str]:
        """Create one blueprint, principal, and credential per use case."""
        if not usecase_id:
            raise A365ProvisioningError("usecase_id is required")
        cached = self._blueprint_cache.get(usecase_id)
        if cached:
            return cached
        with self._usecase_lock(usecase_id):
            cached = self._blueprint_cache.get(usecase_id)
            if cached:
                return cached
            sponsor = sponsor_id or self._resolve_sponsor(usecase_id)
            if not sponsor:
                raise A365ProvisioningError(f"No sponsor object id available for usecase {usecase_id}.")
            result = self._create_blueprint_and_secret(
                self._admin_token(), usecase_id, sponsor, agent_name or f"aaw-usecase-{usecase_id}"
            )
            self._blueprint_cache[usecase_id] = result
            return result

    def _create_blueprint_and_secret(self, admin_token: str, usecase_id: str, sponsor_id: str, display_name: str) -> tuple[str, str, str, str]:
        status, payload, text = self._post(
            admin_token,
            "/v1.0/applications/microsoft.graph.agentIdentityBlueprint",
            {"displayName": display_name, "sponsors@odata.bind": [self._sponsor_bind_ref(sponsor_id, "group")]},
        )
        if status not in (200, 201):
            code, message = self._graph_error_details(payload, text)
            if self._is_authorization_denied(status, payload, text):
                raise A365ProvisioningError(f"Blueprint create denied: HTTP {status} {code}: {message[:300]}")
            raise A365ProvisioningError(f"Blueprint create failed: HTTP {status} {code}: {message[:500]}")
        app_id, object_id = payload.get("appId"), payload.get("id")
        if not app_id or not object_id:
            raise A365ProvisioningError("Blueprint create succeeded but appId/objectId missing.")

        # Graph may need a short period before the principal and password endpoints are ready.
        time.sleep(5)
        self._post_with_retry(admin_token, "/v1.0/servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal", {"appId": app_id}, (200, 201), (400, 403, 404), 8)
        _, credential, credential_text = self._post_with_retry(admin_token, f"/v1.0/applications(appId='{app_id}')/addPassword", {"passwordCredential": {"displayName": f"a365-{usecase_id}"}}, (200, 201), (400, 404), 6)
        secret = credential.get("secretText")
        if not secret:
            raise A365ProvisioningError(f"addPassword succeeded without secretText: {credential_text[:500]}")
        return str(app_id), str(secret), self._tenant_id(), str(object_id)

    def _post_with_retry(self, token: str, path: str, body: dict, success: tuple[int, ...], retry_statuses: tuple[int, ...], attempts: int) -> tuple[int, dict, str]:
        last: tuple[int, dict, str] = (0, {}, "")
        for attempt in range(attempts):
            last = self._post(token, path, body)
            if last[0] in success:
                return last
            if last[0] not in retry_statuses or attempt == attempts - 1:
                code, message = self._graph_error_details(last[1], last[2])
                raise A365ProvisioningError(f"Graph {path} failed: HTTP {last[0]} {code}: {message[:500]}")
            time.sleep(min(5 * (2 ** attempt), 60))
        return last

    def ensure_agent_instance(self, usecase_id: str, workflow_id: str, sponsor_id: Optional[str] = None, agent_identity_group_sponsor_ids: Optional[list[str]] = None, agent_identity_user_sponsor_ids: Optional[list[str]] = None, display_name: Optional[str] = None) -> str:
        """Create or reuse an agent identity instance for a workflow."""
        if not workflow_id:
            raise A365ProvisioningError("workflow_id is required")
        cached = self._instance_cache.get(workflow_id)
        if cached:
            return cached
        with self._workflow_lock(workflow_id):
            cached = self._instance_cache.get(workflow_id)
            if cached:
                return cached
            client_id, secret, tenant_id, blueprint_id = self.create_blueprint_if_not_exists(usecase_id, sponsor_id, display_name)
            groups = self._unique_ids(agent_identity_group_sponsor_ids)
            users = self._unique_ids(agent_identity_user_sponsor_ids)
            if not groups and not users and (sponsor_id or self._resolve_sponsor(usecase_id)):
                groups = [str(sponsor_id or self._resolve_sponsor(usecase_id))]
            if not groups and not users:
                raise A365ProvisioningError(f"No sponsor object id available for usecase {usecase_id}.")
            result = self._mint_agent_instance(client_id, secret, tenant_id, blueprint_id, groups, users, display_name or f"aaw-agent-{workflow_id}")
            self._instance_cache[workflow_id] = result
            return result

    @staticmethod
    def _unique_ids(values: Optional[list[str]]) -> list[str]:
        result: list[str] = []
        for value in values or []:
            value = str(value or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    def _resolve_sponsor(self, usecase_id: str) -> Optional[str]:
        return os.environ.get("A365_DEFAULT_SPONSOR_USER_ID")

    def _blueprint_graph_token(self, client_id: str, client_secret: str, tenant_id: str) -> str:
        import msal

        cached = self._bp_token.get(client_id)
        if cached and time.time() - cached[1] < 3000:
            return cached[0]
        app = msal.ConfidentialClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant_id}", client_credential=client_secret)
        last_error = ""
        for attempt in range(6):
            result = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"]) or {}
            if result.get("access_token"):
                token = str(result["access_token"])
                self._bp_token[client_id] = (token, time.time())
                return token
            last_error = f"{result.get('error', '')} - {str(result.get('error_description', ''))[:300]}"
            if result.get("error") != "invalid_client" or attempt == 5:
                break
            time.sleep(min(5 * (2 ** attempt), 60))
        raise A365ProvisioningError(f"Failed to get blueprint token: {last_error}")

    def _mint_agent_instance(self, client_id: str, client_secret: str, tenant_id: str, agent_app_id: str, group_sponsor_ids: list[str], user_sponsor_ids: list[str], display_name: str) -> str:
        token = self._blueprint_graph_token(client_id, client_secret, tenant_id)
        body = {
            "displayName": display_name,
            "agentAppId": agent_app_id,
            "sponsors@odata.bind": [self._sponsor_bind_ref(value, "group") for value in group_sponsor_ids] + [self._sponsor_bind_ref(value, "user") for value in user_sponsor_ids],
        }
        for attempt in range(5):
            try:
                response = requests.post(f"{GRAPH}{_AGENT_IDENTITY_PATH}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=body, timeout=30)
            except _RETRIABLE as exc:
                if attempt == 4:
                    raise A365ProvisioningError(f"agent-instance mint failed for {display_name}: {exc}") from exc
                time.sleep(min(2 * (2 ** attempt), 30))
                continue
            if response.status_code < 300:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise A365ProvisioningError("agent-instance mint returned invalid JSON") from exc
                instance_id = data.get("appId") or data.get("id")
                if instance_id:
                    return str(instance_id)
                raise A365ProvisioningError(f"agent-instance mint returned no appId for {display_name}")
            if response.status_code == 400 and "sponsor" in (response.text or "").lower():
                raise A365ProvisioningError(f"agent-instance mint rejected: sponsor required/invalid (HTTP 400) for {display_name}")
            if response.status_code == 401 and "Authorization_IdentityNotFound" in (response.text or "") and attempt < 4:
                time.sleep(min(5 * (2 ** attempt), 60))
                continue
            break
        code, message = self._graph_error_details(self._json(response), response.text or "")
        raise A365ProvisioningError(f"agent-instance mint failed for {display_name}: HTTP {response.status_code} {code} ({message[:200]})")

    def register_in_a365_platform(self, agent_identity_blueprint_id: str, agent_identity_id: str, display_name: str, owner_ids: list[str], created_by_id: Optional[str] = None, description: Optional[str] = None, agent_endpoint_url: Optional[str] = None, originating_store: Optional[str] = None, source_agent_id: Optional[str] = None) -> dict:
        """Register an agent identity in the Agent 365 platform."""
        if not agent_identity_blueprint_id or not agent_identity_id or not display_name:
            raise A365ProvisioningError("blueprint id, agent identity id, and display name are required")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000+00:00")
        payload: dict[str, Any] = {"displayName": display_name, "agentIdentityBlueprintId": agent_identity_blueprint_id, "agentIdentityId": agent_identity_id, "sourceCreatedDateTime": now, "sourceLastModifiedDateTime": now}
        if owner_ids:
            payload["ownerIds"] = owner_ids
        for key, value in (("sourceAgentId", source_agent_id), ("description", description), ("createdBy", created_by_id), ("agentEndpointUrl", agent_endpoint_url), ("originatingStore", originating_store)):
            if value:
                payload[key] = value
        status, result, text = self._post(self._admin_token(), _AGENT_REGISTRATION_PATH, payload)
        if status not in (200, 201):
            code, message = self._graph_error_details(result, text)
            if self._is_authorization_denied(status, result, text):
                raise A365ProvisioningError(f"Agent registration denied: HTTP {status} {code}: {message[:300]}")
            raise A365ProvisioningError(f"Agent registration failed for '{display_name}': HTTP {status} {code}: {message[:500]}")
        return result

    def ensure_agent_registration(self, usecase_id: str, workflow_id: str, agent_identity_blueprint_id: str, agent_identity_id: str, display_name: str, owner_ids: list[str], created_by_id: Optional[str] = None, description: Optional[str] = None, agent_endpoint_url: Optional[str] = None, originating_store: Optional[str] = None, source_agent_id: Optional[str] = None) -> str:
        """Create one platform registration per workflow and reuse its ID."""
        if not workflow_id:
            raise A365ProvisioningError("workflow_id is required")
        cache_key = f"{usecase_id}:{workflow_id}"
        cached = self._registration_cache.get(cache_key)
        if cached:
            return cached
        with self._workflow_lock(workflow_id):
            cached = self._registration_cache.get(cache_key)
            if cached:
                return cached
            result = self.register_in_a365_platform(agent_identity_blueprint_id, agent_identity_id, display_name, owner_ids, created_by_id, description, agent_endpoint_url, originating_store, source_agent_id)
            registration_id = str(result.get("id") or "").strip()
            if not registration_id:
                raise A365ProvisioningError("Agent registration succeeded but did not return registration id.")
            self._registration_cache[cache_key] = registration_id
            return registration_id

    @staticmethod
    def _json(response: requests.Response) -> dict:
        try:
            value = response.json()
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def _usecase_lock(self, usecase_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._usecase_locks.setdefault(usecase_id, threading.Lock())

    def _workflow_lock(self, workflow_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._workflow_locks.setdefault(workflow_id, threading.Lock())

    def onboard(self, registration: Any) -> dict[str, str]:
        """Compatibility facade for the original framework onboarding call."""
        client_id, _, _, blueprint_id = self.create_blueprint_if_not_exists(registration.usecase_id, registration.sponsor_user_id, registration.display_name)
        instance_id = self.ensure_agent_instance(registration.usecase_id, registration.workflow_id or registration.usecase_id, registration.sponsor_user_id, display_name=registration.display_name)
        owners = registration.owner_ids or ([registration.owner_user_id] if registration.owner_user_id else [])
        registered = self.register_in_a365_platform(blueprint_id, instance_id, registration.display_name, owners, description=registration.description, agent_endpoint_url=registration.agent_endpoint_url, originating_store=registration.originating_store, source_agent_id=registration.source_agent_id)
        return {"blueprint_id": blueprint_id, "agent_identity_id": instance_id, "agent_registration_id": str(registered.get("id", ""))}


def get_a365_manager() -> A365Manager:
    """Return the process-wide manager used by the API service."""
    global _A365_MANAGER
    try:
        return _A365_MANAGER
    except NameError:
        _A365_MANAGER = A365Manager()
        return _A365_MANAGER
