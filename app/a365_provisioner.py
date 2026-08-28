"""Small Microsoft Graph adapter for Agent 365 provisioning."""
from __future__ import annotations

import os
from typing import Any

GRAPH = "https://graph.microsoft.com"


class A365ProvisioningError(RuntimeError):
    """Raised when Microsoft Graph cannot complete provisioning."""


class _LegacyA365Provisioner:
    def __init__(self) -> None:
        self.tenant_id = os.environ.get("AGENT365_TENANT_ID", os.environ.get("AZURE_TENANT_ID", "")).strip()
        self.client_id = os.environ.get("A365_GRANT_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("A365_GRANT_CLIENT_SECRET", "").strip()

    def _token(self) -> str:
        import msal

        if not self.tenant_id or not self.client_id or not self.client_secret:
            raise A365ProvisioningError(
                "Set AGENT365_TENANT_ID, A365_GRANT_CLIENT_ID, and "
                "A365_GRANT_CLIENT_SECRET before enabling Graph provisioning."
            )
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        result = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"])
        token = result.get("access_token")
        if not token:
            raise A365ProvisioningError(
                f"Could not acquire Graph token: {result.get('error_description', result.get('error', 'unknown error'))}"
            )
        return token

    @staticmethod
    def _sponsor_ref(sponsor_id: str, kind: str = "group") -> str:
        value = sponsor_id.strip()
        if value.lower().startswith(("user:", "group:")):
            value = value.split(":", 1)[1].strip()
        return f"{GRAPH}/v1.0/{'groups' if kind == 'group' else 'users'}/{value}"

    @staticmethod
    def _graph_error_details(payload: dict, text: str) -> tuple[str, str]:
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            return str(err.get("code") or ""), str(err.get("message") or text or "")
        return "", text or ""

    def _post(self, token: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        import requests

        response = requests.post(
            f"{GRAPH}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 300:
            code, message = self._graph_error_details(payload, response.text[:500])
            detail = f"{code}: {message}" if code else message
            raise A365ProvisioningError(f"Graph {path} failed with HTTP {response.status_code}: {detail}")
        return payload

    def onboard(self, registration: Any) -> dict[str, str]:
        token = self._token()
        blueprint = self._post(
            token,
            "/v1.0/applications/microsoft.graph.agentIdentityBlueprint",
            {
                "displayName": registration.display_name,
                "sponsors@odata.bind": [self._sponsor_ref(registration.sponsor_user_id)],
            },
        )
        blueprint_app_id = blueprint.get("appId")
        blueprint_object_id = blueprint.get("id")
        if not blueprint_app_id or not blueprint_object_id:
            raise A365ProvisioningError("Graph blueprint response did not include appId and id.")

        self._post(
            token,
            "/v1.0/servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal",
            {"appId": blueprint_app_id},
        )
        credential = self._post(
            token,
            f"/v1.0/applications(appId='{blueprint_app_id}')/addPassword",
            {"passwordCredential": {"displayName": f"a365-{registration.usecase_id}"}},
        )
        blueprint_secret = credential.get("secretText")
        if not blueprint_secret:
            raise A365ProvisioningError("Graph credential response did not include secretText.")

        blueprint_token = self._blueprint_token(blueprint_app_id, blueprint_secret)
        instance = self._post(
            blueprint_token,
            "/beta/serviceprincipals/Microsoft.Graph.AgentIdentity",
            {
                "displayName": registration.display_name,
                "agentAppId": blueprint_app_id,
                "sponsors@odata.bind": [self._sponsor_ref(registration.sponsor_user_id)],
            },
        )
        agent_identity_id = instance.get("appId") or instance.get("id")
        if not agent_identity_id:
            raise A365ProvisioningError("Graph agent identity response did not include an ID.")

        owners = registration.owner_ids or ([registration.owner_user_id] if registration.owner_user_id else [])
        if not owners:
            raise A365ProvisioningError("At least one owner ID is required for Graph registration.")
        registered = self._post(
            token,
            "/beta/copilot/agentRegistrations",
            {
                "displayName": registration.display_name,
                "ownerIds": owners,
                "agentIdentityBlueprintId": blueprint_object_id,
                "agentIdentityId": agent_identity_id,
            },
        )
        return {
            "blueprint_id": blueprint_object_id,
            "agent_identity_id": str(agent_identity_id),
            "agent_registration_id": str(registered.get("id", "")),
        }

    def _blueprint_token(self, client_id: str, client_secret: str) -> str:
        import msal

        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"])
        token = result.get("access_token")
        if not token:
            raise A365ProvisioningError("Could not acquire a token for the blueprint identity.")
        return token


# Keep the original import path working for clients upgrading to the manager.
# A365Manager is the sole public implementation; the old class above remains
# private so existing source history is easy to compare during migration.
from app.a365_manager import A365Manager as A365Provisioner
from app.a365_manager import A365ProvisioningError as A365ProvisioningError