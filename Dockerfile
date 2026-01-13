FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV VENV_PATH=/opt/venv
ENV MCP_TRANSPORT=sse
ENV MCP_SSE_PATH=/sse
ENV MCP_MESSAGE_PATH=/messages
ENV PORT=8080
ENV HOST=0.0.0.0

WORKDIR /app

# Install dependencies into an isolated virtual environment
COPY requirements.txt .
RUN python -m venv "$VENV_PATH" \
    && "$VENV_PATH/bin/pip" install --upgrade pip \
    && "$VENV_PATH/bin/pip" install --no-cache-dir -r requirements.txt

# Copy the application source
COPY . .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"
ENV MCP_SSE_PATH=/sse
ENV MCP_MESSAGE_PATH=/messages

WORKDIR /app

# Create non-root user for better container security
RUN addgroup --system mcp \
    && adduser --system --ingroup mcp --home /app mcp

# Bring the venv and source code from the builder stage
COPY --from=builder "$VENV_PATH" "$VENV_PATH"
COPY --from=builder /app /app
RUN chown -R mcp:mcp /app "$VENV_PATH"

USER mcp

EXPOSE 8080

ENTRYPOINT ["python", "-m", "start_server"]
