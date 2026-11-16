FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 YOLO_CONFIG_DIR=/tmp/Ultralytics SAFEVISION_DEMO=true
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1     && rm -rf /var/lib/apt/lists/*     && useradd --create-home --uid 1000 safevision
COPY pyproject.toml ./
RUN pip install --no-cache-dir torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
COPY safevision/ safevision/
RUN pip install --no-cache-dir '.[onnx]'
COPY alembic.ini ./
COPY migrations/ migrations/
COPY scripts/ scripts/
COPY docs/ASSETS.md docs/ASSETS.md
COPY --from=frontend /build/dist frontend/dist/
COPY --from=frontend /build/public/examples frontend/public/examples/
RUN mkdir models && chown safevision:safevision models
USER safevision
RUN python scripts/fetch_model.py
EXPOSE 7860
CMD ["uvicorn", "safevision.api:app", "--host", "0.0.0.0", "--port", "7860", "--ws-max-size", "1048576"]
