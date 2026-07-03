"""Etapa de carga: le CSV normalizado e insere no PostgreSQL.

Para cada CSV em dados/csv/:
    1. Extrai produto + ano do nome do arquivo
    2. DELETE FROM produto_preco_hf WHERE produto=X AND ano=Y
    3. COPY dados FROM STDIN (bulk insert)
    4. Commit ao final; rollback em qualquer erro
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import psycopg2
from psycopg2 import sql

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext, StageStatus
from hfbrasil_preco.db import Database
from hfbrasil_preco.errors import LoadError, QueryError
from hfbrasil_preco.model import COLUNAS_DB


def carregar(
    settings: Settings,
    ctx: RunContext,
    arquivos_csv: list[Path] | None = None,
) -> int:
    """Carrega CSVs normalizados na tabela produto_preco_hf.

    Args:
        settings: Configuracao da pipeline.
        ctx: Contexto de execucao.
        arquivos_csv: Lista de paths CSV. Se None, varre settings.csv_dir.

    Returns:
        Total de registros inseridos.
    """
    ctx.iniciar_etapa("load")

    csvs = arquivos_csv or _listar_csv(settings)
    if not csvs:
        ctx.logger.warning("Nenhum CSV encontrado em %s", settings.csv_dir)
        ctx.finalizar_etapa("load", StageStatus.SKIPPED)
        return 0

    db = Database(settings.db)
    total_inseridos = 0

    try:
        db.connect()
        for csv_path in csvs:
            inseridos = _carregar_csv(db, csv_path, settings, ctx)
            total_inseridos += inseridos
        db.commit()
    except (psycopg2.Error, LoadError, QueryError) as exc:
        ctx.logger.error("Erro na carga — executando rollback: %s", exc)
        db.rollback()
        ctx.finalizar_etapa("load", StageStatus.FAILED)
        raise
    else:
        ctx.logger.info("Carga concluida: %d registros inseridos", total_inseridos)
        ctx.finalizar_etapa("load", StageStatus.PASSED)
        return total_inseridos
    finally:
        db.close()


# ── helpers ──


def _listar_csv(settings: Settings) -> list[Path]:
    """Retorna todos os CSVs canonicos do diretorio de transformacao."""
    return sorted(settings.csv_dir.glob("*_db.csv"))


def _extrair_metadados(path: Path) -> tuple[str, int] | None:
    """Extrai (produto, ano) do nome do arquivo.

    Formato esperado: PRODUTO_ANO_db.csv  (ex: ALFACE_2026_db.csv)
    """
    stem = path.stem.upper().replace("_DB", "")
    match = re.match(r"^([A-Z_]+)_(\d{4})$", stem)
    if match:
        return (match.group(1), int(match.group(2)))
    return None


def _carregar_csv(
    db: Database,
    csv_path: Path,
    settings: Settings,
    ctx: RunContext,
) -> int:
    """Executa DELETE + COPY para um unico CSV."""
    metadados = _extrair_metadados(csv_path)
    if metadados is None:
        ctx.logger.warning(
            "Nome de arquivo invalido (esperado PRODUTO_ANO.csv): %s — pulando",
            csv_path.name,
        )
        return 0

    _, ano = metadados
    # Os produtos reais vem da coluna 'produto' do CSV (nomes ricos do site,
    # ex: 'Salada longa vida AA - atacado'), NAO do rotulo do arquivo. O DELETE
    # precisa casar com esses valores para a carga ser idempotente (replace
    # do mesmo produto+ano, sem duplicar nem apagar outros produtos/anos).
    produtos = _produtos_no_csv(csv_path)
    if not produtos:
        ctx.logger.warning("CSV sem produtos validos: %s — pulando", csv_path.name)
        return 0

    ctx.logger.info(
        "Carregando: %s (ano=%d, %d produto(s) distinto(s))",
        csv_path.name, ano, len(produtos),
    )

    with db.cursor() as cur:
        # 1. DELETE registros existentes dos MESMOS produtos + ano
        _deletar_existentes(cur, settings, produtos, ano, ctx)

        # 2. COPY bulk insert
        inseridos = _copiar_csv(cur, csv_path, settings, ctx)

    return inseridos


def _produtos_no_csv(csv_path: Path) -> list[str]:
    """Le os valores distintos (nao vazios) da coluna 'produto' do CSV."""
    produtos: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            valor = (linha.get("produto") or "").strip()
            if valor:
                produtos.add(valor)
    return sorted(produtos)


def _deletar_existentes(
    cur: psycopg2.extensions.cursor,
    settings: Settings,
    produtos: list[str],
    ano: int,
    ctx: RunContext,
) -> None:
    """Remove registros existentes dos produtos do CSV (mesmo ano).

    Usa os produtos REAIS presentes no CSV em vez do rotulo do arquivo: so
    assim o DELETE casa com os nomes ricos ja gravados e a carga vira um
    replace idempotente (sem duplicar nem apagar outros produtos/anos).
    """
    tabela = sql.Identifier(settings.db.db_schema, settings.db.tabela)
    query = sql.SQL(
        "DELETE FROM {} WHERE produto = ANY(%s) AND ano = %s"
    ).format(tabela)

    try:
        cur.execute(query, (produtos, ano))
        removidos = cur.rowcount
        if removidos > 0:
            ctx.logger.info("  Registros removidos: %d", removidos)
    except psycopg2.Error as exc:
        raise QueryError(
            f"Falha ao deletar registros de {len(produtos)} produto(s)/{ano}: {exc}"
        ) from exc


def _copiar_csv(
    cur: psycopg2.extensions.cursor,
    csv_path: Path,
    settings: Settings,
    ctx: RunContext,
) -> int:
    """Faz COPY do CSV para a tabela via psycopg2 copy_expert."""
    colunas = ", ".join(COLUNAS_DB)
    tabela = f"{settings.db.db_schema}.{settings.db.tabela}"
    sql_copy = f"COPY {tabela} ({colunas}) FROM STDIN WITH CSV HEADER"

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            cur.copy_expert(sql_copy, f)
        inseridos: int = cur.rowcount or 0
        ctx.logger.info("  Registros inseridos: %d", inseridos)
        return inseridos
    except (psycopg2.Error, OSError) as exc:
        raise LoadError(
            f"Falha ao copiar {csv_path.name} para {tabela}: {exc}"
        ) from exc
