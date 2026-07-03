# hfbrasil-preco

Pipeline ETL para precos medios hortifruticolas do HF Brasil.

Extrai dados do site [HF Brasil](https://www.hfbrasil.org.br), transforma XLS
em CSV normalizado, aplica gates de qualidade e carrega no PostgreSQL.

## Requisitos

- Python >= 3.12
- Google Chrome (para extracao com Selenium)
- PostgreSQL (para armazenamento dos dados)

## Setup

```bash
# 1. Clonar e entrar no diretorio
git clone <repo>
cd hfbrasil-preco

# 2. Criar virtualenv e ativar
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 3. Instalar o pacote
make install
# ou: pip install -e .

# 4. Criar as tabelas no PostgreSQL
psql -h localhost -U postgres -d FABRICA -f sql/001_destino_produto_preco_hf.sql
psql -h localhost -U postgres -d FABRICA -f sql/002_pipeline_auditoria.sql
```

## Configuracao (.env)

Crie um arquivo `.env` na raiz (veja `.env.example`):

```env
PG_HOST=localhost
PG_PORT=5432
PG_DBNAME=FABRICA
PG_USER=postgres
PG_PASSWORD=postgres
PG_SCHEMA=hfbrasil_preco
BASE_DIR=./dados
HEADLESS=true
CANAL=console
```

## Uso

### Pipeline completa

```bash
# Executar pipeline
hfbrasil-preco

# Simular sem baixar nem inserir
hfbrasil-preco --dry-run -v

# Filtrar produtos especificos
hfbrasil-preco --produto ALFACE --produto TOMATE

# Outro ano / periodicidade
hfbrasil-preco --ano 2025 --periodicidade mensal

# Modo visivel (com GUI do Chrome)
hfbrasil-preco --no-headless

# Usando o atalho run.py
python run.py --dry-run -v
```

### Relatorios

```bash
# Consultar dados carregados
hfbrasil-preco-report --produto ALFACE --ano 2026

# Exportar para CSV
hfbrasil-preco-report --produto TOMATE --formato csv --output dados.csv

# Exportar para Excel
hfbrasil-preco-report --ano 2025 --formato excel --output relatorio.xlsx
```

### Makefile

```bash
make install    # pip install -e .
make test       # pytest tests/ -v
make mypy       # mypy hfbrasil_preco/ tests/
make run        # executar pipeline
make run-dry    # dry-run com verbose
make clean      # limpar caches
```

## Arquitetura

```
run.py / CLI
    |
orchestrator.py
    |
    +---> checks       (site acessivel, diretorios)
    +---> extract      (Selenium + Chrome -> XLS)
    +---> transform    (XLS -> CSV normalizado)
    +---> quality      (gates: nulo, duplicata, range)
    +---> load         (CSV -> PostgreSQL via COPY)
    |
    +---> audit        (registro na tabela pipeline_auditoria)
    +---> notify       (console / file / none)
```

### Fluxo de dados

```
Site HF Brasil  ──extract──>  dados/xlsx/*.xlsx
                                    |
                               transform
                                    |
                            dados/csv/*.csv
                                    |
                               quality (gates)
                                    |
                               load (COPY)
                                    |
                         PostgreSQL (produto_preco_hf)
```

## Estrutura do projeto

```
hfbrasil-preco/
├── hfbrasil_preco/         # Pacote principal
│   ├── cli.py              # CLI (argparse)
│   ├── orchestrator.py     # Orquestrador do pipeline
│   ├── config.py           # Settings via pydantic-settings
│   ├── context.py          # RunContext, StageStatus
│   ├── errors.py           # Hierarquia de erros
│   ├── db.py               # Conexao PostgreSQL
│   ├── model.py            # DTO, COLUNAS_DB, normalizacao
│   ├── checks.py           # Verificacoes pre-voo
│   ├── audit.py            # Auditoria no banco
│   ├── notify.py           # Notificacoes
│   ├── quality.py          # Gates de qualidade
│   ├── report.py           # Relatorios pos-carga
│   └── stages/
│       ├── extract.py      # Selenium + Chrome
│       ├── transform.py    # XLS -> CSV
│       └── load.py         # CSV -> PostgreSQL
├── tests/                  # Testes unitarios
├── sql/                    # DDLs do banco
├── dados/                  # Dados gerados (xlsx/, csv/, logs/)
├── run.py                  # Atalho: python run.py
├── Makefile                # Automacao
└── .env                    # Configuracao local
```

## Testes

```bash
# Todos os testes
pytest tests/ -v

# Testes especificos
pytest tests/test_errors.py -v
pytest tests/test_model.py -v
pytest tests/test_report.py -v
pytest tests/test_transform.py -v
```

50 testes unitarios cobrindo:
- Hierarquia de erros (17 classes)
- Modelo de dados (DTO, COLUNAS_DB, normalizacao)
- Transformacao (extrair produto, ler XLS, ajustar tipos)
- Relatorios (sumarios, exportacao CSV)

## Tecnologias

- **Python 3.12** — tipo estrito (mypy strict)
- **Selenium** + webdriver-manager — automacao do navegador
- **pandas** + openpyxl — transformacao de dados
- **psycopg2** — PostgreSQL (COPY bulk insert)
- **pydantic** + pydantic-settings — configuracao tipada
- **pytest** — testes unitarios

## Deploy com Docker / Portainer

A imagem roda o pipeline **1x por semana, toda segunda-feira as 07:00**
(fuso `America/Sao_Paulo`), via `cron` interno. O container fica de pe
(`restart: unless-stopped`) e o `cron` dispara o job no horario.

```bash
# Build local
docker build -t hfbrasil-preco:latest .

# Subir via compose (ajuste as variaveis no docker-compose.yml antes)
docker compose up -d

# Validar o deploy sem esperar segunda: executa o pipeline uma vez no start
#   defina RUN_ON_START=true no docker-compose.yml, suba, confira os logs,
#   depois volte para false.
docker compose logs -f
```

### Secret da senha do banco (Docker standalone)

A senha do PostgreSQL **nao** fica em variavel de ambiente nem no git: e lida
de um Docker secret montado em `/run/secrets/pg_password`. O `config.py`
resolve `PG_PASSWORD_FILE` (convencao `_FILE` das imagens oficiais) lendo esse
arquivo. Tambem ha suporte a `PG_USER_FILE`, se quiser proteger o usuario.

**No host do Docker** (fora do git), crie o arquivo do secret:

```bash
sudo mkdir -p /opt/hfbrasil-preco/secrets
printf 'SUA_SENHA_REAL' | sudo tee /opt/hfbrasil-preco/secrets/pg_password >/dev/null
sudo chmod 600 /opt/hfbrasil-preco/secrets/pg_password
```

**No Portainer** (Stack a partir do git), defina uma variavel de ambiente da
stack apontando para esse arquivo:

```
PG_PASSWORD_FILE_SRC=/opt/hfbrasil-preco/secrets/pg_password
```

**Em dev local**, basta criar `secrets/pg_password` na raiz do projeto
(gitignored) — o compose usa esse caminho por padrao.

### Schema no banco de destino

O pipeline **nao cria** as tabelas. No destino `192.168.0.250/FABRICA` ambas
ja existem: `hfbrasil_preco.produto_preco_hf` (dados) e
`hfbrasil_preco.pipeline_auditoria` (auditoria, criada via `sql/002`). Num
banco novo (do zero), aplique os dois DDLs:

```bash
psql -h <host> -U postgres -d FABRICA -f sql/001_destino_produto_preco_hf.sql
psql -h <host> -U postgres -d FABRICA -f sql/002_pipeline_auditoria.sql
```

A auditoria e nao-fatal: se a tabela faltar, o pipeline ainda carrega os dados
(apenas emite warning e fica sem trilha historica).

### Como o Chrome roda no container

O `Dockerfile` instala `chromium` + `chromium-driver` do apt (versoes sempre
compativeis). As variaveis `CHROME_BINARY` e `CHROMEDRIVER_PATH` (ja setadas
na imagem) fazem o `extract.py` usar esses binarios diretamente, sem baixar
driver em runtime. Em dev local essas variaveis ficam vazias e o
`webdriver-manager` resolve o driver normalmente.

## Proximos passos

- [x] Agendamento cron / scheduler
- [x] Docker
- [ ] Canais de notificacao: email, Slack, WhatsApp
- [ ] Testes de integracao com banco real
- [ ] CI/CD (GitHub Actions)
