from app.services.ingestion import IngestionService


class IngestionWorker:
    def __init__(self, service: IngestionService):
        self.service = service

    async def process(self, job_id: str) -> None:
        await self.service.process_job(job_id)
