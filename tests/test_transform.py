"""Testes para a etapa de transformacao em hfbrasil_preco/stages/transform.py.

Cobre: _extrair_produto, _ler_xls, _normalizar_colunas, _ajustar_tipos,
_salvar_csv e transformar (fluxo completo com fixture XLS inline).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext
from hfbrasil_preco.stages.transform import (
    _ajustar_tipos,
    _extrair_produto,
    _ler_xls,
    _normalizar_colunas,
    _salvar_csv_canonico,
    _salvar_csv_original,
    _salvar_xlsx_limpo,
    transformar,
)


# ── fixtures ──


@pytest.fixture
def tmp_base() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def settings(tmp_base: str) -> Settings:
    return Settings(base_dir=Path(tmp_base))


@pytest.fixture
def ctx() -> RunContext:
    return RunContext()


@pytest.fixture
def xls_path(tmp_base: str) -> Generator[str, None, None]:
    path = os.path.join(tmp_base, "ALFACE_2026.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["Regiao", "Preco", "Dia", "Mes", "Ano", "Moeda", "Unidade"])
    ws.append(["SP", "1,50", 10, 1, 2026, "R$", "kg"])
    ws.append(["RJ", "2,00", 11, 1, 2026, "R$", "kg"])
    wb.save(path)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ── _extrair_produto ──


def test_extrair_produto_padrao() -> None:
    assert _extrair_produto(Path("ALFACE_2026.xlsx")) == "ALFACE"


def test_extrair_produto_case_insensitive() -> None:
    assert _extrair_produto(Path("tomate_2026.xlsx")) == "TOMATE"


def test_extrair_produto_fallback() -> None:
    assert _extrair_produto(Path("CEBOLA_xyz.xlsx")) == "CEBOLA"


def test_extrair_produto_invalido() -> None:
    assert _extrair_produto(Path("_2026.xlsx")) is None


# ── _ler_xls ──


def test_ler_xls_valido(xls_path: str) -> None:
    df = _ler_xls(Path(xls_path))
    assert not df.empty
    assert "Regiao" in df.columns
    assert "Preco" in df.columns
    assert len(df) == 2  # 2 linhas de dados


def test_ler_xls_inexistente() -> None:
    from hfbrasil_preco.errors import ParseError
    with pytest.raises(ParseError):
        _ler_xls(Path("nao_existe.xlsx"))


# ── _normalizar_colunas ──


def test_normalizar_mapa_exato() -> None:
    df = pd.DataFrame([{"Regiao": "SP", "Preco": "1,50"}])
    resultado = _normalizar_colunas(df)
    assert "regiao" in resultado.columns
    assert "preco" in resultado.columns


def test_normalizar_heuristico() -> None:
    df = pd.DataFrame([{"preço médio": "1,50", "cotação": "3,00"}])
    resultado = _normalizar_colunas(df)
    assert "preco" in resultado.columns
    # "cotação" contém "preco"? não — "cotação" não mapeia para nada
    # "preço médio" → "preco" (via heurística parcial)


def test_normalizar_sem_match() -> None:
    df = pd.DataFrame([{"coluna_estranha": "x"}])
    resultado = _normalizar_colunas(df)
    assert resultado.empty


def test_normalizar_misto() -> None:
    df = pd.DataFrame([{"Regiao": "SP", "Valor": "1,50", "Ano": "2026"}])
    resultado = _normalizar_colunas(df)
    assert "regiao" in resultado.columns
    assert "preco" in resultado.columns  # "Valor" → "preco" via heurística
    assert "ano" in resultado.columns


# ── _ajustar_tipos ──


def test_ajustar_preco_br() -> None:
    df = pd.DataFrame({"preco": ["1.234,56", "0,99", "1.000.000,00"]})
    resultado = _ajustar_tipos(df)
    assert resultado["preco"].tolist() == ["1234.56", "0.99", "1000000.00"]


def test_ajustar_preco_simples() -> None:
    df = pd.DataFrame({"preco": ["1,50", "2,00"]})
    resultado = _ajustar_tipos(df)
    assert resultado["preco"].tolist() == ["1.50", "2.00"]


def test_ajustar_int_colunas() -> None:
    df = pd.DataFrame({"dia": ["10", ""], "mes": ["1", "abc"], "ano": ["2026", "2025"]})
    resultado = _ajustar_tipos(df)
    assert resultado["dia"].tolist() == [10, 0]
    assert resultado["mes"].tolist() == [1, 0]
    assert resultado["ano"].tolist() == [2026, 2025]
    assert resultado["dia"].dtype == int


def test_ajustar_preco_vazio() -> None:
    df = pd.DataFrame({"preco": [None, "", "1,50"]})
    resultado = _ajustar_tipos(df)
    assert resultado["preco"].tolist() == ["", "", "1.50"]


# ── _salvar_csv ──


def test_salvar_csv_canonico(settings: Settings) -> None:
    settings.csv_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"produto": ["ALFACE"], "preco": ["1,50"]})
    xls_path = settings.base_dir / "ALFACE_2026.xlsx"
    csv_path = _salvar_csv_canonico(df, xls_path, settings)
    assert csv_path.exists()
    assert csv_path.name == "ALFACE_2026_db.csv", f"Esperado '_db' suffix, obtido: {csv_path.name}"
    lido = pd.read_csv(csv_path)
    assert len(lido) == 1
    assert lido["produto"].iloc[0] == "ALFACE"


def test_salvar_csv_original(settings: Settings) -> None:
    settings.csv_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"Produto": ["ALFACE"], "Preço": ["1,50"]})
    csv_path = settings.csv_dir / "ALFACE_2026.csv"
    _salvar_csv_original(df, csv_path)
    assert csv_path.exists()
    lido = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig")
    assert len(lido) == 1
    assert "Produto" in lido.columns


def test_salvar_xlsx_limpo(settings: Settings, ctx: RunContext) -> None:
    import tempfile
    import os
    xlsx_dir = settings.base_dir / "xlsx"
    xlsx_dir.mkdir(parents=True, exist_ok=True)
    xls_path = xlsx_dir / "ALFACE_2026.xlsx"
    df = pd.DataFrame({"Produto": ["ALFACE"]})
    _salvar_xlsx_limpo(df, xls_path, settings, ctx)
    assert xls_path.exists()
    lido = pd.read_excel(xls_path, engine="openpyxl")
    assert "Produto" in lido.columns


# ── transformar (fluxo completo) ──


def test_transformar_com_xls(settings: Settings, ctx: RunContext, xls_path: str) -> None:
    csvs = transformar(settings, ctx, [Path(xls_path)])
    assert len(csvs) == 1
    csv_path = csvs[0]
    assert csv_path.exists()
    assert csv_path.name.endswith("_db.csv"), f"Esperado CSV canonico, obtido: {csv_path.name}"
    lido = pd.read_csv(csv_path)
    assert not lido.empty
    assert "produto" in lido.columns
    assert lido["produto"].iloc[0] == "ALFACE"

    # Verifica que o CSV original e XLSX limpo tambem foram gerados
    xls_path_obj = Path(xls_path)
    csv_original = settings.csv_dir / xls_path_obj.with_suffix(".csv").name
    assert csv_original.exists(), "CSV original nao foi gerado"
    assert xls_path_obj.exists(), "XLSX limpo foi sobrescrito"


def test_transformar_sem_xls(settings: Settings, ctx: RunContext) -> None:
    csvs = transformar(settings, ctx, [])
    assert csvs == []
