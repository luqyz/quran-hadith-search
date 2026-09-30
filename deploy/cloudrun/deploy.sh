#!/usr/bin/env bash
# Deploy API ke Cloud Run. Jalankan dalam Google Cloud Shell dari root repo:
#   bash deploy/cloudrun/deploy.sh
set -euo pipefail

SERVICE=quran-hadith-api
REGION=asia-southeast1
ARTIFACT_REPO=${ARTIFACT_REPO:-luqyz/quran-hadith-artifacts}

BUILD_DIR=$(mktemp -d)
cp deploy/space/Dockerfile deploy/space/requirements.txt "$BUILD_DIR"/
mkdir -p "$BUILD_DIR/src"
cp -r src/retrieval src/app "$BUILD_DIR/src/"
find "$BUILD_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +

gcloud run deploy "$SERVICE" \
  --source "$BUILD_DIR" \
  --region "$REGION" \
  --port 7860 \
  --memory 4Gi --cpu 2 --cpu-boost \
  --min-instances 0 --max-instances 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --update-env-vars "ARTIFACT_REPO=${ARTIFACT_REPO}" \
  --set-secrets "HF_TOKEN=hf-token:latest"