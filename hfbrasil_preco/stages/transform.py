"""Etapa de transformacao: le XLS, normaliza colunas, exporta CSV.

Para cada arquivo XLS em dados/xlsx/:
    1. Le com pandas + openpyxl
    2. Extrai nome do produto do nome do arquivo
    3. Mapeia colunas (MAPA_ORIGEM + heuristica)
    4. Normaliza tipos (preco → str)
    5. Salva CSV em dados/csv/
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from hfbrasil_preco.config import PREFIXOS_PRODUTO, Settings
from hfbrasil_preco.context import RunContext, StageStatus
from hfbrasil_preco.errors import ParseError
from hfbrasil_preco.model import (
    COLUNAS_DB,
    MAPA_ORIGEM,
    normalizar,
    normalizar_preco,
)


# Heuristica complementar: normaliza nomes de colunas mesmos sem
# entrada explicita no MAPA_ORIGEM (ex: "Preço Médio" -> "preco").
_HEURISTICA_COL: dict[str, str] = {
    "produto": "produto",
    "regiao": "regiao",
    "região": "regiao",
    "dia": "dia",
    "mes": "mes",
    "mês": "mes",
    "ano": "ano",
    "moeda": "moeda",
    "unidade": "unidade",
    "preco": "preco",
    "preço": "preco",
    "preco medio": "preco",
    "preço médio": "preco",
    "preco semanal": "preco",
    "cotacao": "preco",
    "valor": "preco",
}


def transformar(
    settings: Settings,
    ctx: RunContext,
    arquivos_xls: list[Path] | None = None,
) -> list[Path]:
    """Transforma arquivos XLS em CSVs normalizados.

    Args:
        settings: Configuracao da pipeline.
        ctx: Contexto de execucao.
        arquivos_xls: Lista de paths XLS para processar.
                       Se None, varre settings.xlsx_dir.

    Returns:
        Lista de paths dos CSVs gerados.
    """
    ctx.iniciar_etapa("transform")
    settings.csv_dir.mkdir(parents=True, exist_ok=True)

    xls_paths = arquivos_xls or _listar_xls(settings)
    if not xls_paths:
        ctx.logger.warning("Nenhum arquivo XLS encontrado em %s", settings.xlsx_dir)
        ctx.finalizar_etapa("transform", StageStatus.SKIPPED)
        return []

    csvs_gerados: list[Path] = []

    for path in xls_paths:
        try:
            csv_path = _transformar_arquivo(path, settings, ctx)
            if csv_path:
                csvs_gerados.append(csv_path)
        except ParseError:
            ctx.logger.exception("Erro ao processar %s — pulando", path.name)
            continue
        except Exception:
            ctx.finalizar_etapa("transform", StageStatus.FAILED)
            raise

    if csvs_gerados:
        ctx.finalizar_etapa("transform", StageStatus.PASSED)
    else:
        ctx.finalizar_etapa("transform", StageStatus.FAILED)

    return csvs_gerados


# ── helpers ──


def _listar_xls(settings: Settings) -> list[Path]:
    """Retorna todos os .xlsx do diretorio de extracao."""
    return sorted(settings.xlsx_dir.glob("*.xlsx"))


def _transformar_arquivo(
    path: Path, settings: Settings, ctx: RunContext
) -> Path | None:
    """Processa um unico XLS: limpa rodapé, salva XLSX+CSV originais,
    depois processa para formato canonico e salva CSV para DB."""
    ctx.logger.info("Transformando: %s", path.name)

    produto = _extrair_produto(path)
    if not produto:
        ctx.logger.warning("Nome invalido: %s — pulando", path.name)
        return None

    ctx.logger.info("  Produto detectado: %s", produto)

    # 1. Leitura bruta (colunas originais preservadas)
    df = _ler_xls(path)
    if df.empty:
        ctx.logger.warning("  XLS vazio: %s — pulando", path.name)
        return None

    ctx.logger.info("  Linhas brutas: %d | Colunas: %s", len(df), list(df.columns))

    # 2. Remove linhas-residuo (rodapé "Fonte:...") ANTES de qq manipulacao
    df = _remover_residuos(df, ctx)
    if df.empty:
        ctx.logger.warning("  Todas as linhas removidas em %s", path.name)
        return None

    # 3. Aplica prefixo de grupo (ex: Cebola) na coluna original
    df = _aplicar_prefixo(df, produto, ctx)

    # 4. Salva XLSX limpo (sobrescreve o baixado, agora sem rodapé)
    _salvar_xlsx_limpo(df, path, settings, ctx)

    # 5. Salva CSV com colunas ORIGINAIS (= XLSX, separador ";", UTF-8 BOM)
    csv_nome = path.with_suffix(".csv").name
    csv_path_original = settings.csv_dir / csv_nome
    _salvar_csv_original(df, csv_path_original)
    ctx.logger.info("  CSV original: %s (%d linhas)", csv_nome, len(df))

    # 6. Processa para formato canonico (DB)
    df_canonico = _processar_canonico(df, produto, ctx)
    if df_canonico.empty:
        ctx.logger.warning("  Zero linhas apos processamento canonico em %s", path.name)
        return None

    # 7. Salva CSV canonico para DB
    csv_path_db = _salvar_csv_canonico(df_canonico, path, settings)
    ctx.logger.info("  CSV DB: %s (%d linhas)", csv_path_db.name, len(df_canonico))

    return csv_path_db


# Colunas numericas (sentinela 0) vs textuais (sentinela "") quando ausentes.
_COLUNAS_NUMERICAS: set[str] = {"dia", "mes", "ano"}


def _garantir_colunas_canonicas(
    df: pd.DataFrame, produto: str, ctx: RunContext
) -> pd.DataFrame:
    """Adiciona colunas de COLUNAS_DB ausentes com defaults sensatos.

    Numericas → 0 (sentinela), textuais → "". Evita que layouts que
    omitem colunas (ex: dados anuais sem 'dia') quebrem normalizar().
    """
    faltando = [c for c in COLUNAS_DB if c not in df.columns]
    if not faltando:
        return df
    ctx.logger.info("  Colunas ausentes preenchidas com default: %s", faltando)
    for col in faltando:
        df[col] = 0 if col in _COLUNAS_NUMERICAS else ""
    return df


# Marcadores de linha-residuo: linhas cujo conteudo em qq coluna textual
# COMECA com um destes sao descartadas (ex: rodape 'Fonte: Hortifruti/Cepea').
MARCADORES_RESIDUO: tuple[str, ...] = ("Fonte:",)


def _remover_residuos(df: pd.DataFrame, ctx: RunContext) -> pd.DataFrame:
    """Remove linhas-residuo identificadas por marcadores em qq coluna textual.

    Varre todas as colunas textuais em busca de marcadores (ex: "Fonte:"),
    que indicam linhas de rodape que nao sao registros de preco.
    """
    mask = pd.Series(False, index=df.index)
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            txt = df[col].fillna("").astype(str).str.strip()
            for marcador in MARCADORES_RESIDUO:
                mask = mask | txt.str.startswith(marcador, na=False)
    if mask.any():
        ctx.logger.info("  Linha(s)-residuo removida: %d", mask.sum())
        df = df[~mask]
    return df


def _aplicar_prefixo(
    df: pd.DataFrame, produto_label: str, ctx: RunContext
) -> pd.DataFrame:
    """Antepoe o prefixo do grupo ao nome do produto, quando configurado.

    O site omite o prefixo do grupo no export de alguns produtos (ex: cebola
    exporta "Amarela ..." mas o banco usa "Cebola Amarela ..."). Aplicado a
    nivel de linha apenas onde o valor ainda nao comeca com o prefixo (evita
    duplo prefixo). Sem entrada em PREFIXOS_PRODUTO, e um no-op.
    """
    prefixo = PREFIXOS_PRODUTO.get(produto_label.upper(), "")
    if not prefixo:
        return df

    col_produto = None
    for nome in ("Produto", "produto"):
        if nome in df.columns:
            col_produto = nome
            break
    if col_produto is None:
        return df

    prefixo_full = f"{prefixo} "
    produto_txt = df[col_produto].fillna("").astype(str).str.strip()
    falta = produto_txt.ne("") & ~produto_txt.str.startswith(prefixo_full)
    qtd = int(falta.sum())
    if qtd:
        df.loc[falta, col_produto] = prefixo_full + produto_txt[falta]
        ctx.logger.info(
            "  Prefixo '%s' aplicado a %d linha(s) de produto", prefixo, qtd
        )
    return df


def _extrair_produto(path: Path) -> str | None:
    """Extrai nome do produto do nome do arquivo.

    Formato esperado: PRODUTO_ANO.xlsx  (ex: ALFACE_2026.xlsx)
    """
    stem = path.stem  # ex: "ALFACE_2026"
    match = re.match(r"^([A-Z_]+)_\d{4}$", stem.upper())
    if match:
        return match.group(1)
    # fallback: pega a parte antes do primeiro underscore/digito
    partes = re.split(r"[_\d]", stem)
    for p in partes:
        if p.strip():
            return p.strip().upper()
    return None


def _ler_xls(path: Path) -> pd.DataFrame:
    """Le um XLS com pandas + openpyxl."""
    try:
        df = pd.read_excel(
            path,
            engine="openpyxl",
            header=0,
            dtype=str,
        )
        # Remove colunas completamente sem nome
        df = df.loc[:, ~df.columns.str.contains("^Unnamed", na=False)]
        return df
    except Exception as exc:
        raise ParseError(f"Falha ao ler XLS {path.name}: {exc}") from exc


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas usando MAPA_ORIGEM + heuristica.

    1. Tenta MAPA_ORIGEM (match exato)
    2. Fallback heuristico (lowercase + strip + 'preco' in nome, etc.)
    """
    colunas_antigas = list(df.columns)
    novo_nome: dict[str, str] = {}

    for col in colunas_antigas:
        col_str = str(col).strip()

        # 1. Match exato no MAPA_ORIGEM
        if col_str in MAPA_ORIGEM:
            novo_nome[col] = MAPA_ORIGEM[col_str]
            continue

        # 2. Match heuristico (case-insensitive, normalizado)
        chave = col_str.lower().strip()
        if chave in _HEURISTICA_COL:
            novo_nome[col] = _HEURISTICA_COL[chave]
            continue

        # 3. Match parcial (coluna contem palavra-chave)
        for palavra, canonico in _HEURISTICA_COL.items():
            if palavra in chave:
                novo_nome[col] = canonico
                break

    if not novo_nome:
        return pd.DataFrame()

    df = df.rename(columns=novo_nome)

    # Mantem apenas colunas que conseguimos mapear
    uteis = [c for c in novo_nome.values() if c in df.columns]
    # Remove duplicatas mantendo a primeira
    uteis = list(dict.fromkeys(uteis))
    return df[uteis]


