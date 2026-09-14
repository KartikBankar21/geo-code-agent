import time
from dataclasses import dataclass

from packages.execution.artifacts import (
    collect_new_artifacts,
    snapshot_artifacts,
)
from packages.execution.sandbox import Sandbox
from packages.execution.validator import validate_code


@dataclass
class ExecutionResult:
    status: str
    stdout: str
    stderr: str
    error_type: str | None
    error_message: str | None
    execution_time: float
    artifacts: list[str]


class Executor:
    """Coordinate validation, sandbox execution, and artifact collection."""

    def __init__(self):
        self.sandbox = Sandbox()

    def start(self):
        """Start the persistent execution sandbox."""
        self.sandbox.start()

    def stop(self):
        """Stop the execution sandbox."""
        self.sandbox.stop()

    def execute(
        self,
        code: str,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """
        Validate and execute generated Python code.

        Validation happens on the host before the code is sent
        to the Docker sandbox. `timeout` overrides the sandbox's
        default execution timeout (in seconds) when provided.
        """

        validation = validate_code(code)

        if not validation.valid:
            violations = []

            if validation.syntax_error:
                violations.append(
                    f"Syntax error: {validation.syntax_error}"
                )

            if validation.import_violations:
                violations.append(
                    "Disallowed imports: "
                    + ", ".join(validation.import_violations)
                )

            if validation.dangerous_operations:
                violations.append(
                    "Dangerous operations: "
                    + ", ".join(validation.dangerous_operations)
                )

            return ExecutionResult(
                status="validation_error",
                stdout="",
                stderr="",
                error_type="ValidationError",
                error_message="; ".join(violations),
                execution_time=0.0,
                artifacts=[],
            )

        before_artifacts = snapshot_artifacts()

        start = time.perf_counter()

        try:
            if timeout is not None:
                result = self.sandbox.execute(code, timeout=timeout)
            else:
                result = self.sandbox.execute(code)

        except Exception as e:
            execution_time = time.perf_counter() - start

            return ExecutionResult(
                status="sandbox_error",
                stdout="",
                stderr="",
                error_type=type(e).__name__,
                error_message=str(e),
                execution_time=execution_time,
                artifacts=[],
            )

        execution_time = time.perf_counter() - start

        new_artifacts = collect_new_artifacts(before_artifacts)

        return ExecutionResult(
            status=result["status"],
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            error_type=result.get("error_type"),
            error_message=result.get("error_message"),
            execution_time=execution_time,
            artifacts=new_artifacts,
        )