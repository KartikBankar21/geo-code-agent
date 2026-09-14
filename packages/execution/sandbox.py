import os
import json
import subprocess
import uuid


IMAGE_NAME = "geo-agent-sandbox:dev"

MEMORY_LIMIT = "1g"
CPU_LIMIT = "1.0"
PIDS_LIMIT = "64"
SWAP_LIMIT = "1g"

PROJECT_ROOT = os.path.abspath(".")
INPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "outputs")

# 10s was too tight for real-world GIS workloads (e.g. a spatial join or
# reprojection over tens of thousands of features can legitimately take
# longer than that) and caused correct code to be killed and retried.
# Override with the SANDBOX_TIMEOUT_SECONDS env var if needed.
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_TIMEOUT_SECONDS", "60"))

class Sandbox:
    """Manage a persistent Docker sandbox and Python worker."""

    def __init__(self):
        self.container_name = f"geo-agent-{uuid.uuid4().hex[:12]}"
        self.container_process = None
        self.worker_process = None

    def start(self):
        """Start the Docker container and persistent Python worker."""

        self.container_process = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "--network",
                "none",
                "--memory",
                MEMORY_LIMIT,
                "--memory-swap",
                SWAP_LIMIT,
                "--cpus",
                CPU_LIMIT,
                "--pids-limit",
                PIDS_LIMIT,
                # Read-only access to input datasets
                "--mount",
                f"type=bind,source={INPUT_DIR},target=/sandbox/input,readonly",

                "--mount",
                f"type=bind,source={OUTPUT_DIR},target=/sandbox/output",
                IMAGE_NAME,
                "python",
                "-c",
                "import time; time.sleep(3600)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Copy the persistent worker into the running container.
        subprocess.run(
            [
                "docker",
                "cp",
                "packages/execution/worker.py",
                f"{self.container_name}:/sandbox/worker.py",
            ],
            check=True,
        )

        self.worker_process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                self.container_name,
                "python",
                "-u",
                "/sandbox/worker.py",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        return self.container_process.stdout.strip()
    
    def execute(
        self,
        code: str,
        timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict:
        """Execute code in the persistent sandbox worker."""

        if self.worker_process is None:
            raise RuntimeError("Sandbox is not running")

        request = {
            "code": code,
            "timeout": timeout,
        }

        self.worker_process.stdin.write(
            json.dumps(request) + "\n"
        )
        self.worker_process.stdin.flush()

        response = self.worker_process.stdout.readline()

        if not response:
            raise RuntimeError("Worker process exited unexpectedly")

        return json.loads(response)
    
    
    
    def stop(self):
        """Stop and remove the sandbox container."""

        if self.worker_process is not None:
            self.worker_process.terminate()
            self.worker_process.wait()

            self.worker_process = None

        if self.container_process is not None:
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                capture_output=True,
                text=True,
            )

            self.container_process = None