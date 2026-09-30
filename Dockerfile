# Zani Terminal — base TUI + MCP (filesystem, bash, LSP). No Kitty harness assets required.

FROM golang:1.24-bookworm AS mcp_lsp_bridge
ENV GOTOOLCHAIN=auto
RUN go install github.com/isaacphi/mcp-language-server@v0.1.1

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mcp_lsp_bridge /go/bin/mcp-language-server /usr/local/bin/mcp-language-server

WORKDIR /app

COPY pyproject.toml README.md requirements.txt zani.py zani ./
COPY config ./config
COPY core ./core
COPY assets ./assets
COPY tools ./tools

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Project is mounted at run time; default cwd is the workspace root.
WORKDIR /workspace

ENV TERM=xterm-256color \
    PYTHONUNBUFFERED=1 \
    ZANI_DOCKER=1

ENTRYPOINT ["zani"]
CMD ["tui"]
