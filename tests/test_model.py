"""Testes para o modelo de dominio em hfbrasil_preco/model.py.

Cobre: PrecoRegistro DTO, COLUNAS_DB, MAPA_ORIGEM, normalizar(), to_registros().
"""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from hfbrasil_preco.model import (
    COLUNAS_DB,
    MAPA_ORIGEM,
    PrecoRegistro,
    colunas_db,
    normalizar,
    to_registros,
)

_COLUNAS_ESPERADAS: list[str] = [
    "produto", "regiao", "dia", "mes", "ano", "moeda", "unidade", "preco",
]


# ── PrecoRegistro DTO ──


def test_preco_registro_campos() -> None:
    campos = list(PrecoRegistro.model_fields.keys())
    assert campos == _COLUNAS_ESPERADAS


def test_preco_registro_tipos() -> None:
    fields = PrecoRegistro.model_fields
    assert fields["produto"].annotation is str
    assert fields["regiao"].annotation is str
    assert fields["dia"].annotation is int
    assert fields["mes"].annotation is int
    assert fields["ano"].annotation is int
    assert fields["moeda"].annotation is str
    assert fields["unidade"].annotation is str
    assert fields["preco"].annotation is str


def test_preco_registro_all_required() -> None:
    with pytest.raises(ValidationError):
        PrecoRegistro()  # type: ignore[call-arg]


def test_preco_registro_valid() -> None:
    r = PrecoRegistro(
        produto="ALFACE", regiao="SP", dia=10, mes=1, ano=2026,
        moeda="R$", unidade="kg", preco="1,50",
    )
    assert r.produto == "ALFACE"
    assert r.dia == 10
    assert r.preco == "1,50"


# ── COLUNAS_DB ──


def test_colunas_db_ordem() -> None:
    assert list(COLUNAS_DB) == _COLUNAS_ESPERADAS


def test_colunas_db_conteudo() -> None:
    assert "produto" in COLUNAS_DB
    assert "preco" in COLUNAS_DB
    assert "ano" in COLUNAS_DB
    assert len(COLUNAS_DB) == 8


def test_colunas_db_funcao() -> None:
    assert colunas_db() == COLUNAS_DB


# ── MAPA_ORIGEM ──


def test_mapa_origem_chaves() -> None:
    chaves_esperadas = {
        "Produto", "Regiao", "Região", "Dia", "Mes", "Mês",
        "Ano", "Moeda", "Unidade", "Preco", "Preço",
    }
    assert set(MAPA_ORIGEM.keys()) == chaves_esperadas


def test_mapa_origem_valores() -> None:
    for valor in MAPA_ORIGEM.values():
        assert valor in COLUNAS_DB, f"{valor} nao esta em COLUNAS_DB"


# ── normalizar ──


def test_normalizar_colunas_validas() -> None:
    df = pd.DataFrame([
        {"Regiao": "SP", "Preco": "1,50", "Dia": 10, "Mes": 1,
         "Ano": 2026, "Moeda": "R$", "Unidade": "kg", "produto": "ALFACE"},
    ])
    resultado = normalizar(df)
    assert list(resultado.columns) == _COLUNAS_ESPERADAS
    assert resultado.iloc[0]["regiao"] == "SP"
    assert resultado.iloc[0]["preco"] == "1,50"


def test_normalizar_coluna_ausente() -> None:
    df = pd.DataFrame([{"Regiao": "SP", "Preco": "1,50"}])
    with pytest.raises(KeyError):
        normalizar(df)


def test_normalizar_df_vazio() -> None:
    df = pd.DataFrame({"produto": [], "Regiao": [], "Dia": [], "Mes": [],
                        "Ano": [], "Moeda": [], "Unidade": [], "Preco": []})
    resultado = normalizar(df)
    assert list(resultado.columns) == _COLUNAS_ESPERADAS
    assert len(resultado) == 0


# ── to_registros ──


def test_to_registros() -> None:
    df = pd.DataFrame([{
        "produto": "ALFACE", "regiao": "SP", "dia": 10, "mes": 1,
        "ano": 2026, "moeda": "R$", "unidade": "kg", "preco": "1,50",
    }])
    registros = to_registros(df)
    assert len(registros) == 1
    r = registros[0]
    assert isinstance(r, PrecoRegistro)
    assert r.produto == "ALFACE"
    assert r.preco == "1,50"


def test_to_registros_vazio() -> None:
    df = pd.DataFrame(columns=_COLUNAS_ESPERADAS)
    assert to_registros(df) == []


def test_to_registros_tipos_nativos() -> None:
    import numpy as np

    df = pd.DataFrame([{
        "produto": "TOMATE", "regiao": "MG", "dia": np.int64(5),
        "mes": np.int64(3), "ano": np.int64(2026),
        "moeda": "R$", "unidade": "kg", "preco": "3,00",
    }])
    registros = to_registros(df)
    r = registros[0]
    assert isinstance(r.dia, int)
    assert isinstance(r.mes, int)
    assert isinstance(r.ano, int)
