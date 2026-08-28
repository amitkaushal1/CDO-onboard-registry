"""MongoDB persistence for Agent 365 registry records."""
from __future__ import annotations

import os
from typing import Any

from app.models import RegistryRecord


class MongoRegistryRepository:
    """Persist registry records in MongoDB, including Cosmos DB Mongo API."""

    def __init__(self) -> None:
        connection_string = os.environ.get("COSMOS_MONGO_CONNECTION_STRING", "").strip()
        if not connection_string:
            raise ValueError("COSMOS_MONGO_CONNECTION_STRING is required for MongoDB persistence")
        self.database_name = os.environ.get("COSMOS_MONGO_DATABASE", "cdo-agent-registry-sandbox").strip()
        self.collection_name = os.environ.get("COSMOS_MONGO_COLLECTION", "agents").strip()
        self.operations_collection_name = os.environ.get(
            "COSMOS_MONGO_OPERATIONS_COLLECTION", "agent_operations"
        ).strip()
        if not self.database_name or not self.collection_name:
            raise ValueError("COSMOS_MONGO_DATABASE and COSMOS_MONGO_COLLECTION must not be empty")
        if not self.operations_collection_name:
            raise ValueError("COSMOS_MONGO_OPERATIONS_COLLECTION must not be empty")
        self._connection_string = connection_string
        self._client = None
        self._collection = None
        self._operations = None

    def connect(self) -> None:
        if self._client is not None:
            return
        from pymongo import MongoClient

        self._client = MongoClient(self._connection_string, serverSelectionTimeoutMS=10000)
        self._client.admin.command("ping")
        database = self._client[self.database_name]
        self._collection = database[self.collection_name]
        self._operations = database[self.operations_collection_name]
        self._collection.create_index("blueprint_id", unique=True)
        self._collection.create_index([("usecase_id", 1), ("workflow_id", 1)])
        self._operations.create_index("idempotency_key", unique=True)
        self._operations.create_index([("usecase_id", 1), ("workflow_id", 1)])

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._collection = None
            self._operations = None

    def _get_collection(self):
        self.connect()
        return self._collection

    def get_idempotency_record(self, idempotency_key: str) -> dict[str, Any] | None:
        self._get_collection()
        return self._operations.find_one({"idempotency_key": idempotency_key}, {"_id": False})

    def get_workflow_record(self, usecase_id: str, workflow_id: str) -> dict[str, Any] | None:
        self._get_collection()
        return self._operations.find_one(
            {"usecase_id": usecase_id, "workflow_id": workflow_id, "provisioning_status": "ready"},
            {"_id": False},
        )

    def claim_idempotency(self, idempotency_key: str, request_fingerprint: str) -> dict[str, Any] | None:
        self._get_collection()
        collection = self._operations
        existing = self.get_idempotency_record(idempotency_key)
        if existing is not None:
            return existing
        try:
            collection.insert_one(
                {
                    "idempotency_key": idempotency_key,
                    "request_fingerprint": request_fingerprint,
                    "provisioning_status": "processing",
                }
            )
            return None
        except Exception as error:
            from pymongo.errors import DuplicateKeyError

            if isinstance(error, DuplicateKeyError):
                return self.get_idempotency_record(idempotency_key)
            raise

    def save(self, record: RegistryRecord) -> RegistryRecord:
        """Upsert a record so repeated onboarding does not create duplicates."""
        document = record.model_dump()
        document["provisioning_status"] = "ready"
        existing = self._operations.find_one(
            {"idempotency_key": record.idempotency_key},
            {"request_fingerprint": 1, "_id": 0},
        )
        if existing and existing.get("request_fingerprint"):
            document["request_fingerprint"] = existing["request_fingerprint"]
        self._collection.replace_one({"blueprint_id": record.blueprint_id}, document, upsert=True)
        self._operations.replace_one(
            {"idempotency_key": record.idempotency_key},
            {**document, "request_fingerprint": existing.get("request_fingerprint") if existing else None},
            upsert=True,
        )
        return record

    def list_records(self) -> list[RegistryRecord]:
        """Return all persisted records in stable creation order."""
        documents = self._get_collection().find({}, {"_id": False}).sort("blueprint_id", 1)
        return [RegistryRecord.model_validate(document) for document in documents]
