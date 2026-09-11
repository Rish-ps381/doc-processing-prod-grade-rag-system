from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.ingest import router
from app.core.errors import AppError, app_error_handler
from app.main import app


class FakeService:
    async def create_file_job(self, filename, mime_type, file_type, content):
        return SimpleNamespace(id="job_file", document_id="doc_file", status=SimpleNamespace(value="QUEUED"))

    async def create_url_job(self, url):
        return SimpleNamespace(id="job_url", document_id="doc_url", status=SimpleNamespace(value="QUEUED"))

    async def get_job(self, job_id):
        if job_id == "missing":
            return None
        return SimpleNamespace(id=job_id, document_id="doc_1", status=SimpleNamespace(value="PROCESSING"), error=None, created_at="now", started_at=None, completed_at=None)


class FakeQueue:
    def __init__(self):
        self.jobs = []

    async def enqueue(self, job_id):
        self.jobs.append(job_id)


@pytest.fixture
def configured_app():
    app.state.ingestion_service = FakeService()
    app.state.job_queue = FakeQueue()
    app.add_exception_handler(AppError, app_error_handler)
    return app


@pytest.mark.asyncio
async def test_file_creation_returns_accepted(configured_app):
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.post("/ingest/create", data={"source_type": "file"}, files={"file": ("guide.md", b"# Guide", "text/markdown")})
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_url_creation_returns_accepted(configured_app):
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.post("/ingest/create", data={"source_type": "url", "url": "https://example.com"})
    assert response.status_code == 202
    assert response.json()["document_id"] == "doc_url"


@pytest.mark.asyncio
async def test_unsupported_file_type_is_rejected(configured_app):
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.post("/ingest/create", data={"source_type": "file"}, files={"file": ("guide.txt", b"text", "text/plain")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_missing_job_is_not_found(configured_app):
    async with AsyncClient(transport=ASGITransport(app=configured_app), base_url="http://test") as client:
        response = await client.get("/ingest/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INGESTION_JOB_NOT_FOUND"
