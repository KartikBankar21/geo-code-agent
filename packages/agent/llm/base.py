import json
from abc import ABC, abstractmethod

def _strip_thinking(text: str) -> str:
    if "<think>" in text and "</think>" in text:
        text = text.split("</think>", 1)[1]

    return text.strip()

class LLMProvider(ABC):
    """
    Common interface for all LLM providers.

    Providers only need to implement generate().
    JSON parsing and code extraction are provider-independent.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate plain text from a prompt."""
        raise NotImplementedError

    def generate_json(self, prompt: str) -> dict:
        """Generate and parse the first JSON object returned by the LLM."""

        text = _strip_thinking(self.generate(prompt))

        # Ideal case: entire response is valid JSON.
        try:
            result = json.loads(text)

            if not isinstance(result, dict):
                raise RuntimeError(
                    "LLM returned valid JSON, but it was not a JSON object."
                )

            return result

        except json.JSONDecodeError:
            pass

        # Handle markdown wrapping or additional text.
        decoder = json.JSONDecoder()

        for index, character in enumerate(text):
            if character != "{":
                continue

            try:
                result, _ = decoder.raw_decode(text[index:])

                if isinstance(result, dict):
                    return result

            except json.JSONDecodeError:
                continue

        raise RuntimeError(
            "LLM returned invalid JSON.\n"
            f"Response:\n{text}"
        )

    def generate_code(self, prompt: str) -> str:
        """Generate Python code and remove Markdown code fences."""

        text = _strip_thinking(self.generate(prompt))

        if "```python" in text:
            text = text.split("```python", 1)[1]

            if "```" in text:
                text = text.split("```", 1)[0]

        elif "```" in text:
            text = text.split("```", 1)[1]

            if "```" in text:
                text = text.split("```", 1)[0]

        return text.strip()
    
