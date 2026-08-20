# main.py
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from registry_client import AgentRegistryClient

load_dotenv()

app = FastAPI()

registry = AgentRegistryClient(
    generated_config_path=Path(
        os.environ.get("A365_GENERATED_CONFIG", "a365.generated.config.json")
    ),
)


@app.post("/agents/onboard")
async def onboard_agent():
    try:
        response = await registry.register_agent()
        return {
            "message": "Agent blueprint is ready for publishing",
            "blueprint_id": response["blueprint_id"],
            "agent_name": response["agent_name"],
            "sponsor_user_id": response["sponsor_user_id"],
            "owner_user_id": response["owner_user_id"],
            "next_step": f"Run 'a365 publish --agent-name {response['agent_name']}' and upload manifest/manifest.zip in the Microsoft 365 admin center.",
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))