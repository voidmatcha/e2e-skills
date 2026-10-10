# Apache-2.0. Immutable ARM64 Playwright 1.62.0 Noble browser runtime.
FROM mcr.microsoft.com/playwright@sha256:5361940f845a5077926d54746122f7b68a121cc2aa27df6241087b774203fc44
RUN apt-get update && apt-get install --yes --no-install-recommends git python3 ripgrep bash \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/evals/fixtures/package.json scripts/evals/fixtures/package-lock.json /opt/fixtures/
RUN cd /opt/fixtures && npm ci --ignore-scripts && npm install --global @openai/codex@0.159.3
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /work/project
