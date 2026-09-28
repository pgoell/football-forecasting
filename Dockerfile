# Backtest dashboard. Reads data/ (mounted read-only), never writes.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HOME=/tmp

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8501
CMD ["/app/.venv/bin/streamlit", "run", "src/football_forecasting/dashboard.py", \
     "--server.address", "0.0.0.0", "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
