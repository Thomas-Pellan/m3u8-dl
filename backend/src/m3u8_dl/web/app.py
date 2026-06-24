from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .browse_session_repository import BrowseSessionRepository
from .browse_session_router import router as browse_session_router
from .browse_session_service import BrowseSessionService
from .repository import JobRepository
from .router import router
from .service import JobService
from .website_repository import WebsiteRepository
from .website_router import router as website_router
from .website_service import WebsiteService

_DEFAULT_DB_PATH = Path.home() / ".m3u8-dl" / "jobs.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = _DEFAULT_DB_PATH

    website_repo = WebsiteRepository(db_path)
    website_service = WebsiteService(website_repo)
    await website_service.init()
    app.state.website_service = website_service

    job_repo = JobRepository(db_path)
    job_service = JobService(job_repo, on_download=website_service.record_download)
    await job_service.init()
    app.state.job_service = job_service

    session_repo = BrowseSessionRepository(db_path)
    session_service = BrowseSessionService(session_repo, on_download=website_service.record_download)
    await session_service.init()
    app.state.browse_session_service = session_service

    yield

    await job_service.cleanup()
    await session_service.cleanup()


app = FastAPI(title="m3u8-dl", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(browse_session_router)
app.include_router(website_router)


def main() -> None:
    import uvicorn
    uvicorn.run("m3u8_dl.web.app:app", host="0.0.0.0", port=8080, reload=False)