def _ajustar_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Converte tipos para o contrato do DTO / banco."""
    # preco → str canonico (ponto decimal), tratando locale BR sem
    # corromper valores que ja vem com ponto decimal.
    if "preco" in df.columns:
        df["preco"] = normalizar_preco(df["preco"])

    # dia, mes, ano → int (NaN vira 0)
    for col in ("dia", "mes", "ano"):
        if col in df.columns:
            df[col] = (
                pd.to_numeric(df[col], errors="coerce")
                .fillna(0)
                .astype(int)
            )

    return df


def _salvar_xlsx_limpo(
    df: pd.DataFrame, xls_path: Path, settings: Settings, ctx: RunContext
) -> Path:
    """Salva DataFrame limpo como XLSX (sobrescreve o baixado)."""
    df.to_excel(xls_path, index=False, engine="openpyxl")
    ctx.logger.info("  XLSX limpo salvo: %s", xls_path.name)
    return xls_path


def _salvar_csv_original(df: pd.DataFrame, csv_path: Path) -> Path:
    """Salva CSV com colunas originais (separador ";", UTF-8 BOM).

    Usa separador ; para compatibilidade com Excel pt-BR e
    encoding UTF-8 BOM para que o Excel reconheca o encoding.
    """
    df.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")
    return csv_path


def _salvar_csv_canonico(df: pd.DataFrame, xls_path: Path, settings: Settings) -> Path:
    """Salva DataFrame normalizado como CSV canonico para carga no DB."""
    csv_nome = xls_path.stem + "_db.csv"
    csv_path = settings.csv_dir / csv_nome
    df.to_csv(csv_path, index=False, encoding="utf-8")
    return csv_path


def _processar_canonico(
    df: pd.DataFrame, produto: str, ctx: RunContext
) -> pd.DataFrame:
    """Processa DataFrame limpo para formato canonico (DB)."""
    df = _normalizar_colunas(df)
    if df.empty:
        return df
    df = df.dropna(how="all")
    if "produto" in df.columns:
        df["produto"] = df["produto"].fillna(produto)
    else:
        df["produto"] = produto
    df = _garantir_colunas_canonicas(df, produto, ctx)
    df = normalizar(df)
    df = _ajustar_tipos(df)
    return df
