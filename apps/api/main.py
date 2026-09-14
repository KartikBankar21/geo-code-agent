from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.api import conversations, datasets, geo, storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    conversations.start_worker()

    yield

    # Only close the agent's shared resources (Qdrant client, embedding
    # model) once, when the server itself stops - not after each turn.
    # See packages/agent/nodes.py: these are process-lifetime singletons
    # on purpose, so re-closing them between turns would break the next
    # one rather than clean anything up.
    if conversations.graph_already_built():
        from packages.agent.nodes import close_resources

        close_resources()

    conversations.shutdown_worker()


app = FastAPI(title="Geo Agent API", lifespan=lifespan)

# Permissive CORS for local development (the UI is normally served by
# this same app, so this mostly matters if you point a separate dev
# server at the API while iterating on the frontend).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
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


# Mounted last so the /api/* routes above always win; anything else
# (starting with `/`) falls through to the static UI, with index.html
# served at the root.
app.mount("/", StaticFiles(directory="apps/ui", html=True), name="ui")
