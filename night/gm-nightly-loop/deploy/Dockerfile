FROM oven/bun:1.3.14 AS bun
FROM python:3.12-slim-bookworm
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG GBRAIN_REV=e78f1c38b947b053f3a46881340f74f316be855a
RUN git init /opt/gbrain && cd /opt/gbrain && git remote add origin https://github.com/garrytan/gbrain.git && git fetch --depth 1 origin "$GBRAIN_REV" && git checkout FETCH_HEAD && bun install --frozen-lockfile
RUN printf '#!/bin/sh\nexec bun /opt/gbrain/src/cli.ts "$@"\n' > /usr/local/bin/gbrain && chmod +x /usr/local/bin/gbrain
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir '.[river]'
COPY deploy/entrypoint.py /app/entrypoint.py
RUN useradd --create-home --uid 10001 gm-nightly && mkdir -p /data /training && chown gm-nightly:gm-nightly /data /training
USER gm-nightly
ENV GBRAIN_HOME=/data PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/entrypoint.py"]
CMD ["brain"]
