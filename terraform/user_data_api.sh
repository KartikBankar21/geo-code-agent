#!/bin/bash
set -euxo pipefail

apt-get update -y
apt-get install -y git python3-pip python3-venv libexpat1

cd /opt
git clone -b "${repo_branch}" "${repo_url}" geo-code-agent
cd /opt/geo-code-agent

mkdir -p data/raw data/outputs

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-api.txt

cat <<EOF > /opt/geo-code-agent/.env
LLM_PROVIDER=groq
GROQ_API_KEY=${groq_api_key}
GROQ_MODEL=${groq_model}
QDRANT_URL=${qdrant_url}
QDRANT_API_KEY=${qdrant_api_key}
QDRANT_CLOUD_INFERENCE=true
QDRANT_CLOUD_MODEL=sentence-transformers/all-minilm-l6-v2
SANDBOX_EXECUTOR_URL=http://${exec_private_ip}:8001
EXECUTOR_SHARED_SECRET=${executor_secret}
S3_ARTIFACTS_BUCKET=${s3_bucket}
AWS_REGION=${aws_region}
CORS_ORIGINS=${vercel_origin}
EOF

cat <<EOF > /etc/systemd/system/geo-api.service
[Unit]
Description=Geo Agent Tier 2 Web API & LangGraph Node
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/geo-code-agent
EnvironmentFile=/opt/geo-code-agent/.env
ExecStart=/opt/geo-code-agent/.venv/bin/uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable geo-api
systemctl start geo-api