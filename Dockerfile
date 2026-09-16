FROM ghcr.io/astral-sh/uv:debian-slim
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_CHANNEL=chrome
ENV UV_NO_DEV=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends wget gnupg xvfb x11vnc novnc \
  && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y /tmp/chrome.deb \
  && rm /tmp/chrome.deb /var/lib/apt/lists/* -rf \
  && google-chrome --version
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY agent-entrypoint.sh ./
COPY src/ ./src/
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "--app-dir", "src", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
