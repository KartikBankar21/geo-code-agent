import packages.execution.executor as executor_module
from packages.execution.executor import Executor


class FakeSandbox:
    """Stands in for the real Docker-backed Sandbox in tests."""

    def __init__(self, response=None, raise_error=None):
        self._response = response or {"status": "success", "stdout": "ok\n", "stderr": ""}
        self._raise_error = raise_error
        self.started = False
        self.stopped = False
        self.last_code = None

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def execute(self, code):
        self.last_code = code

        if self._raise_error is not None:
            raise self._raise_error

        return self._response


def _executor_with_fake_sandbox(monkeypatch, fake_sandbox):
    monkeypatch.setattr(
        executor_module,
        "Sandbox",
        lambda: fake_sandbox,
    )
    monkeypatch.setattr(
        executor_module,
        "snapshot_artifacts",
        lambda: set(),
    )
    monkeypatch.setattr(
        executor_module,
        "collect_new_artifacts",
        lambda before: [],
    )

    return Executor()


def test_invalid_code_never_reaches_the_sandbox(monkeypatch):
    fake_sandbox = FakeSandbox()
    executor = _executor_with_fake_sandbox(monkeypatch, fake_sandbox)

    result = executor.execute("import subprocess\nsubprocess.run(['ls'])")

    assert result.status == "validation_error"
    assert "subprocess" in result.error_message
    assert fake_sandbox.last_code is None


def test_valid_code_is_forwarded_to_the_sandbox(monkeypatch):
    fake_sandbox = FakeSandbox(
        response={"status": "success", "stdout": "6533\n", "stderr": ""}
    )
    executor = _executor_with_fake_sandbox(monkeypatch, fake_sandbox)

    code = "import geopandas as gpd\nprint(6533)"
    result = executor.execute(code)

    assert fake_sandbox.last_code == code
    assert result.status == "success"
    assert result.stdout == "6533\n"


def test_sandbox_exception_is_reported_as_sandbox_error(monkeypatch):
    fake_sandbox = FakeSandbox(raise_error=RuntimeError("worker crashed"))
    executor = _executor_with_fake_sandbox(monkeypatch, fake_sandbox)

    result = executor.execute("import geopandas as gpd")

    assert result.status == "sandbox_error"
    assert result.error_type == "RuntimeError"
    assert "worker crashed" in result.error_message
