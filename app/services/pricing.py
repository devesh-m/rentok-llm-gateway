from typing import Dict, Tuple

# Pricing Matrix per 1 Million Tokens (in USD)
# Format: (prompt_cost_per_million, completion_cost_per_million)
MODEL_PRICING_PER_1M: Dict[str, Tuple[float, float]] = {
    # Groq Models
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama3-70b-8192": (0.59, 0.79),
    "llama3-8b-8192": (0.05, 0.08),
    "mixtral-8x7b-32768": (0.24, 0.24),

    # Google Gemini Models (OpenAI-compatible endpoint)
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),

    # Fallback / Default generic model pricing
    "default": (0.10, 0.20),
}


def get_model_rates(model_name: str) -> Tuple[float, float]:
    """Retrieve (prompt_rate_per_token, completion_rate_per_token) for a given model."""
    normalized = model_name.lower().strip()
    
    # Direct match
    if normalized in MODEL_PRICING_PER_1M:
        prompt_1m, comp_1m = MODEL_PRICING_PER_1M[normalized]
        return prompt_1m / 1_000_000.0, comp_1m / 1_000_000.0

    # Substring match (e.g., if model is prefixed like "accounts/fireworks/models/...")
    for key, (prompt_1m, comp_1m) in MODEL_PRICING_PER_1M.items():
        if key in normalized:
            return prompt_1m / 1_000_000.0, comp_1m / 1_000_000.0

    prompt_1m, comp_1m = MODEL_PRICING_PER_1M["default"]
    return prompt_1m / 1_000_000.0, comp_1m / 1_000_000.0


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate the estimated total cost in USD for a given request."""
    rate_in, rate_out = get_model_rates(model_name)
    total_cost = (prompt_tokens * rate_in) + (completion_tokens * rate_out)
    return round(total_cost, 8)

