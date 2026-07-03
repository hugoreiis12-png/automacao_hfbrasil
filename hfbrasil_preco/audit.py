"""Auditoria: registra cada etapa da pipeline na tabela pipeline_auditoria.

Uso tipico no orchestrator:
    auditoria.registrar(ctx, settings, "extract", "passed", produto="ALFACE")
    auditoria.registrar(ctx, settings, "load", "failed", erro=exc)
"""

from __future__ import annotations

from datetime import datetime

import psycopg2
from psycopg2 import sql

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext
from hfbrasil_preco.db import Database
from hfbrasil_preco.errors import AuditError, DBConnectionError


def registrar(
    ctx: RunContext,
    settings: Settings,
    etapa: str,
    status: str,
    produto: str | None = None,
    ano: int | str | None = None,
    registros: int = 0,
    erro: Exception | None = None,
) -> None:
    """Insere um registro de auditoria no banco.

    Args:
        ctx: Contexto da execucao (fornece run_id, duracao).
        settings: Configuracao (fornece db, audit_tabela).
        etapa: Nome da etapa (ex: "extract", "transform").
        status: "passed", "failed", "skipped".
        produto: Nome do produto (opcional).
        ano: Ano filtrado (opcional, varchar(4) no banco).
        registros: Quantidade de registros processados.
        erro: Excecao capturada (opcional).
    """
    try:
        _inserir(ctx, settings, etapa, status, produto, ano, registros, erro)
    except Exception as exc:
        ctx.logger.warning("Falha ao registrar auditoria: %s", exc)


def _inserir(
    ctx: RunContext,
    settings: Settings,
    etapa: str,
    status: str,
    produto: str | None,
    ano: int | str | None,
    registros: int,
    erro: Exception | None,
) -> None:
    """Executa o INSERT na tabela de auditoria."""
    db = Database(settings.db)
    try:
        db.connect()
        with db.cursor() as cur:
            tabela = sql.Identifier(settings.db.db_schema, settings.db.audit_tabela)
            query = sql.SQL(
                "INSERT INTO {} "
                "(run_id, etapa, status, produto, ano, registros, "
                " duracao_s, erro_tipo, erro_msg) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            ).format(tabela)

            erro_tipo = type(erro).__name__ if erro else None
            erro_msg = str(erro) if erro else None
            ano_str = str(ano) if ano is not None else None

            cur.execute(query, (
                str(ctx.run_id),
                etapa,
                status,
                produto,
                ano_str,
                registros,
                round(ctx.duracao_segundos, 2),
                erro_tipo,
                erro_msg,
            ))
        db.commit()
    except (psycopg2.Error, DBConnectionError) as exc:
        raise AuditError(f"Falha no INSERT de auditoria: {exc}") from exc
    finally:
        db.close()
