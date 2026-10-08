from contextlib import asynccontextmanager

from fastapi import FastAPI


def create_app(coordinator):
    @asynccontextmanager
    async def lifespan(_app):
        coordinator.start_accepting()
        try:
            yield
        finally:
            result = await coordinator.drain(timeout=2.0)
            if result.timed_out:
                raise TimeoutError(f"workers did not drain: {result.timed_out}")

    return FastAPI(lifespan=lifespan)

