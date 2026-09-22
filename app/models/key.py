from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_value = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False, default="Unnamed Key")
    max_budget = Column(Float, nullable=False, default=1.0)  # In USD
    current_spend = Column(Float, nullable=False, default=0.0)  # In USD
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    def remaining_budget(self) -> float:
        return max(0.0, self.max_budget - self.current_spend)

    def is_exhausted(self) -> bool:
        return self.current_spend >= self.max_budget


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_value = Column(String(128), nullable=False, index=True)
    provider_used = Column(String(64), nullable=False)  # groq, gemini, mock, cache
    model = Column(String(128), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost = Column(Float, nullable=False, default=0.0)  # In USD
    cost_saved = Column(Float, nullable=False, default=0.0)  # In USD (from cache)
    latency_ms = Column(Float, nullable=False, default=0.0)
    status_code = Column(Integer, nullable=False, default=200)
    is_cache_hit = Column(Boolean, nullable=False, default=False)
    timestamp = Column(DateTime, nullable=False, default=utc_now, index=True)


class ResponseCache(Base):
    __tablename__ = "response_cache"

    prompt_hash = Column(String(64), primary_key=True, index=True)
    model = Column(String(128), nullable=False)
    response_json = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=False, default=0.0)
    hit_count = Column(Integer, nullable=False, default=1)
    cost_saved = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)

