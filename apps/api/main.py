import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.api import conversations, datasets, geo, storage
from packages.observability.otel import init_telemetry

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    conversations.start_worker()

    yield

    if conversations.graph_already_built():
        from packages.agent.nodes import close_resources

        close_resources()

    conversations.shutdown_worker()


app = FastAPI(title="Geo Agent API", lifespan=lifespan)
init_telemetry("geo-agent-tier2-api", app=app)

raw_origins = os.getenv("CORS_ORIGINS", "*").strip()
allowed_origins = (
    ["*"]
    if raw_origins == "*"
    else [o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(datasets.router)
app.include_router(geo.router)
app.include_router(conversations.router)


@app.get("/api/health")
def health():
    graph, error = conversations.get_graph()

    return {
        "status": "ok",
        "agent_ready": graph is not None,
        "agent_error": error,
    }


app.mount("/", StaticFiles(directory="apps/ui", html=True), name="ui")
