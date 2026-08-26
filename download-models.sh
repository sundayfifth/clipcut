#!/usr/bin/env bash
# โหลดโมเดล MediaPipe ที่ clipcut ต้องใช้ (Apache 2.0, จาก Google โดยตรง)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models
base="https://storage.googleapis.com/mediapipe-models"
curl -sSL -o models/efficientdet_lite0.tflite \
  "$base/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite"
echo "โหลดโมเดลเสร็จแล้ว: $(ls -la models/)"
