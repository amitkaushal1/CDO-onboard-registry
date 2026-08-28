# Agent Onboarding Microservice

This service provides a small FastAPI onboarding endpoint for an Agent 365 agent. Blueprint provisioning and publishing follow the Microsoft Agent 365 CLI workflow documented by Microsoft.

The service uses Microsoft Graph for Agent 365 provisioning. Publishing remains a separate CLI/admin workflow.

Registry records are stored in the Cosmos DB MongoDB API. The default database is `cdo-agent-registry-sandbox` and the default collection is `agents`.

## Files

### `main.py`

Creates the FastAPI application and includes the HTTP router from `app/routes.py`.

### `app/routes.py`

Defines the Graph-backed endpoints:

```http
POST /agents/onboard
GET /agents/registry
```

`POST /agents/onboard` creates the blueprint, blueprint principal, credential, agent identity, and Agent 365 registration through Microsoft Graph before saving the result.

`GET /agents/registry` returns the current registered agent metadata without performing a separate onboarding action.

### `app/services.py`

Contains the Graph provisioning and registry service.

### `app/models.py`

Contains the typed registration and onboarding result models.

### `app/config.py`

Reads Graph and MongoDB environment configuration.

### `registry_client.py`

Provides backward-compatible imports for the registry service and models.

Blueprint creation, required permissions, managed identity, infrastructure, and platform metadata are owned by `a365 setup all`, as required by the Agent 365 workflow. This client does not make a third-party API call.

## Microsoft Agent 365 Flow

```text
1. Developer or administrator
   |
   | a365 setup all --agent-name <agent-name>
   v
2. Agent 365 CLI
   |
   | Creates/configures blueprint, permissions, and Azure resources
   | Writes a365.generated.config.json
   v
3. FastAPI service
   |
   | POST /agents/onboard
   | Provisions and registers the agent
   | Persists the onboarding result
   v
4. Agent 365 CLI
   |
   | a365 publish --agent-name <agent-name>
   | Updates manifest.json
   | Creates manifest/manifest.zip
   v
5. Microsoft 365 admin center
   |
   | Agents -> All agents -> Upload custom agent
   | Upload manifest/manifest.zip
   v
6. Published agent
```

## Prerequisites

Install and authenticate the tools required by the Microsoft workflow:

```powershell
az login
a365 --help
```

The publishing documentation requires a Microsoft 365 tenant and a Global Administrator for the admin center upload step. Blueprint setup requires the appropriate Agent 365 role, such as Global Administrator or Agent ID Developer, and access to an Azure subscription.

## Setup the Blueprint

Use the `display_name` from the onboarding template as the CLI agent name:

```powershell
a365 setup all --agent-name claims-support-agent
```

For a project that uses a configuration file, run:

```powershell
a365 setup all
```

The setup command creates or configures the blueprint, applies required platform settings and permissions, and writes:

```text
a365.generated.config.json
```

Verify that the file contains an `agentBlueprintId`:

```powershell
Get-Content a365.generated.config.json | ConvertFrom-Json | Select-Object agentBlueprintId
```

Do not manually create a partial blueprint in this service. Microsoft notes that platform-manageable blueprints require settings such as `managerApplications`; the CLI setup is the authoritative way to configure them.

## Agent Onboarding

The onboarding request supplies the metadata for each agent:

```json
{
  "display_name": "claims-support-agent",
  "sponsor_user_id": "sponsor-user-object-id",
   "owner_user_id": "owner-user-object-id",
   "description": "Assists claims teams with support and onboarding workflows.",
   "version": "1.0.0",
   "category": "claims-support",
   "capabilities": [
      "claims triage",
      "knowledge retrieval",
      "case handoff"
   ],
   "environment": "development",
   "support_contact": "claims-platform-team@example.com"
}
```

Replace the placeholder IDs and support contact with real values. `owner_user_id` and `owner_ids` are optional. When supplied, `owner_ids` may contain an A365-supported user or group Object ID. The AAW administrator group remains the blueprint sponsor through `A365_DEFAULT_SPONSOR_USER_ID`.

Onboard the agent through Microsoft Graph:

