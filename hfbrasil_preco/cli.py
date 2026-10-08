"""Interface de linha de comando para o pipeline hfbrasil-preco.

Uso:
    hfbrasil-preco [opcoes]

Entry point registrado em pyproject.toml:
    hfbrasil-preco = "hfbrasil_preco.cli:main"
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext
from hfbrasil_preco.orchestrator import executar


def main() -> None:
    """Entry point da CLI."""
    parser = _criar_parser()
    args = parser.parse_args()

    # 1. Carrega settings do .env (propaga env_file ao DBConfig tambem)
    settings = Settings.load(args.env)

    # 2. Sobrescreve com args da CLI
    if args.ano is not None:
        settings.ano = args.ano
    if args.produto:
        settings.produtos = {
            p.upper(): v for p, v in settings.produtos.items()
            if p.upper() in {x.upper() for x in args.produto}
        }
    if args.regiao is not None:
        settings.regiao = args.regiao
    if args.periodicidade is not None:
        settings.periodicidade = args.periodicidade
    if args.headless is not None:
        settings.headless = args.headless
    if args.dry_run:
        settings.dry_run = True
    if args.canal is not None:
        settings.canal = args.canal

    # 3. Cria contexto e configura logging
    ctx = RunContext()
    log_file: Path | None = None
    if args.log_file:
        log_file = Path(args.log_file)
    else:
        log_file = settings.logs_dir / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"

    level = logging.DEBUG if args.verbose else logging.INFO
    ctx.configurar_logger(level=level, log_file=log_file)

    ctx.logger.info("hfbrasil-preco v0.1.0 — Pipeline ETL")
    ctx.logger.info("Run ID: %s", ctx.run_id)
    ctx.logger.info("Produtos: %s", list(settings.produtos.keys()))
    ctx.logger.info("Ano: %s | Regiao: %s | Periodicidade: %s",
                    settings.ano, settings.regiao, settings.periodicidade)
    ctx.logger.info("Dry-run: %s | Headless: %s", settings.dry_run, settings.headless)

    # 4. Executa pipeline
    exit_code = executar(settings, ctx)
    sys.exit(exit_code)


def _criar_parser() -> argparse.ArgumentParser:
    """Configura o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="hfbrasil-preco",
        description="Pipeline ETL para precos medios hortifruticolas (HF Brasil)",
        epilog="Documentacao: https://github.com/.../hfbrasil-preco",
    )

    parser.add_argument(
        "--ano", type=int, default=None,
        help="Ano dos dados (default: ano corrente)",
    )
    parser.add_argument(
        "--produto", action="append", dest="produto", default=None,
        help="Produto(s) especifico(s). Usar multiplas vezes: --produto ALFACE --produto TOMATE",
    )
    parser.add_argument(
        "--regiao", type=str, default=None,
        help="Regiao (default: Todos)",
    )
    parser.add_argument(
        "--periodicidade", type=str, default=None,
        choices=["diario", "mensal", "anual", "Diario", "Mensal", "Anual"],
        help="Periodicidade (default: Diario)",
    )
    parser.add_argument(
        "--headless", action="store_true", dest="headless", default=None,
        help="Modo headless (Chrome sem GUI)",
    )
    parser.add_argument(
        "--no-headless", action="store_false", dest="headless", default=None,
        help="Modo visivel (Chrome com GUI)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run", default=False,
        help="Simular pipeline sem baixar ou inserir dados",
    )
    parser.add_argument(
        "--canal", type=str, default=None,
        choices=["console", "file", "none"],
        help="Canal de notificacao (default: console)",
    )
    parser.add_argument(
        "--env", type=str, default=".env",
        help="Caminho do arquivo .env (default: ./.env)",
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="Arquivo de log (default: dados/logs/pipeline_TIMESTAMP.log)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", dest="verbose", default=False,
        help="Log nivel DEBUG",
    )

    return parser


if __name__ == "__main__":
    main()
