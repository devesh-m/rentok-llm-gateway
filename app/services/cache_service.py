import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.models.key import ResponseCache, utc_now
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse

STOPWORDS = {
    "a", "an", "the", "please", "can", "you", "could", "would", "tell", "me",
    "explain", "describe", "what", "is", "are", "does", "do", "in", "to", "for",
    "of", "on", "with", "about", "briefly", "simply", "just",
}
NEGATIONS = {"not", "no", "never", "without", "dont", "don't", "isnt", "isn't", "cannot", "cant"}


def extract_normalized_prompt_text(request: ChatCompletionRequest) -> str:
    """Extract concatenated user/system messages for semantic similarity comparison."""
    return " ".join(f"{m.role.strip().lower()}: {m.content.strip().lower()}" for m in request.messages)


def _tokenize_and_ngrams(text: str) -> Counter:
    """Build a combined feature vector of content words and character 3-grams for cosine similarity."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = [w for w in cleaned.split() if w and w not in STOPWORDS]
    features = Counter()
    for w in words:
        # Weight content words strongly
        stem = w[:-1] if len(w) > 4 and w.endswith("s") else w
        features[f"w:{stem}"] += 2.0
        # Character 3-grams capture morphological variations
        if len(stem) >= 3:
            for i in range(len(stem) - 2):
                features[f"g:{stem[i:i+3]}"] += 0.5
    return features


def compute_semantic_similarity(text_a: str, text_b: str) -> float:
    """
    Compute hybrid word-stem + character n-gram cosine similarity in [0.0, 1.0].
    Includes a negation polarity check so 'What is X?' never matches 'What is NOT X?'.
    """
    words_a = set(re.findall(r"[a-z']+", text_a.lower()))
    words_b = set(re.findall(r"[a-z']+", text_b.lower()))
    if bool(words_a & NEGATIONS) != bool(words_b & NEGATIONS):
        return 0.0

    vec_a = _tokenize_and_ngrams(text_a)
    vec_b = _tokenize_and_ngrams(text_b)
    if not vec_a or not vec_b:
        return 0.0

    intersection = set(vec_a.keys()) & set(vec_b.keys())
    dot = sum(vec_a[k] * vec_b[k] for k in intersection)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def generate_prompt_hash(request: ChatCompletionRequest) -> str:
    """Generate a deterministic SHA-256 hash for a normalized chat completion request."""
    normalized_messages = [
        {"role": m.role.strip().lower(), "content": m.content.strip()}
        for m in request.messages
    ]
    payload = {
        "model": (request.model or settings.PRIMARY_MODEL).strip().lower(),
        "messages": normalized_messages,
        "temperature": request.temperature,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CacheService:
    """Manages two-tier caching (Exact SHA-256 + Semantic Cosine Similarity), TTL, and cost savings."""

    SEMANTIC_THRESHOLD = 0.72

    async def get(
        self,
        session: AsyncSession,
        prompt_hash: str,
        request: Optional[ChatCompletionRequest] = None,
    ) -> Optional[Tuple[ChatCompletionResponse, float]]:
        """
        Check if an exact or semantically equivalent cached response exists and is valid.
        Returns: (cached_response, cost_saved) or None
        """
        if not settings.CACHE_ENABLED:
            return None

        now = utc_now()

        # 1. Tier-1: Fast O(1) Exact-Match Lookup
        query = select(ResponseCache).where(
            ResponseCache.prompt_hash == prompt_hash,
            ResponseCache.expires_at > now,
        )
        result = await session.execute(query)
        cache_entry = result.scalars().first()
        match_type = "exact"

        # 2. Tier-2: Semantic Cosine Similarity Lookup over recent active entries
        if not cache_entry and request is not None:
            query_text = extract_normalized_prompt_text(request)
            candidates_q = (
                select(ResponseCache)
                .where(ResponseCache.expires_at > now)
                .order_by(ResponseCache.created_at.desc())
                .limit(50)
            )
            candidates = (await session.execute(candidates_q)).scalars().all()
            best_score = 0.0
            best_entry = None
            for cand in candidates:
                try:
                    payload_dict = json.loads(cand.response_json)
                    cand_prompt = (
                        payload_dict.get("gateway_metadata", {}).get("cached_prompt_text") or ""
                    )
                    if cand_prompt:
                        score = compute_semantic_similarity(query_text, cand_prompt)
                        if score >= self.SEMANTIC_THRESHOLD and score > best_score:
                            best_score = score
                            best_entry = cand
                except Exception:
                    continue

            if best_entry is not None:
                cache_entry = best_entry
                match_type = f"semantic ({best_score:.2f})"

        if not cache_entry:
            return None

        # Cache Hit! Update metrics
        cost_saved = cache_entry.estimated_cost
        cache_entry.hit_count += 1
        cache_entry.cost_saved += cost_saved
        await session.commit()

        response_dict = json.loads(cache_entry.response_json)
        if "gateway_metadata" in response_dict and response_dict["gateway_metadata"]:
            response_dict["gateway_metadata"]["cache_match_type"] = match_type
        response_obj = ChatCompletionResponse(**response_dict)
        return response_obj, cost_saved

    async def set(
        self,
        session: AsyncSession,
        prompt_hash: str,
        model: str,
        response: ChatCompletionResponse,
        cost: float,
        request: Optional[ChatCompletionRequest] = None,
    ) -> None:
        """Store a successful LLM response into the cache with normalized prompt text and TTL."""
        if not settings.CACHE_ENABLED:
            return

        expires_at = utc_now() + timedelta(seconds=settings.CACHE_TTL_SECONDS)

        cleaned_response = response.model_dump()
        if "gateway_metadata" not in cleaned_response or not cleaned_response["gateway_metadata"]:
            cleaned_response["gateway_metadata"] = {}
        cleaned_response["gateway_metadata"]["cached"] = True
        if request is not None:
            cleaned_response["gateway_metadata"]["cached_prompt_text"] = extract_normalized_prompt_text(
                request
            )

        existing_q = select(ResponseCache).where(ResponseCache.prompt_hash == prompt_hash)
        existing = (await session.execute(existing_q)).scalars().first()
        if existing:
            return

        cache_entry = ResponseCache(
            prompt_hash=prompt_hash,
            model=model,
            response_json=json.dumps(cleaned_response),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            estimated_cost=cost,
            hit_count=0,
            cost_saved=0.0,
            expires_at=expires_at,
        )
        session.add(cache_entry)
        await session.commit()


cache_service = CacheService()
