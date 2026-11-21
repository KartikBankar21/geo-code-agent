import os
from groq import Groq
from packages.agent.llm.base import LLMProvider

DEFAULT_MODEL = "openai/gpt-oss-20b"


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
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": 1024,
        }

        # Apply low reasoning effort for gpt-oss reasoning models so reasoning
        # tokens do not consume the output budget needed for Python code.
        if "gpt-oss" in self.model:
            kwargs["reasoning_effort"] = "low"

        response = self.client.chat.completions.create(**kwargs)

        text = response.choices[0].message.content
        if not text:
            raise RuntimeError("Groq returned an empty response.")

        return text.strip()