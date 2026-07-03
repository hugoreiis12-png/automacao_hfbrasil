# ============================================================
# hfbrasil-preco — imagem de execucao agendada (segunda 07:00 BRT)
# Base: Python 3.12 slim (Debian bookworm)
# Chromium + chromium-driver (apt) para Selenium headless
# cron para o agendamento semanal
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    BASE_DIR=/app/dados

# Chromium para Selenium headless + cron para agendamento + tzdata p/ o fuso.
# chromium e chromium-driver vem do MESMO repo apt: versoes ja compatíveis,
# sem download de driver em runtime (webdriver-manager fica ocioso no container).
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        cron \
        tzdata \
    && ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Codigo + dependencias. Copiar o pacote ANTES do pip install: o setuptools
# (packages.find) precisa das fontes presentes para resolver hfbrasil_preco.
COPY pyproject.toml ./
COPY hfbrasil_preco/ ./hfbrasil_preco/
RUN pip install --no-cache-dir .

# Crontab (formato de 5 campos, sem coluna de usuario): toda segunda 07:00.
# O horario segue o TZ do container (definido acima / sobrescrito no entrypoint).
COPY crontab /app/crontab
RUN crontab /app/crontab

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/dados/logs /app/dados/xlsx /app/dados/csv

ENTRYPOINT ["/entrypoint.sh"]
