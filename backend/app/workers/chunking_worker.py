from app.services.chunking.service import ChunkingService


class ChunkingWorker:
    def __init__(self, service: ChunkingService):
        self.service = service

    async def process(self, job_id: str) -> None:
        await self.service.process_job(job_id)
