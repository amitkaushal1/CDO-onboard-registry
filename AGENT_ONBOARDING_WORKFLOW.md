# Agent 365 Onboarding Workflow

## 1. Overview

This service provisions and registers Agent 365 agents through Microsoft Graph. It stores completed registration records in Cosmos DB MongoDB API.

The service exposes two protected endpoints:

```http
POST /agents/onboard
GET /agents/registry
```

Publishing remains a separate Agent 365 CLI and Microsoft 365 admin-center workflow.

## 2. Required Configuration

Configure these environment variables before starting the service:

```env
A365_GRAPH_ENABLED=true
AGENT365_TENANT_ID=<tenant-id>
A365_GRANT_CLIENT_ID=<client-id>
A365_GRANT_CLIENT_SECRET=<client-secret>

A365_READ_API_KEY=<read-api-key>
A365_WRITE_API_KEY=<write-api-key>

A365_DEFAULT_SPONSOR_USER_ID=<optional-sponsor-object-id>

COSMOS_MONGO_CONNECTION_STRING=<mongodb-connection-string>
COSMOS_MONGO_DATABASE=cdo-agent-registry-sandbox
COSMOS_MONGO_COLLECTION=agents
COSMOS_MONGO_OPERATIONS_COLLECTION=agent_operations
```

The application loads `.env` through `python-dotenv`.

Startup fails when Graph credentials, API keys, or the MongoDB connection string are missing.

## 3. Start the Service

Install the dependencies:

```powershell
pip install -r requirements.txt
```

Start FastAPI:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## 4. Startup Lifecycle

FastAPI uses the application lifespan handler in `main.py`.

At startup, the service:

1. Validates API authentication configuration.
2. Connects to MongoDB.
3. Executes a MongoDB `ping`.
4. Creates the required indexes.
5. Begins accepting requests.

At shutdown, the service closes the MongoDB client.

MongoDB indexes include:

- Unique `blueprint_id`
- Unique sparse `idempotency_key`
- Unique `usecase_id` and `workflow_id`
- Provisioning lookup index

The existing `agents` collection is sharded by `blueprint_id`. Idempotency state is therefore stored in the separate `agent_operations` collection, which must be created with `idempotency_key` as its shard key in Cosmos DB before first startup.

## 5. Submit an Onboarding Request

Use the write API key and a unique idempotency key:

```http
POST /agents/onboard
X-API-Key: <write-api-key>
Idempotency-Key: claims-agent-request-001
Content-Type: application/json
```

Example request:

```json
{
  "display_name": "claims-support-agent",
  "sponsor_user_id": "sponsor-object-id",
  "usecase_id": "claims-usecase",
  "workflow_id": "claims-workflow-v1",
  "owner_user_id": "owner-object-id",
  "description": "Assists claims teams",
  "version": "1.0.0",
  "category": "claims-support",
  "capabilities": [
    "claims triage",
    "knowledge retrieval"
  ],
  "environment": "development",
  "support_contact": "claims-team@example.com"
}
```

The request must contain:

- `sponsor_user_id`, or a configured `A365_DEFAULT_SPONSOR_USER_ID`
- A unique `Idempotency-Key`
- A valid `A365_WRITE_API_KEY`

`owner_user_id` and `owner_ids` are optional. When supplied, `owner_ids` may contain an A365-supported user or group Object ID. The AAW administrator group remains the blueprint sponsor.

## 6. Authentication and Authorization

The service uses API keys supplied in the `X-API-Key` header.

### Onboarding

`POST /agents/onboard` requires `A365_WRITE_API_KEY`.

### Registry access

`GET /agents/registry` accepts `A365_READ_API_KEY`. The write key may also be used for registry reads.

Invalid or missing keys return:

```http
401 Unauthorized
```

## 7. Idempotency Processing

The service calculates a SHA-256 fingerprint of the request body and stores it with the idempotency key.

The first request creates a MongoDB processing record:

```json
{
  "idempotency_key": "claims-agent-request-001",
  "request_fingerprint": "<sha256-hash>",
  "provisioning_status": "processing"
}
```

If the same key and request are submitted again after completion, the saved result is returned and Microsoft Graph is not called again.

If the same key is reused with different request data, the request is rejected.

Concurrent requests are protected by the unique MongoDB idempotency index.

## 8. Workflow Reuse After Restart

The service also checks MongoDB for an existing completed record matching:

```text
usecase_id + workflow_id
```

This allows completed Graph resources to be reused after an application restart. The process does not depend only on the in-memory caches in `A365Manager`.

## 9. Microsoft Graph Provisioning

When no existing record is found, `A365Manager` performs the following sequence:

1. Creates an Agent Identity Blueprint.
2. Creates the blueprint service principal.
3. Adds a password credential.
4. Obtains a token for the blueprint identity.
5. Creates the Agent Identity instance.
6. Registers the agent through:

   ```text
   /beta/copilot/agentRegistrations
   ```

7. Returns the Graph blueprint, identity, and registration IDs.

Graph errors return:

```http
502 Bad Gateway
```

## 10. Persist the Completed Result

After Graph provisioning succeeds, the service saves a completed `RegistryRecord` in MongoDB.

The record contains:

- Agent name and metadata
- Blueprint ID
- Agent identity ID
- Agent registration ID
- Use case ID
- Workflow ID
- Idempotency key
- Provisioning mode: `graph`
- Provisioning status: `ready`

## 11. Successful Response

A successful onboarding response resembles:

```json
{
  "message": "Agent onboarding completed",
  "blueprint_id": "graph-blueprint-id",
  "agent_name": "claims-support-agent",
  "sponsor_user_id": "sponsor-object-id",
  "owner_user_id": "owner-object-id",
  "agent_identity_id": "agent-identity-id",
  "agent_registration_id": "agent-registration-id",
  "provisioning_mode": "graph",
  "provisioning_status": "ready"
}
```

## 12. Read Registered Agents

Call the registry endpoint with a read key:

```http
GET /agents/registry
X-API-Key: <read-api-key>
```

The service returns completed registration records from MongoDB.

## 13. Publish the Agent

After onboarding succeeds, publish the agent with the Agent 365 CLI:

```powershell
a365 publish --agent-name claims-support-agent
```

The command creates or updates:

```text
manifest/manifest.json
manifest/manifest.zip
```

Upload `manifest/manifest.zip` in the Microsoft 365 admin center:

```text
Agents -> All agents -> Upload custom agent
```

## 14. End-to-End Sequence

```text
1. Configure Graph, API key, and MongoDB environment variables.
2. Start the FastAPI service.
3. FastAPI validates configuration and initializes MongoDB.
4. Client sends POST /agents/onboard.
5. API validates the write key and Idempotency-Key.
6. MongoDB claims the idempotency key.
7. Service checks for an existing completed workflow.
8. Microsoft Graph creates or reuses Agent 365 resources.
9. Service stores the completed registration in MongoDB.
10. API returns the Graph IDs and ready status.
11. Client runs a365 publish.
12. Administrator uploads manifest/manifest.zip.
13. The agent becomes available through Microsoft 365.
```

## 15. Production Considerations

- Store API keys and Graph secrets in a managed secret store such as Azure Key Vault.
- Use HTTPS in every deployed environment.
- Restrict network access to the API and MongoDB.
- Grant only the Microsoft Graph application permissions required by the provisioning workflow.
- Monitor Graph failures, MongoDB failures, and abandoned `processing` records.
- Add recovery or lease expiration for idempotency records left in `processing` after a crash.
- Use separate API keys for separate clients or environments and rotate them regularly.
