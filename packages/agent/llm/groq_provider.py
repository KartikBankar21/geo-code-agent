import os
import time
from groq import Groq
from packages.agent.llm.base import LLMProvider
from packages.observability.otel import get_meter, traced_span

DEFAULT_MODEL = "openai/gpt-oss-20b"

_meter = get_meter("geo-agent.llm")
_token_counter = _meter.create_counter(
    name="geo_agent.llm.tokens",
    description="LLM tokens consumed by direction (prompt vs completion)",
    unit="1",
)
_llm_duration = _meter.create_histogram(
    name="geo_agent.llm.duration_seconds",
    description="Groq API inference latency in seconds",
    unit="s",
)


class GroqProvider(LLMProvider):
    """Groq implementation of the common LLMProvider interface."""

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        self.client = Groq(api_key=api_key)
        self.model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    def generate(self, prompt: str) -> str:
        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }

        if "gpt-oss" in self.model:
            kwargs["reasoning_effort"] = "low"

        with traced_span("llm.groq.generate", {"gen_ai.request.model": self.model}) as span:
            start = time.perf_counter()
            response = self.client.chat.completions.create(**kwargs)
            elapsed = time.perf_counter() - start

            _llm_duration.record(elapsed, {"model": self.model})

            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
                _token_counter.add(prompt_tokens, {"model": self.model, "type": "prompt"})
                _token_counter.add(completion_tokens, {"model": self.model, "type": "completion"})

            text = response.choices[0].message.content
            if not text:
                raise RuntimeError("Groq returned an empty response.")

            return text.strip()