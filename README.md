# Agent Onboarding Microservice

This service provides a small FastAPI onboarding endpoint for an Agent 365 agent. Blueprint provisioning and publishing follow the Microsoft Agent 365 CLI workflow documented by Microsoft.

The service does not call a third-party registry and does not publish directly from the HTTP request. The Agent 365 CLI performs the platform setup and package creation.

## Files

### `main.py`

Defines the local endpoint:

```http
POST /agents/onboard
```

The endpoint uses the fixed template in `registry_client.py`, verifies that the Agent 365 CLI generated a blueprint configuration, and returns the `agentBlueprintId` that publishing uses.

### `registry_client.py`

Contains the local wrapper that reads `a365.generated.config.json` and extracts `agentBlueprintId`.

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
   | Uses the fixed template
   | Reads agentBlueprintId from generated config
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

## Fixed Agent Template

The fixed template is defined in `registry_client.py`:

```json
{
  "display_name": "claims-support-agent",
  "sponsor_user_id": "sponsor-user-object-id",
  "owner_user_id": "owner-user-object-id"
}
```

Replace the placeholder IDs with the real Microsoft Entra user object IDs before running the service. `owner_user_id` is optional. `a365 setup all` remains responsible for creating the fully configured blueprint.

The FastAPI endpoint has no request body. Call it after `a365 setup all`:

```powershell
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/agents/onboard" `
   -Method Post
```

Expected response shape:

```json
{
   "message": "Agent blueprint is ready for publishing",
   "agent_name": "claims-support-agent",
   "sponsor_user_id": "sponsor-user-object-id",
   "owner_user_id": "owner-user-object-id",
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

The `.env` file contains the path to the CLI-generated configuration:

```env
A365_GENERATED_CONFIG=a365.generated.config.json
```

`main.py` loads this file with `python-dotenv`. The `.env` file is ignored by Git. Do not put client secrets or passwords in it.

## Installation and Run

Install the FastAPI service dependencies:

```powershell
pip install -r requirements.txt
```

Start the local service:

```powershell
uvicorn main:app --reload
```

The endpoint is available at:

```text
http://127.0.0.1:8000/agents/onboard
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Important Boundary

The upload cannot create the blueprint. Microsoft requires the blueprint ID before `a365 publish` can update `manifest.json` and create `manifest/manifest.zip`. The required order is:

```text
1. Update the fixed template in `registry_client.py`.
2. Run `a365 setup all --agent-name <display_name>` to create/configure the blueprint.
3. Run `POST /agents/onboard` with no request body to verify `agentBlueprintId`.
4. Test the agent locally.
5. Run a365 publish --agent-name <display_name>.
6. Upload manifest/manifest.zip to Microsoft 365 admin center.
```

This service does not replace `a365 setup all` or `a365 publish`. It validates the template and reads the CLI-generated blueprint ID; the Microsoft Agent 365 CLI provisions the blueprint and creates the publishable package.
