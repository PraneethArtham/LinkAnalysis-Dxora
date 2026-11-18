"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class LLMResponse:
    """Standard response from any LLM provider."""

    analysis: dict = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    response_time_ms: float = 0.0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    error: Optional[str] = None
    success: bool = True


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All LLM provider implementations must inherit from this class
    and implement the ``generate`` method.
    """

    provider_name: str = ""
    model_name: str = ""
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated API cost based on token usage.

        Args:
            input_tokens: Number of input (prompt) tokens.
            output_tokens: Number of output (completion) tokens.

        Returns:
            Estimated cost in USD.
        """
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_million
        return round(input_cost + output_cost, 6)

    def parse_json_response(self, text: str) -> dict:
        """Parse JSON from LLM response text.

        Handles markdown code block wrapping that some models add.

        Args:
            text: Raw LLM response text.

        Returns:
            Parsed dictionary from the JSON content.

        Raises:
            json.JSONDecodeError: If the text is not valid JSON.
        """
        text = text.strip()

        # Remove markdown code block wrapping if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    return item
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @abstractmethod
    async def generate(self, prompt: str) -> LLMResponse:
        """Generate analysis from the given prompt.

        Args:
            prompt: The analysis prompt with website content.

        Returns:
            LLMResponse with analysis results and metrics.
        """
        pass
