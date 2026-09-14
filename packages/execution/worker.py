import io
import json
import signal
import sys
from contextlib import redirect_stdout, redirect_stderr


namespace = {"__name__": "__main__"}


class ExecutionTimeout(Exception):
    """Raised when code execution exceeds the configured timeout."""


def _timeout_handler(signum, frame):
    raise ExecutionTimeout("Code execution timed out")


for line in sys.stdin:
    request = json.loads(line)

    stdout = io.StringIO()
    stderr = io.StringIO()

    timeout = request.get("timeout")

    if timeout is not None:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout)

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(request["code"], namespace)

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