from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


# -------------------------------------------------------------
# OpenAI-Compatible Chat Completion Schemas
# -------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author (system, user, assistant)")
    content: str = Field(..., description="Content of the message")


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = Field("llama-3.3-70b-versatile", description="Model ID to call")
    model: Optional[str] = Field("openai/gpt-oss-20b", description="Model ID to call")
    messages: List[ChatMessage] = Field(..., description="List of conversation messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    stream: Optional[bool] = Field(False, description="Streaming is explicitly disabled in this minimal gateway")


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: UsageInfo
    # Gateway-added metadata
    gateway_metadata: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------
# Admin & Virtual Key Schemas
# -------------------------------------------------------------
class CreateKeyRequest(BaseModel):
    name: str = Field("API Key", min_length=1, max_length=128)
    max_budget: float = Field(1.0, gt=0.0, description="Spending cap in USD")


class VirtualKeyResponse(BaseModel):
    id: int
    key_value: str
    name: str
    max_budget: float
    current_spend: float
    remaining_budget: float
    is_active: bool
    created_at: datetime


class UsageLogItem(BaseModel):
    id: int
    provider_used: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    latency_ms: float
    is_cache_hit: bool
    cost_saved: float
    timestamp: datetime


class KeyUsageSummaryResponse(BaseModel):
    key_value: str
    name: str
    max_budget_usd: float
    current_spend_usd: float
    remaining_budget_usd: float
    is_exhausted: bool
    total_requests: int
    total_tokens: int
    recent_logs: List[UsageLogItem]


class CacheStatsResponse(BaseModel):
    cache_enabled: bool
    total_cached_entries: int
    total_cache_hits: int
    total_cost_saved_usd: float

