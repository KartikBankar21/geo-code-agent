import os
import subprocess
from pathlib import Path

from ollama import Client

from packages.agent.llm.base import LLMProvider


DEFAULT_PORT = 11434


def _is_wsl() -> bool:
    """Detect whether we're running inside WSL (any version)."""
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _detect_wsl2_windows_host_ip() -> str | None:
    """
    Best-effort detection of the Windows host IP as seen from inside WSL2.

    In WSL2's default NAT networking mode, the Windows host is reachable
    at the default gateway IP, which the Windows OS re-assigns on every
    reboot. Reading it at runtime (instead of hardcoding it) is what
    makes this survive a reboot.

    This has no effect under WSL2 "mirrored" networking mode, where the
    Windows host is already reachable at localhost — in that case this
    function is simply not needed, and `localhost` is used instead.
    """

    try:
        output = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=1,
            check=True,
        ).stdout.split()

        if "via" in output:
            return output[output.index("via") + 1]

    except (OSError, subprocess.SubprocessError):
        return None

    return None


def _default_ollama_host() -> str:
    """
    Resolve a sensible default Ollama host without hardcoding a
    machine-specific IP.

    Priority:
    1. OLLAMA_HOST environment variable, if set (handled by the caller).
    2. Auto-detected WSL2 Windows-host IP, if running inside WSL2 NAT mode.
    3. http://localhost:11434 (covers native Linux, WSL2 mirrored
       networking, and Ollama running in the same environment as the
       agent).
    """

    if _is_wsl():
        host_ip = _detect_wsl2_windows_host_ip()

        if host_ip:
            return f"http://{host_ip}:{DEFAULT_PORT}"

    return f"http://localhost:{DEFAULT_PORT}"


class OllamaProvider(LLMProvider):
    """
    LLM provider for locally hosted Ollama models.

    Ollama commonly runs on Windows while the agent runs inside WSL, or
    both run on the same machine directly. See `_default_ollama_host`
    for how the host is resolved when OLLAMA_HOST is not set.
    """

    def __init__(self):
        host = os.getenv("OLLAMA_HOST") or _default_ollama_host()

        model = os.getenv(
            "OLLAMA_MODEL",
            "qwen3.5:4b",
        )

        self.client = Client(host=host)
        self.model = model
        self.host = host

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
            )
        except Exception as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host} "
                f"(model={self.model}). If this host is wrong, set "
                f"OLLAMA_HOST explicitly in .env. Original error: {e}"
            ) from e

        text = response.get("response", "")

        if not text:
            raise RuntimeError(
                "Ollama returned an empty response."
            )

        return text.strip()
