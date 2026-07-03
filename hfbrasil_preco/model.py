"""Modelo de dominio do dado de preco: a unica fonte da verdade para as
colunas que atravessam a pipeline.

"""
from __future__ import annotations
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas as pd


# Classe de Modelos Base tipado para Preços de Registros 
class PrecoRegistro(BaseModel):
    """DTO / modelo tipado que espelha as colunas da tabela produto_preco_hf
    (excluindo id_tabela que e auto-gerado pelo banco).
    A ordem dos campos = ordem das colunas no banco (usada no COPY)."""
    produto: str
    regiao: str
    dia: int
    mes: int
    ano: int
    moeda: str
    unidade: str
    preco: str


# Colunas canonicas na ordem do banco, DERIVADAS do DTO (sem duplicar).
COLUNAS_DB: tuple[str, ...] = tuple(PrecoRegistro.model_fields)

# Atalhos usados pelos quality gates.
COL_PRODUTO = "produto"
COL_ANO = "ano"
COL_PRECO = "preco"

# Mapa de nomes de colunas do XLS → nomes canonicos do DTO.
# Preenchido com os nomes mais provaveis com base no layout do site;
# o transform.py ainda aplica um fallback heuristico caso o XLS use
# nomes diferentes.
MAPA_ORIGEM: dict[str, str] = {
    "Produto": "produto",
    "Regiao": "regiao",
    "Região": "regiao",
    "Dia": "dia",
    "Mes": "mes",
    "Mês": "mes",
    "Ano": "ano",
    "Moeda": "moeda",
    "Unidade": "unidade",
    "Preco": "preco",
    "Preço": "preco",
}


def colunas_db() -> tuple[str, ...]:
    """Lista ordenada de colunas para o COPY (deriva do DTO)."""
    return COLUNAS_DB


def normalizar_preco(serie: "pd.Series") -> "pd.Series":
    """Normaliza precos textuais para o formato canonico (ponto decimal).

    Trata o locale BR sem corromper valores que ja usam ponto decimal:
    - "1.234,56" → "1234.56"  (ponto = milhar, virgula = decimal)
    - "1,50"     → "1.50"
    - "1.50"     → "1.50"     (sem virgula, ponto e decimal: preservado)
    - "" / NaN   → ""
    """
    s = serie.fillna("").astype(str).str.strip()
    tem_virgula = s.str.contains(",", regex=False)
    # So remove pontos (milhar) quando ha virgula decimal presente.
    s = s.mask(tem_virgula, s.str.replace(".", "", regex=False))
    s = s.str.replace(",", ".", regex=False)
    s = s.str.replace(r"[^\d.\-]", "", regex=True)
    return s


def normalizar(df: "pd.DataFrame") -> "pd.DataFrame":
    """Renomeia as colunas de origem para o contrato e reordena.

    Com MAPA_ORIGEM preenchido, qualquer coluna canonica ausente vira erro
    (sinal de que o layout da fonte mudou). O transform garante as colunas
    opcionais antes desta chamada (ver _garantir_colunas_canonicas).
    """
    if not MAPA_ORIGEM:
        return df
    df = df.rename(columns=MAPA_ORIGEM)
    faltando = [c for c in COLUNAS_DB if c not in df.columns]
    if faltando:
        raise KeyError(f"colunas ausentes apos normalizacao: {faltando}")
    return df[list(COLUNAS_DB)]

# Materialização de Dataframe normalizando os DTOS tipados 
def to_registros(df: "pd.DataFrame") -> list[PrecoRegistro]:
    """Materializa um DataFrame ja normalizado em DTOs tipados (validados).

    NAO usar no caminho de carga em lote -- e para bordas e testes onde se
    quer trabalhar linha a linha."""
    registros: list[PrecoRegistro] = []
    for linha in df[list(COLUNAS_DB)].to_dict(orient="records"):
        nativo = {k: (v.item() if hasattr(v, "item") else v)
                  for k, v in linha.items()}
        registros.append(PrecoRegistro(**nativo))
    return registros