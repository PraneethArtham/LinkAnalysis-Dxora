"""Groq (GPT-OSS 120B) LLM provider implementation."""

import json
import time

from openai import AsyncOpenAI

from app.services.llm.base import BaseLLMProvider, LLMResponse
from app.config import settings


class GroqProvider(BaseLLMProvider):
    """Groq GPT-OSS 120B provider.

    Uses the OpenAI-compatible Groq API for ultra-fast inference
    powered by Groq's custom LPU hardware (~500 tokens/sec).

    Pricing (per 1M tokens): Input $0.15 | Output $0.60
    Context window: 131,072 tokens | Free tier available
    """

    provider_name = "Groq"
    model_name = "openai/gpt-oss-120b"
    input_cost_per_million = 0.15
    output_cost_per_million = 0.60

    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured")
        self.client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    async def generate(self, prompt: str) -> LLMResponse:
        """Generate analysis using GPT-OSS 120B on Groq."""
        start_time = time.time()

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert business analyst specializing in "
                            "website analysis, competitive intelligence, SEO, and "
                            "digital marketing. Always respond with valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4096,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Parse response
            text = response.choices[0].message.content
            analysis = json.loads(text)

            # Token usage
            input_tokens = None
            output_tokens = None
            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            cost = None
            if input_tokens is not None and output_tokens is not None:
                cost = self.calculate_cost(input_tokens, output_tokens)

            return LLMResponse(
                analysis=analysis,
                provider=self.provider_name,
                model=self.model_name,
                response_time_ms=round(elapsed_ms, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=cost,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                provider=self.provider_name,
                model=self.model_name,
                response_time_ms=round(elapsed_ms, 2),
                error=f"Groq API error: {str(e)}",
                success=False,
            )
