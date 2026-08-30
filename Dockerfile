# ── Stage 1: Build Next.js Static Frontend ──
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python Backend & Static Server (Hugging Face Spaces) ──
FROM python:3.11-slim
WORKDIR /app

# Create a non-root user (Hugging Face Spaces requires UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/app/backend \
    AEGIS_HOST=0.0.0.0 \
    AEGIS_PORT=7860

# Install Python requirements
COPY --chown=user requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --user -r /app/requirements.txt

# Copy backend code, vendor fixtures, and built frontend static assets
COPY --chown=user backend /app/backend
COPY --chown=user vendor /app/vendor
COPY --chown=user --from=frontend-builder /frontend/out /app/frontend/out

# Hugging Face Spaces exposes port 7860
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--app-dir", "/app/backend"]
