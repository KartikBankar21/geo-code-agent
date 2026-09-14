from typing import Any, Literal
from pydantic import BaseModel, Field


# --- Datasets -----------------------------------------------------------

class DatasetFile(BaseModel):
    filename: str
    host_path: str
    sandbox_path: str | None
    size_bytes: int


class Dataset(BaseModel):
    name: str
    files: list[DatasetFile]


class DatasetListResponse(BaseModel):
    datasets: list[Dataset]


class LayerInfo(BaseModel):
    name: str


class LayersResponse(BaseModel):
    layers: list[str]


# --- Conversations (persistent GIS workflow chats) -----------------------

class ConversationCreateRequest(BaseModel):
    task: str = Field(..., min_length=1, description="The first GIS workflow prompt.")
    dataset: str = Field(..., description="Dataset name as returned by GET /api/datasets.")
    file: str | None = Field(
        None,
        description="Filename within the dataset, if it has more than one.",
    )


class ConversationCreateResponse(BaseModel):
    conversation_id: str
    turn_id: str


class ContinueConversationRequest(BaseModel):
    task: str = Field(..., min_length=1, description="The follow-up GIS workflow prompt.")


class ContinueConversationResponse(BaseModel):
    turn_id: str


TurnStatus = Literal["queued", "running", "completed", "failed"]


class TaskEvent(BaseModel):
    node: str
    type: str
    data: dict[str, Any]


class TurnSummary(BaseModel):
    id: str
    conversation_id: str
    turn_index: int
    task: str
    status: TurnStatus
    generated_code: str | None = None
    validation_result: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    artifacts: list[str] = []
    error: str | None = None
    events: list[TaskEvent] = []
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    dataset_host_path: str
    dataset_sandbox_path: str
    created_at: str
    updated_at: str
    turns: list[TurnSummary] = []


class ConversationListItem(BaseModel):
    id: str
    title: str
    dataset_host_path: str
    dataset_sandbox_path: str
    created_at: str
    updated_at: str
    turn_count: int
    last_task: str | None = None
    last_status: TurnStatus | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]
