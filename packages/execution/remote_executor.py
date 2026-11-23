import os
import requests

from packages.execution.executor import ExecutionResult
from packages.execution.validator import validate_code
from packages.observability.otel import inject_trace_headers


class RemoteExecutor:
    """Forwards validated Python chunks to Tier 3's Sandbox Pool Manager."""

    def __init__(self, base_url: str, secret: str = ""):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Executor-Secret": secret} if secret else {}

    def execute(
        self,
        code: str,
        conversation_id: str = "default",
        turn_id: str = "default",
        timeout: float = 60.0,
    ) -> ExecutionResult:
        validation = validate_code(code)
        if not validation.valid:
            return ExecutionResult(
                status="validation_error",
                stdout="",
                stderr="",
                error_type="ValidationError",
                error_message="Code failed AST/import/security policy validation.",
                execution_time=0.0,
                artifacts=[],
            )

        resp = requests.post(
            f"{self.base_url}/execute",
            json={
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "code": code,
                "timeout": timeout,
            },
            headers = inject_trace_headers(self.headers),
            timeout=timeout + 15,
        )
        resp.raise_for_status()
        data = resp.json()

        return ExecutionResult(
            status=data["status"],
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            execution_time=data.get("execution_time", 0.0),
            artifacts=data.get("artifacts", []),
        )

    def delete_session(self, conversation_id: str) -> None:
        try:
            requests.delete(
                f"{self.base_url}/sessions/{conversation_id}",
                headers = inject_trace_headers(self.headers),
                timeout=10,
            )
        except Exception:
            pass
