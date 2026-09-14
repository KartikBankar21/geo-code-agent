import os

from google import genai

from packages.agent.llm.base import LLMProvider


MODEL_NAME = "gemini-3.6-flash"


class GeminiProvider(LLMProvider):
    """
    Gemini implementation of the common LLMProvider interface.
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set"
            )

        self.client = genai.Client(
            api_key=api_key
        )

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        if not response.text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        return response.text.strip()