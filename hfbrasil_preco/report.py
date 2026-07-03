"""Relatorios: consulta dados carregados e gera sumarios/exportacoes.

Uso como biblioteca:
    from hfbrasil_preco.report import consultar, resumo_precos
    df = consultar(settings, produto="ALFACE", ano=2026)
    resumo = resumo_precos(df)

Uso como CLI:
    hfbrasil-preco-report --produto ALFACE --ano 2026 --formato csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from hfbrasil_preco.config import Settings
from hfbrasil_preco.db import Database
from typing import Any

from hfbrasil_preco.errors import DBConnectionError, QueryError
from hfbrasil_preco.model import normalizar_preco

_COLUNAS_RESUMO: list[str] = [
    "produto", "regiao", "ocorrencias",
    "preco_medio", "preco_mediano",
    "preco_min", "preco_max",
]


def listar_produtos(settings: Settings, db: Database | None = None) -> list[str]:
    """Retorna lista de produtos distintos disponiveis no banco (ignora NULL)."""
    return [p for p in _coluna_distinta(settings, db, "produto") if p is not None]


def listar_anos(settings: Settings, db: Database | None = None) -> list[int]:
    """Retorna lista de anos distintos disponiveis no banco (ignora NULL).

    Descarta valores NULL antes de ordenar -- dados reais tem linhas de
    rodape (ex: 'Fonte: Hortifruti/Cepea') com ano nulo, e sorted() nao
    compara None com int.
    """
    return sorted(a for a in _coluna_distinta(settings, db, "ano") if a is not None)


def consultar(
    settings: Settings,
    produto: str | None = None,
    ano: int | None = None,
    regiao: str | None = None,
    mes: int | None = None,
) -> pd.DataFrame:
    """Consulta dados da tabela produto_preco_hf com filtros opcionais.

    Args:
        settings: Configuracao (fornece db, tabela).
        produto: Filtrar por produto (ex: "ALFACE").
        ano: Filtrar por ano (ex: 2026).
        regiao: Filtrar por regiao (ex: "Todos").
        mes: Filtrar por mes (1-12).

    Returns:
        DataFrame com os registros encontrados.
    """
    tabela = settings.db.tabela_completa
    sql = f"SELECT * FROM {tabela} WHERE 1=1"
    params: list[object] = []

    if produto:
        sql += " AND produto = %s"
        params.append(produto)
    if ano is not None:
        sql += " AND ano = %s"
        params.append(ano)
    if regiao:
        sql += " AND regiao = %s"
        params.append(regiao)
    if mes is not None:
        sql += " AND mes = %s"
        params.append(mes)

    sql += " ORDER BY produto, ano, mes, dia"

    db = Database(settings.db)
    try:
        db.connect()
        with db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame.from_records(rows)
        return df
    except Exception as exc:
        raise QueryError(f"Falha ao consultar dados: {exc}") from exc
    finally:
        db.close()


def resumo_precos(df: pd.DataFrame) -> pd.DataFrame:
    """Gera estatisticas descritivas dos precos por produto e regiao.

    Args:
        df: DataFrame com colunas produto, regiao, preco (pelo menos).

    Returns:
        DataFrame agrupado com media, mediana, min, max, contagem.
    """
    if df.empty or "preco" not in df.columns:
        return pd.DataFrame(columns=_COLUNAS_RESUMO)

    preco_numerico = _preco_para_float(df)
    agrupado = (
        preco_numerico.groupby(["produto", "regiao"], as_index=False)["preco"]
        .agg(ocorrencias="count", preco_medio="mean", preco_mediano="median",
             preco_min="min", preco_max="max")
        .round(2)
    )
    return agrupado


def exportar_csv(df: pd.DataFrame, path: str | Path) -> Path:
    """Salva DataFrame como CSV.

    Args:
        df: DataFrame a exportar.
        path: Caminho de destino.

    Returns:
        Path absoluto do arquivo gerado.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return path.resolve()


def exportar_excel(df: pd.DataFrame, path: str | Path) -> Path:
    """Salva DataFrame como Excel (.xlsx).

    Args:
        df: DataFrame a exportar.
        path: Caminho de destino.

    Returns:
        Path absoluto do arquivo gerado.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")
    return path.resolve()


# ── helpers ──


def _coluna_distinta(
    settings: Settings, db: Database | None, coluna: str
) -> list[Any]:
    """Retorna valores distintos de uma coluna da tabela."""
    fechar_db = db is None
    if db is None:
        db = Database(settings.db)

    tabela = settings.db.tabela_completa
    sql = f"SELECT DISTINCT {coluna} FROM {tabela} ORDER BY {coluna}"

    try:
        db.connect()
        with db.cursor() as cur:
            cur.execute(sql)
            return [row[coluna] for row in cur.fetchall()]
    except Exception as exc:
        raise QueryError(
            f"Falha ao listar {coluna}: {exc}"
        ) from exc
    finally:
        if fechar_db:
            db.close()


def _preco_para_float(df: pd.DataFrame) -> pd.DataFrame:
    """Converte coluna preco de string para float (locale BR)."""
    if "preco" not in df.columns:
        return df
    copia = df.copy()
    copia["preco"] = pd.to_numeric(
        normalizar_preco(copia["preco"]), errors="coerce"
    )
    return copia


def main() -> None:
    """Entry point CLI para geracao de relatorios."""
    parser = argparse.ArgumentParser(
        prog="hfbrasil-preco-report",
        description="Relatorios de precos medios hortifruticolas (HF Brasil)",
    )
    parser.add_argument("--produto", type=str, default=None, help="Filtrar por produto")
    parser.add_argument("--ano", type=int, default=None, help="Filtrar por ano")
    parser.add_argument("--regiao", type=str, default=None, help="Filtrar por regiao")
    parser.add_argument("--mes", type=int, default=None, help="Filtrar por mes (1-12)")
    parser.add_argument(
        "--formato", type=str, default="console",
        choices=["console", "csv", "excel"],
        help="Formato de saida (default: console)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Caminho do arquivo de saida (obrigatorio se formato=csv ou excel)",
    )
    parser.add_argument("--env", type=str, default=".env", help="Caminho do .env")

    args = parser.parse_args()
    settings = Settings.load(args.env)

    if args.formato in ("csv", "excel") and not args.output:
        parser.error("--output e obrigatorio quando formato=csv ou excel")

    try:
        df = consultar(settings, produto=args.produto, ano=args.ano,
                       regiao=args.regiao, mes=args.mes)
    except (QueryError, DBConnectionError) as exc:
        print(f"Erro ao consultar dados: {exc}", file=sys.stderr)
        sys.exit(1)

    if df.empty:
        print("Nenhum registro encontrado para os filtros informados.")
        sys.exit(0)

    if args.formato == "console":
        print(df.to_string(index=False))
    elif args.formato == "csv":
        caminho = exportar_csv(df, args.output)
        print(f"Arquivo salvo: {caminho}")
    elif args.formato == "excel":
        caminho = exportar_excel(df, args.output)
        print(f"Arquivo salvo: {caminho}")

    sys.exit(0)


if __name__ == "__main__":
    main()
