# ---- Build stage ----
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- Run stage ----
FROM python:3.12-slim
WORKDIR /app

# Copy only installed packages
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy app code
COPY app/ ./app/
COPY static/ ./static/
COPY knowledge/ ./knowledge/
COPY .env.example ./

# Create .env from env vars at runtime (for Railway/Render)
COPY <<'ENTRY' /app/entrypoint.sh
#!/bin/bash
# Generate .env from environment variables if not exists
if [ ! -f .env ]; then
  echo "OPENAI_API_KEY=${OPENAI_API_KEY:-}" > .env
  echo "OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.deepseek.com/v1}" >> .env
  echo "LLM_MODEL=${LLM_MODEL:-deepseek-chat}" >> .env
  echo "LLM_PROVIDER=${LLM_PROVIDER:-deepseek}" >> .env
fi
exec python -m app.main
ENTRY
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENV PORT=8000
ENV HOST=0.0.0.0

CMD ["/app/entrypoint.sh"]
