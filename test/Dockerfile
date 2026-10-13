# Playwright runner for docker-compose.test.yml. Keep the tag in step with
# @playwright/test in package.json so the bundled browsers match.
FROM mcr.microsoft.com/playwright:v1.64.0-noble

WORKDIR /e2e
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
CMD ["npx", "playwright", "test"]
