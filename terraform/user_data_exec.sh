#!/bin/bash
set -euxo pipefail

apt-get update -y
apt-get install -y docker.io git python3-pip python3-venv

systemctl enable docker
systemctl start docker

cd /opt
git clone -b "${repo_branch}" "${repo_url}" geo-code-agent
cd /opt/geo-code-agent

mkdir -p data/raw data/sandbox_projects

# Build the isolated GeoPandas/Shapely/Rasterio sandbox image
docker build -t geo-agent-sandbox:dev -f packages/execution/Dockerfile.sandbox .

# Lightweight venv for the Tier 3 pool manager API
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install fastapi "uvicorn[standard]" python-multipart boto3 pydantic opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-logging

cat <<EOF > /etc/systemd/system/geo-executor.service
[Unit]
Description=Geo Agent Tier 3 Sandbox Pool Executor
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/geo-code-agent
Environment="EXECUTOR_SHARED_SECRET=${executor_secret}"
Environment="S3_ARTIFACTS_BUCKET=${s3_bucket}"
Environment="AWS_REGION=${aws_region}"
Environment="SANDBOX_POOL_SIZE=2"
Environment="SANDBOX_MEMORY_LIMIT=1g"
Environment="SANDBOX_IDLE_TTL_SECONDS=900"
Environment="OTEL_EXPORTER_OTLP_ENDPOINT=${otel_endpoint}"
Environment="OTEL_EXPORTER_OTLP_HEADERS=${otel_headers}"
ExecStart=/opt/geo-code-agent/.venv/bin/uvicorn apps.executor_service.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable geo-executor
systemctl start geo-executor