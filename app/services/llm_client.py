import time
import uuid
import logging
from typing import Tuple, Dict, Any, Optional
import httpx
from fastapi import HTTPException
from app.config import settings
from app.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    UsageInfo,
)
from app.services.pricing import calculate_cost

logger = logging.getLogger("llm_gateway.proxy")


class LLMProxyClient:
    """Handles upstream HTTP forwarding to LLM providers with automatic fallback resilience."""

    def __init__(self):
        self.timeout = httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS, connect=5.0)

    async def call_llm(
        self, request: ChatCompletionRequest
    ) -> Tuple[ChatCompletionResponse, str, float, float]:
        """
        Attempts primary provider (Groq). If it errors, rate limits, or times out,
        gracefully falls back to secondary provider (Gemini).
        Returns: (response, provider_used, latency_ms, cost_usd)
        """
        start_time = time.perf_counter()

        # -------------------------------------------------------------
        # 1. Attempt Primary Provider: Groq
        # -------------------------------------------------------------
        if settings.GROQ_API_KEY:
            try:
                response, latency_ms, cost = await self._call_groq(request, start_time)
                return response, "groq", latency_ms, cost
            except Exception as exc:
                logger.warning(
                    f"Primary provider (Groq) failed with: {str(exc)}. Falling back to secondary provider."
                )
        else:
            logger.info("GROQ_API_KEY not configured. Checking secondary provider.")

        # -------------------------------------------------------------
        # 2. Attempt Secondary Fallback Provider: Google Gemini
        # -------------------------------------------------------------
        if settings.GEMINI_API_KEY:
            try:
                response, latency_ms, cost = await self._call_gemini(request, start_time)
                return response, "gemini", latency_ms, cost
            except Exception as exc:
                logger.warning(
                    f"Secondary provider (Gemini) failed with: {str(exc)}. Checking mock fallback."
                )
        else:
            logger.info("GEMINI_API_KEY not configured. Checking mock fallback.")

        # -------------------------------------------------------------
        # 3. Offline / Dev Mock Fallback (Fail-Safe Resilience)
        # -------------------------------------------------------------
        if settings.ENABLE_MOCK_FALLBACK:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            response, cost = self._generate_mock_response(request, latency_ms)
            return response, "mock", latency_ms, cost

        # If all options exhausted and mock disabled:
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "message": "All upstream LLM providers failed or timed out.",
                    "type": "gateway_upstream_failure",
                    "code": 502,
                }
            },
        )

    async def _call_groq(
        self, request: ChatCompletionRequest, start_time: float
    ) -> Tuple[ChatCompletionResponse, float, float]:
        """Forward request to Groq OpenAI-compatible endpoint."""
        url = f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": request.model or settings.PRIMARY_MODEL,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            # If caller requested a deprecated or non-Groq model name (e.g. gpt-4o or llama-3.3-70b-versatile),
            # automatically route to Groq's active PRIMARY_MODEL (openai/gpt-oss-20b)
            if resp.status_code in (400, 404) and payload["model"] != settings.PRIMARY_MODEL:
                logger.info(
                    f"Model '{payload['model']}' not found on Groq; remapping to '{settings.PRIMARY_MODEL}'"
                )
                payload["model"] = settings.PRIMARY_MODEL
                resp = await client.post(url, headers=headers, json=payload)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            
            cost = calculate_cost(payload["model"], prompt_tokens, completion_tokens)

            choices = [
                Choice(
                    index=c.get("index", 0),
                    message=ChoiceMessage(
                        role=c.get("message", {}).get("role", "assistant"),
                        content=c.get("message", {}).get("content", ""),
                    ),
                    finish_reason=c.get("finish_reason", "stop"),
                )
                for c in data.get("choices", [])
            ]

            response_obj = ChatCompletionResponse(
                id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
                created=data.get("created", int(time.time())),
                model=data.get("model", payload["model"]),
                choices=choices,
                usage=UsageInfo(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ),
                gateway_metadata={
                    "provider": "groq",
                    "latency_ms": round(latency_ms, 2),
                    "cost_usd": cost,
                },
            )
            return response_obj, latency_ms, cost

        # On rate limits or server errors, raise exception to trigger fallback
        raise httpx.HTTPStatusError(
            f"Groq returned HTTP {resp.status_code}: {resp.text}",
            request=resp.request,
            response=resp,
        )

    async def _call_gemini(
        self, request: ChatCompletionRequest, start_time: float
    ) -> Tuple[ChatCompletionResponse, float, float]:
        """Forward request to Google Gemini OpenAI-compatible endpoint."""
        url = f"{settings.GEMINI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
            "Content-Type": "application/json",
        }
        fallback_model = settings.FALLBACK_MODEL
        payload: Dict[str, Any] = {
            "model": fallback_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            
            cost = calculate_cost(fallback_model, prompt_tokens, completion_tokens)

            choices = [
                Choice(
                    index=c.get("index", 0),
                    message=ChoiceMessage(
                        role=c.get("message", {}).get("role", "assistant"),
                        content=c.get("message", {}).get("content", ""),
                    ),
                    finish_reason=c.get("finish_reason", "stop"),
                )
                for c in data.get("choices", [])
            ]

            response_obj = ChatCompletionResponse(
                id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
                created=data.get("created", int(time.time())),
                model=fallback_model,
                choices=choices,
                usage=UsageInfo(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ),
                gateway_metadata={
                    "provider": "gemini",
                    "fallback_triggered": True,
                    "latency_ms": round(latency_ms, 2),
                    "cost_usd": cost,
                },
            )
            return response_obj, latency_ms, cost

        raise httpx.HTTPStatusError(
            f"Gemini returned HTTP {resp.status_code}: {resp.text}",
            request=resp.request,
            response=resp,
        )

    def _generate_mock_response(
        self, request: ChatCompletionRequest, latency_ms: float
    ) -> Tuple[ChatCompletionResponse, float]:
        """Fallback mock generator for local testing or complete upstream outage."""
        # Simple heuristic token estimation (approx 4 chars per token)
        total_prompt_chars = sum(len(m.content) for m in request.messages)
        prompt_tokens = max(1, total_prompt_chars // 4)

        last_user_message = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "Hello",
        )
        content = (
            f"[Mock Fallback Response] Gateway processed prompt: \"{last_user_message[:50]}...\". "
            "Resilience fallback triggered successfully."
        )
        completion_tokens = max(1, len(content) // 4)
        total_tokens = prompt_tokens + completion_tokens

        cost = calculate_cost("default", prompt_tokens, completion_tokens)

        response_obj = ChatCompletionResponse(
            id=f"chatcmpl-mock-{uuid.uuid4().hex[:10]}",
            created=int(time.time()),
            model="mock-fallback-model",
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
            gateway_metadata={
                "provider": "mock",
                "fallback_triggered": True,
                "latency_ms": round(latency_ms, 2),
                "cost_usd": cost,
            },
        )
        return response_obj, cost


llm_client = LLMProxyClient()

