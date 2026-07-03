"""Testes para o modulo report.py.

Testa resumo_precos, exportar_csv, exportar_excel e helpers
com DataFrames mockados — sem dependencia de banco de dados.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pandas as pd
import pytest

from hfbrasil_preco.report import (
    _preco_para_float,
    exportar_csv,
    exportar_excel,
    resumo_precos,
)


# ── fixtures ──


@pytest.fixture
def df_base() -> pd.DataFrame:
    return pd.DataFrame({
        "produto": ["ALFACE", "ALFACE", "TOMATE", "TOMATE"],
        "regiao": ["SP", "SP", "MG", "MG"],
        "preco": ["1,50", "2,00", "3,00", "4,50"],
        "ano": [2026, 2026, 2026, 2026],
        "mes": [1, 2, 1, 2],
        "dia": [10, 15, 10, 15],
    })


@pytest.fixture
def tmp_path() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as d:
        yield d


# ── resumo_precos ──


def test_resumo_precos_com_dados(df_base: pd.DataFrame) -> None:
    resumo = resumo_precos(df_base)
    assert not resumo.empty
    assert list(resumo.columns) == [
        "produto", "regiao", "ocorrencias",
        "preco_medio", "preco_mediano", "preco_min", "preco_max",
    ]
    assert len(resumo) == 2  # 2 grupos: ALFACE/SP e TOMATE/MG

    alface = resumo[resumo["produto"] == "ALFACE"].iloc[0]
    assert alface["ocorrencias"] == 2
    assert alface["preco_medio"] == 1.75
    assert alface["preco_min"] == 1.50
    assert alface["preco_max"] == 2.00


def test_resumo_precos_vazio() -> None:
    vazio = resumo_precos(pd.DataFrame())
    assert vazio.empty
    assert list(vazio.columns) == [
        "produto", "regiao", "ocorrencias",
        "preco_medio", "preco_mediano", "preco_min", "preco_max",
    ]


def test_resumo_precos_sem_preco() -> None:
    df = pd.DataFrame({"produto": ["ALFACE"], "regiao": ["SP"]})
    resumo = resumo_precos(df)
    assert resumo.empty
    assert list(resumo.columns) == [
        "produto", "regiao", "ocorrencias",
        "preco_medio", "preco_mediano", "preco_min", "preco_max",
    ]


def test_resumo_precos_preco_invalido() -> None:
    df = pd.DataFrame({
        "produto": ["ALFACE"],
        "regiao": ["SP"],
        "preco": ["INVALIDO"],
    })
    resumo = resumo_precos(df)
    assert not resumo.empty
    assert pd.isna(resumo["preco_medio"].iloc[0])


# ── _preco_para_float ──


def test_preco_br_para_float() -> None:
    df = pd.DataFrame({"preco": ["1.234,56", "0,99", "1.000.000,00"]})
    resultado = _preco_para_float(df)
    esperado = [1234.56, 0.99, 1000000.00]
    assert resultado["preco"].tolist() == esperado


def test_preco_para_float_coluna_ausente() -> None:
    df = pd.DataFrame({"outra": ["x"]})
    resultado = _preco_para_float(df)
    assert "outra" in resultado.columns
    assert len(resultado) == 1


# ── exportar_csv ──


def test_exportar_csv(df_base: pd.DataFrame, tmp_path: str) -> None:
    caminho = os.path.join(tmp_path, "teste.csv")
    resultado = exportar_csv(df_base, caminho)
    assert os.path.isfile(resultado)
    lido = pd.read_csv(resultado)
    assert len(lido) == 4


def test_exportar_csv_dataframe_vazio(tmp_path: str) -> None:
    caminho = os.path.join(tmp_path, "vazio.csv")
    resultado = exportar_csv(pd.DataFrame(), caminho)
    assert os.path.isfile(resultado)


# ── exportar_excel ──


@pytest.mark.skipif(
    not os.environ.get("OPENPYXL_TEST"),
    reason="OPENPYXL_TEST nao definido; exportar_excel requer openpyxl instalado",
)
def test_exportar_excel(df_base: pd.DataFrame, tmp_path: str) -> None:
    caminho = os.path.join(tmp_path, "teste.xlsx")
    resultado = exportar_excel(df_base, caminho)
    assert os.path.isfile(resultado)
    lido = pd.read_excel(resultado, engine="openpyxl")
    assert len(lido) == 4
