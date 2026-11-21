import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import boto3
from botocore.config import Config

IMAGE_NAME = os.getenv("SANDBOX_IMAGE", "geo-agent-sandbox:dev")
POOL_SIZE = int(os.getenv("SANDBOX_POOL_SIZE", "2"))
MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "1g")
SWAP_LIMIT = os.getenv("SANDBOX_SWAP_LIMIT", "1g")
CPU_LIMIT = os.getenv("SANDBOX_CPU_LIMIT", "1.0")
PIDS_LIMIT = os.getenv("SANDBOX_PIDS_LIMIT", "64")
IDLE_TTL_SECONDS = int(os.getenv("SANDBOX_IDLE_TTL_SECONDS", "900"))  # 15 minutes

PROJECT_ROOT = Path(os.path.abspath(".")).resolve()
INPUT_DIR = PROJECT_ROOT / "data" / "raw"
PROJECTS_HOST_DIR = PROJECT_ROOT / "data" / "sandbox_projects"

S3_BUCKET = os.getenv("S3_ARTIFACTS_BUCKET", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")


class WarmContainer:
    """Represents one persistent warmed Docker container in the pool."""

    def __init__(self, slot: int):
        self.slot = slot
        self.container_name = f"geo-agent-pool-{slot}"
        self.worker_process: subprocess.Popen | None = None
        self.exec_lock = threading.Lock()

    def start(self):
        # Remove any stale container with the same slot name from an ungraceful exit
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            text=True,
        )

        subprocess.run(
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
                "--mount",
                f"type=bind,source={INPUT_DIR},target=/sandbox/input,readonly",
                "--mount",
                f"type=bind,source={PROJECTS_HOST_DIR},target=/sandbox/projects",
                IMAGE_NAME,
                "python",
                "-c",
                "import time; time.sleep(86400)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        subprocess.run(
            [
                "docker",
                "cp",
                str(PROJECT_ROOT / "packages" / "execution" / "worker.py"),
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

    def send_command(self, payload: dict) -> dict:
        with self.exec_lock:
            if self.worker_process is None or self.worker_process.poll() is not None:
                self.start()

            self.worker_process.stdin.write(json.dumps(payload) + "\n")
            self.worker_process.stdin.flush()

            line = self.worker_process.stdout.readline()
            if not line:
                # Worker died (e.g., OOM); restart container cleanly and report error
                self.start()
                return {
                    "status": "error",
                    "stdout": "",
                    "stderr": "",
                    "error_type": "SandboxWorkerCrash",
                    "error_message": "Sandbox worker terminated unexpectedly (possible memory limit exceeded).",
                }

            return json.loads(line)

    def stop(self):
        if self.worker_process is not None:
            self.worker_process.terminate()
            self.worker_process.wait(timeout=5)
            self.worker_process = None

        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            text=True,
        )


class SandboxPoolManager:
    """
    Manages a fixed pool of warmed containers with consistent-hashing session
    routing, S3 artifact uploads, and a 15-minute background cleaner daemon.
    """

    def __init__(self):
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        PROJECTS_HOST_DIR.mkdir(parents=True, exist_ok=True)

        self.containers: list[WarmContainer] = [
            WarmContainer(slot) for slot in range(POOL_SIZE)
        ]
        self.last_activity: dict[str, float] = {}
        self.activity_lock = threading.Lock()
        self._stop_cleaner = threading.Event()
        self._cleaner_thread: threading.Thread | None = None

        self.s3 = (
            boto3.client(
                "s3",
                region_name=AWS_REGION,
                config=Config(signature_version="s3v4"),
            )
            if S3_BUCKET
            else None
        )

    def start(self):
        for container in self.containers:
            container.start()

        self._cleaner_thread = threading.Thread(
            target=self._cleaner_loop, daemon=True
        )
        self._cleaner_thread.start()

    def stop(self):
        self._stop_cleaner.set()
        if self._cleaner_thread is not None:
            self._cleaner_thread.join(timeout=3)
        for container in self.containers:
            container.stop()

    def _route_container(self, conversation_id: str) -> WarmContainer:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
        slot = int(digest, 16) % len(self.containers)
        return self.containers[slot]

    def _touch_session(self, conversation_id: str):
        with self.activity_lock:
            self.last_activity[conversation_id] = time.time()

    def _snapshot_outputs(self, output_dir: Path) -> dict[str, float]:
        if not output_dir.exists():
            return {}
        return {
            p.name: p.stat().st_mtime
            for p in output_dir.iterdir()
            if p.is_file()
        }

    def _upload_artifacts_to_s3(
        self,
        conversation_id: str,
        turn_id: str,
        output_dir: Path,
        changed_files: list[str],
    ) -> tuple[list[str], list[dict]]:
        artifact_uris: list[str] = []
        presigned_items: list[dict] = []

        for filename in sorted(changed_files):
            local_path = output_dir / filename
            if not local_path.exists():
                continue

            if self.s3 and S3_BUCKET:
                s3_key = f"artifacts/{conversation_id}/{turn_id}/{filename}"
                self.s3.upload_file(str(local_path), S3_BUCKET, s3_key)
                presigned_url = self.s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": s3_key},
                    ExpiresIn=3600,
                )
                s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
                artifact_uris.append(s3_uri)
                presigned_items.append(
                    {
                        "filename": filename,
                        "s3_uri": s3_uri,
                        "presigned_url": presigned_url,
                    }
                )
            else:
                artifact_uris.append(str(local_path))

        return artifact_uris, presigned_items

    def execute(
        self,
        conversation_id: str,
        turn_id: str,
        code: str,
        timeout: float = 60.0,
    ) -> dict:
        self._touch_session(conversation_id)

        project_host_dir = PROJECTS_HOST_DIR / conversation_id
        output_host_dir = project_host_dir / "output"
        output_host_dir.mkdir(parents=True, exist_ok=True)

        before = self._snapshot_outputs(output_host_dir)
        container = self._route_container(conversation_id)

        start = time.perf_counter()
        raw_result = container.send_command(
            {
                "action": "execute",
                "conversation_id": conversation_id,
                "code": code,
                "timeout": timeout,
            }
        )
        elapsed = time.perf_counter() - start
        self._touch_session(conversation_id)

        after = self._snapshot_outputs(output_host_dir)
        # Detect BOTH newly created files AND overwritten files (newer mtime)
        changed_files = [
            fname
            for fname, mtime in after.items()
            if fname not in before or mtime > before[fname]
        ]

        artifact_uris, presigned_items = self._upload_artifacts_to_s3(
            conversation_id=conversation_id,
            turn_id=turn_id,
            output_dir=output_host_dir,
            changed_files=changed_files,
        )

        return {
            "status": raw_result.get("status", "error"),
            "stdout": raw_result.get("stdout", ""),
            "stderr": raw_result.get("stderr", ""),
            "error_type": raw_result.get("error_type"),
            "error_message": raw_result.get("error_message"),
            "execution_time": elapsed,
            "artifacts": artifact_uris,
            "artifact_urls": presigned_items,
            "container_slot": container.slot,
        }

    def cleanup_session(self, conversation_id: str) -> None:
        container = self._route_container(conversation_id)
        try:
            container.send_command(
                {"action": "cleanup", "conversation_id": conversation_id}
            )
        except Exception:
            pass

        project_host_dir = PROJECTS_HOST_DIR / conversation_id
        if project_host_dir.exists():
            shutil.rmtree(project_host_dir, ignore_errors=True)

        with self.activity_lock:
            self.last_activity.pop(conversation_id, None)

    def _cleaner_loop(self):
        """Purge sandbox project directories idle for > 15 minutes."""
        while not self._stop_cleaner.wait(timeout=60):
            now = time.time()
            with self.activity_lock:
                expired = [
                    cid
                    for cid, ts in self.last_activity.items()
                    if (now - ts) > IDLE_TTL_SECONDS
                ]

            for cid in expired:
                print(f"[CLEANER] Purging idle sandbox session: {cid}")
                self.cleanup_session(cid)