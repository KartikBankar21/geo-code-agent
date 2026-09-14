import os

from groq import Groq

from packages.agent.llm.base import LLMProvider


MODEL_NAME = "openai/gpt-oss-20b"


class GroqProvider(LLMProvider):
    """
    Groq implementation of the common LLMProvider interface.
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set"
            )

        self.client = Groq(
            api_key=api_key
        )

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            reasoning_effort="medium",
            max_tokens=900,
        )

        text = response.choices[0].message.content

        if not text:
            raise RuntimeError(
                "Groq returned an empty response."
            )

        return text.strip()