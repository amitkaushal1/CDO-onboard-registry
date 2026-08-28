from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import require_api_configuration
from app.routes import router
from app.routes import registry


@asynccontextmanager
async def lifespan(_: FastAPI):
	require_api_configuration()
	registry.mongo_repository.connect()
	try:
		yield
	finally:
		registry.close()

app = FastAPI(
	title="CDO Onboard Registry API",
	description="API for registering blueprints and onboarding agents.",
	version="1.0.0",
	lifespan=lifespan,
)
app.include_router(router)
