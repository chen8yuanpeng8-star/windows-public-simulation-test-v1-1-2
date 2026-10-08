import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class DrainResult:
    exited: tuple[str, ...]
    timed_out: tuple[str, ...]


class DrainCoordinator:
    def __init__(self):
        self.accepting = False
        self._workers = {}

    def register(self, name, stop_and_wait):
        if name in self._workers:
            raise ValueError(f"duplicate worker: {name}")
        self._workers[name] = stop_and_wait

    def start_accepting(self):
        self.accepting = True

    async def drain(self, timeout):
        self.accepting = False
        tasks = {
            asyncio.create_task(stop_and_wait()): name
            for name, stop_and_wait in self._workers.items()
        }
        if not tasks:
            return DrainResult((), ())
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        timed_out = tuple(sorted(tasks[task] for task in pending))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
        exited = tuple(sorted(tasks[task] for task in done))
        return DrainResult(exited, timed_out)

