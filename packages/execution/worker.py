import io
import json
import os
import signal
import sys
from contextlib import redirect_stdout, redirect_stderr

# Per-conversation isolated Python namespaces so variables persist across
# multi-step chunks within a chat without leaking across different chats.
namespaces: dict[str, dict] = {}


class ExecutionTimeout(Exception):
    """Raised when code execution exceeds the configured timeout."""


def _timeout_handler(signum, frame):
    raise ExecutionTimeout("Code execution timed out")


for line in sys.stdin:
    request = json.loads(line)
    action = request.get("action", "execute")
    session_id = request.get("conversation_id", "default")

    if action == "cleanup":
        namespaces.pop(session_id, None)
        print(json.dumps({"status": "cleaned", "conversation_id": session_id}), flush=True)
        continue

    project_dir = f"/sandbox/projects/{session_id}"
    output_dir = f"{project_dir}/output"
    os.makedirs(output_dir, exist_ok=True)

    # Point /sandbox/output symlink to this conversation's isolated output folder
    # so any agent code writing to /sandbox/output/<file> stays session-isolated.
    if os.path.islink("/sandbox/output") or os.path.exists("/sandbox/output"):
        try:
            if os.path.islink("/sandbox/output"):
                os.unlink("/sandbox/output")
        except OSError:
            pass
    if not os.path.exists("/sandbox/output"):
        os.symlink(output_dir, "/sandbox/output")

    os.chdir(project_dir)

    if session_id not in namespaces:
        namespaces[session_id] = {"__name__": "__main__"}

    stdout = io.StringIO()
    stderr = io.StringIO()
    timeout = request.get("timeout", 60)

    if timeout is not None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout)

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(request["code"], namespaces[session_id])

        response = {
            "status": "success",
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

    except ExecutionTimeout as e:
        response = {
            "status": "timeout",
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "error_type": type(e).__name__,
            "error_message": str(e),
        }

    except Exception as e:
        response = {
            "status": "error",
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "error_type": type(e).__name__,
            "error_message": str(e),
        }

    finally:
        if timeout is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)

    print(json.dumps(response), flush=True)