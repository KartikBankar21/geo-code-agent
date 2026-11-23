import os
from contextlib import asynccontextmanager
from pathlib import Path
import shutil

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from apps.executor_service.pool_manager import INPUT_DIR, SandboxPoolManager
from packages.observability.otel import init_telemetry

EXECUTOR_SECRET = os.getenv("EXECUTOR_SHARED_SECRET", "").strip()
pool_manager = SandboxPoolManager()


def verify_secret(x_executor_secret: str | None = Header(default=None)):
    if EXECUTOR_SECRET and x_executor_secret != EXECUTOR_SECRET:
        raise HTTPException(status_code=401, detail="Invalid executor secret")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool_manager.start()
    yield
    pool_manager.stop()


app = FastAPI(title="Geo Agent Execution Node (Tier 3)", lifespan=lifespan)
init_telemetry("geo-agent-tier3-executor", app=app)


class ExecuteRequest(BaseModel):
    conversation_id: str
    turn_id: str
    code: str
    timeout: float = 60.0


@app.get("/health")
def health():
    return {
        "status": "ok",
        "pool_size": len(pool_manager.containers),
        "active_sessions": len(pool_manager.last_activity),
    }


@app.post("/execute", dependencies=[Depends(verify_secret)])
def execute(req: ExecuteRequest):
    return pool_manager.execute(
        conversation_id=req.conversation_id,
        turn_id=req.turn_id,
        code=req.code,
        timeout=req.timeout,
    )


@app.post("/datasets/sync", dependencies=[Depends(verify_secret)])
async def sync_dataset(
    relative_path: str = Form(...),
    file: UploadFile = File(...),
):
    """Receive user-uploaded datasets from Tier 2 so /sandbox/input matches."""
    target = (INPUT_DIR / relative_path).resolve()
    if INPUT_DIR not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid dataset relative_path")

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return {"synced": str(target)}


@app.delete("/sessions/{conversation_id}", dependencies=[Depends(verify_secret)])
def delete_session(conversation_id: str):
    pool_manager.cleanup_session(conversation_id)
    return {"deleted": conversation_id}