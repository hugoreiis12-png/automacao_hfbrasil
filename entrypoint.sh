#!/bin/sh
set -e

mkdir -p /app/dados/logs /app/dados/xlsx /app/dados/csv
touch /app/dados/logs/cron.log

# Timezone: permite sobrescrever o TZ da imagem em runtime (env do compose).
if [ -n "$TZ" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
    echo "$TZ" > /etc/timezone
fi

# O cron nao herda o ambiente do container. Exportamos as variaveis relevantes
# para um arquivo que o job carrega (. /app/container_env.sh) antes de rodar o
# pipeline. Valores em aspas simples para tolerar espacos/&/? (ex: SITE_URL).
printenv | grep -E '^(PG_[A-Z0-9_]*|BASE_DIR|SITE_URL|ANO|PERIODICIDADE|HEADLESS|CANAL|CHROME_BINARY|CHROMEDRIVER_PATH|TZ|RUN_ON_START)=' \
    | while IFS='=' read -r chave valor; do
        printf "export %s='%s'\n" "$chave" "$valor"
    done > /app/container_env.sh

echo "[entrypoint] $(date '+%Y-%m-%d %H:%M:%S %Z') — container pronto."
echo "[entrypoint] Agendamento: toda segunda-feira 07:00 (${TZ:-UTC})."

# Execucao imediata opcional — util para validar o deploy sem esperar segunda.
if [ "${RUN_ON_START:-false}" = "true" ]; then
    echo "[entrypoint] RUN_ON_START=true — executando pipeline agora..."
    . /app/container_env.sh
    hfbrasil-preco >> /app/dados/logs/cron.log 2>&1 \
        || echo "[entrypoint] pipeline retornou erro (segue para o agendador)."
fi

# Sobe o cron (daemoniza) e mantem o PID 1 vivo espelhando o log no stdout,
# assim as execucoes ficam visiveis nos logs do container (Portainer).
cron
exec tail -F /app/dados/logs/cron.log
