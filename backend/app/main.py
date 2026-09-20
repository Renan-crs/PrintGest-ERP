from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}