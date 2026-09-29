FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -yq --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && groupadd -r -g 1000 appgroup \
    && useradd -r -u 1000 -g appgroup -d /app -s /sbin/nologin appuser

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME=/opt/poetry \
    POETRY_VERSION=2.4.1 \
    PATH="/opt/poetry/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

# Копируем файлы зависимостей отдельно для кэширования слоя
COPY --chown=appuser:appgroup pyproject.toml poetry.lock ./

# --- Стадия разработки (с pytest и dev-зависимостями) ---
FROM base AS development
# Устанавливаем все зависимости, включая dev-группу
RUN poetry install --no-root --no-interaction --no-ansi
COPY --chown=appuser:appgroup . .
# Даем права пользователю
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE 8000
# CMD в docker-compose

# --- Стадия продакшена (без dev-зависимостей) ---
FROM base AS production
# Устанавливаем только основные зависимости (Django, DRF, python-telegram-bot и т.д.)
RUN poetry install --only main --no-root --no-interaction --no-ansi
COPY --chown=appuser:appgroup . .
USER appuser
EXPOSE 8000
# CMD в docker-compose