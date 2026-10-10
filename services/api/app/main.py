import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.public_demo import public_preview
from app.api.routes import router
from app.api.guides import router as guides_router
from app.api.statistics import router as statistics_router
from app.api.data_validation import router as data_router
from app.api.meta import router as meta_router

def create_app():
    app = FastAPI(title="EmblemLab", version="0.1.0", description="Versioned static-data strategy optimizer; scoped verification")
    app.middleware("http")(public_preview)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(router)

    app.include_router(guides_router)

    app.include_router(statistics_router)
    app.include_router(data_router)
    app.include_router(meta_router)

    # Optional all-in-one public host when GitHub Pages builds are unavailable.
    if os.getenv("PUBLIC_WEB_DIR"):
        app.mount("/", StaticFiles(directory=os.environ["PUBLIC_WEB_DIR"], html=True), name="web")
    return app


app = create_app()
