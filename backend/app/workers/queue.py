import asyncio
from collections.abc import Awaitable, Callable


class JobQueue:
    async def enqueue(self, job_id: str) -> None:
        raise NotImplementedError


class InProcessJobQueue(JobQueue):
    def __init__(self, handler: Callable[[str], Awaitable[None]]):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._handler = handler
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def _run(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._handler(job_id)
            finally:
                self._queue.task_done()
