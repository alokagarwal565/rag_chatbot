from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=10000)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural-language question")
    conversation_history: List[ConversationTurn] = Field(default_factory=list, max_length=20)
    doc_ids: Optional[List[str]] = Field(None, description="Optional: restrict retrieval to these documents")
    rerank: Optional[bool] = Field(None, description="Override the reranker toggle for this request")


class StreamEvent(BaseModel):
    type: Literal["status", "rewrite", "retrieval", "token", "final", "abstain", "error", "done"]
    data: Dict[str, Any]


class DocumentItem(BaseModel):
    doc_id: str
    filename: str
    title: str
    page_count: int
    native_pages: int = 0
    ocr_pages: int = 0
    chunk_count: int = 0
    language: Optional[str] = None
    status: str
    stage: Optional[str] = None
    stage_timings: Dict[str, float] = Field(default_factory=dict)
    source_url: Optional[str] = None
    license: Optional[str] = None
    ingested_at: Optional[str] = None


class ErrorResponse(BaseModel):
    request_id: str
    error_code: str
    message: str
    details: Optional[Any] = None
