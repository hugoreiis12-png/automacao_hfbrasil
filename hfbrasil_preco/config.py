"""Configuracao central, tipada com pydantic-settings.

Le as variaveis do ambiente / .env com validacao de tipos. As decisoes
ainda em aberto (onde roda, canal, parametros do filtro, tipo do 'ano')
continuam como campos com defaults sensatos -- nunca espalhadas pelo codigo.
"""
from __future__ import annotations
import os
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# value do radio "produto-<value>" no formulario (confirmado por inspecao)
PRODUTOS_PADRAO: dict[str, int] = {"ALFACE": 12, "TOMATE": 5, "CEBOLA": 2}

# Prefixo do grupo a antepor ao nome do produto vindo do XLS. O site omite o
# prefixo do grupo no export de alguns produtos: a cebola exporta
# "Amarela ..." enquanto o banco usa "Cebola Amarela ...". Alface/Tomate ja
# vem com o nome completo (sem entrada aqui = prefixo vazio). Chave = rotulo
# do arquivo em UPPER (ex: "CEBOLA").
PREFIXOS_PRODUTO: dict[str, str] = {"CEBOLA": "Cebola"}

# Convencao Docker "_FILE": pares (env que aponta para o arquivo, campo do DTO).
# Usado para injetar credenciais sensiveis via secret montado (/run/secrets/...).
_DB_SECRETS_FILE: tuple[tuple[str, str], ...] = (
    ("PG_PASSWORD_FILE", "password"),
    ("PG_USER_FILE", "user"),
)


class DBConfig(BaseSettings):
    """Conexao e destino no PostgreSQL (le variaveis PG_* do ambiente/.env)."""
    model_config = SettingsConfigDict(
        env_prefix="PG_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    dbname: str = "FABRICA"
    user: str = ""
    password: str = ""
    # 'schema' conflita com atributo do pydantic -> atributo db_schema, env PG_SCHEMA
    db_schema: str = Field(default="hfbrasil_preco", validation_alias="PG_SCHEMA")
    tabela: str = "produto_preco_hf"
    audit_tabela: str = "pipeline_auditoria"

    @model_validator(mode="before")
    @classmethod
    def _resolver_secrets_file(cls, data: Any) -> Any:
        """Suporte a Docker/Swarm secrets (convencao _FILE das imagens oficiais).

        Se PG_PASSWORD_FILE / PG_USER_FILE apontar para um arquivo (ex:
        /run/secrets/pg_password), le o conteudo (sem espacos nas bordas) e usa
        como valor do campo. Assim a senha nunca precisa ir em variavel de
        ambiente nem ser commitada no git — fica so no secret montado pelo
        orquestrador. Precede o valor vindo de PG_PASSWORD/PG_USER em env.
        """
        if not isinstance(data, dict):
            return data
        for env_file, campo in _DB_SECRETS_FILE:
            caminho = os.environ.get(env_file)
            if caminho and Path(caminho).is_file():
                data[campo] = Path(caminho).read_text(encoding="utf-8").strip()
        return data

    @property
    def tabela_completa(self) -> str:
        return f"{self.db_schema}.{self.tabela}"

    @property
    def auditoria_completa(self) -> str:
        return f"{self.db_schema}.{self.audit_tabela}"


class Settings(BaseSettings):
    """Parametros gerais da pipeline (le variaveis do ambiente/.env)."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_dir: Path = Path("./dados")

    site_url: str = ("https://www.hfbrasil.org.br/br/"
                     "banco-de-dados-precos-medios-dos-hortifruticolas.aspx")
    produtos: dict[str, int] = Field(default_factory=lambda: dict(PRODUTOS_PADRAO))
    ano: int = Field(default_factory=lambda: date.today().year)
    regiao: str = "Todos"
    periodicidade: str = "Diario"
    headless: bool = True
    postback_timeout: int = 30
    download_timeout: int = 60

    # Selenium/Chrome: caminhos explicitos para binario e driver. Vazios em
    # dev local (usa webdriver-manager); no container Docker apontam para o
    # chromium/chromedriver instalados via apt (CHROME_BINARY / CHROMEDRIVER_PATH),
    # tornando a extracao deterministica sem download de driver em runtime.
    chrome_binary: str | None = None
    chromedriver_path: str | None = None

    # comportamento
    verificar_site: bool = True
    dry_run: bool = False

    # resiliencia
    max_tentativas: int = 3
    backoff_s: float = 5.0

    # TODO: definir canal (console | file | email | slack | teams | whatsapp)
    canal: str = "console"
    notificar_sucesso: bool = False

    db: DBConfig = Field(default_factory=DBConfig)

    @property
    def xlsx_dir(self) -> Path:
        return self.base_dir / "xlsx"

    @property
    def csv_dir(self) -> Path:
        return self.base_dir / "csv"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @classmethod
    def load(cls, env_file: str | None = ".env") -> "Settings":
        """Carrega Settings e DBConfig a partir do MESMO arquivo .env.

        O DBConfig precisa ser construido explicitamente com o env_file: o
        default_factory criaria DBConfig() sem argumentos, lendo sempre o
        '.env' fixo do seu model_config e ignorando o env_file escolhido aqui
        (CLI --env). Variaveis de ambiente PG_* continuam tendo prioridade.
        """
        db = DBConfig(_env_file=env_file)  # type: ignore[call-arg]
        return cls(_env_file=env_file, db=db)  # type: ignore[call-arg]