```powershell
Invoke-RestMethod `
   -Uri "http://127.0.0.1:8000/agents/onboard" `
   -Method Post `
   -ContentType "application/json" `
   -Body (@{
      display_name = "claims-support-agent"
      sponsor_user_id = "sponsor-user-object-id"
      description = "Assists claims teams"
      version = "1.0.0"
      category = "claims-support"
      capabilities = @("claims triage", "knowledge retrieval")
      environment = "development"
      support_contact = "claims-platform-team@example.com"
   } | ConvertTo-Json)
```

Read all persisted registrations through the separate registry endpoint:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agents/registry" -Method Get
```

### Microsoft Graph mode

Set `A365_GRAPH_ENABLED=true` and configure the tenant, provisioning application, client secret, and sponsor group before starting the service:

```powershell
$env:A365_GRAPH_ENABLED = "true"
$env:AGENT365_TENANT_ID = "<tenant-id>"
$env:A365_GRANT_CLIENT_ID = "<client-id>"
$env:A365_GRANT_CLIENT_SECRET = "<rotated-secret>"
$env:A365_DEFAULT_SPONSOR_USER_ID = "<sponsor-group-id>"
```

In Graph mode, `POST /agents/onboard` performs the full provisioning sequence. The provisioning identity needs the required Agent 365 Microsoft Graph application permissions and administrator consent. The client secret is used only through environment configuration and must not be committed.

Expected response shape:

```json
{
   "message": "Agent blueprint is ready for publishing",
   "agent_name": "claims-support-agent",
   "sponsor_user_id": "sponsor-user-object-id",
   "owner_user_id": "owner-user-object-id",
   "description": "Assists claims teams with support and onboarding workflows.",
   "version": "1.0.0",
   "category": "claims-support",
   "capabilities": ["claims triage", "knowledge retrieval", "case handoff"],
   "environment": "development",
   "support_contact": "claims-platform-team@example.com",
  "blueprint_id": "<agent-blueprint-id>",
   "next_step": "Run 'a365 publish --agent-name claims-support-agent' and upload manifest/manifest.zip in the Microsoft 365 admin center."
}
```

## Publish the Agent

After `a365 setup all` has created the blueprint and after local testing, run:

```powershell
a365 publish --agent-name claims-support-agent
```

The command:

1. Updates `manifest.json` with the blueprint ID.
2. Creates `manifest/manifest.zip`.
3. Prints upload instructions.

Verify the package exists:

```powershell
Test-Path manifest/manifest.json
Test-Path manifest/manifest.zip
```

Then upload `manifest/manifest.zip` manually:

```text
Microsoft 365 admin center
-> Agents
-> All agents
-> Upload custom agent
```

Publishing can take several minutes before the agent appears in the admin center and Teams.

## Environment Configuration

The `.env` file contains the Graph and MongoDB configuration:

```env
COSMOS_MONGO_CONNECTION_STRING=<cosmos-mongodb-connection-string>
COSMOS_MONGO_DATABASE=cdo-agent-registry-sandbox
COSMOS_MONGO_COLLECTION=agents
A365_READ_API_KEY=<read-api-key>
A365_WRITE_API_KEY=<write-api-key>
```

The application loads this file with `python-dotenv`. The `.env` file is ignored by Git. Do not commit client secrets or database passwords.

All API requests require an `X-API-Key` header. Use `A365_WRITE_API_KEY` with `POST /agents/onboard` and `A365_READ_API_KEY` with `GET /agents/registry`. Onboarding also requires a unique `Idempotency-Key` header; repeating a completed request with the same key returns the stored result without creating new Graph resources.

## Installation and Run

Install the FastAPI service dependencies:

```powershell
pip install -r requirements.txt
```

Start the local service:

```powershell
uvicorn main:app --reload
```

The registration APIs are available at:

```text
http://127.0.0.1:8000/agents/onboard
http://127.0.0.1:8000/agents/registry
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Important Boundary

The upload cannot create the blueprint. Microsoft requires the blueprint ID before `a365 publish` can update `manifest.json` and create `manifest/manifest.zip`. The required order is:

```text
1. Run `a365 setup all --agent-name <display_name>` to create/configure the requested blueprint.
2. Send the agent metadata with `POST /agents/onboard`; Graph creates the blueprint and registration.
3. Test the agent locally.
4. Run `a365 publish --agent-name <display_name>`.
5. Upload `manifest/manifest.zip` to Microsoft 365 admin center.
```

`POST /agents/onboard` provisions the blueprint, agent identity, and Agent 365 registration. The service does not replace `a365 publish` or the Microsoft 365 admin-center upload.
