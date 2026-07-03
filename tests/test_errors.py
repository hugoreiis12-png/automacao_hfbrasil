"""Testes para a hierarquia de erros em hfbrasil_preco/errors.py.

Valida que todas as 17 classes herdam de PipelineError e respeitam
a arvore de heranca documentada.
"""

from __future__ import annotations

import pytest

from hfbrasil_preco.errors import (
    AuditError,
    CheckError,
    ConfigError,
    DBConnectionError,
    DatabaseError,
    DirectoryError,
    DownloadError,
    DownloadTimeoutError,
    DuplicateError,
    EncodingError,
    ExtractError,
    FormFillError,
    LoadError,
    NormalizationError,
    NotifyError,
    NullFieldError,
    ParseError,
    PipelineError,
    ProductNameError,
    QualityGateError,
    QueryError,
    RangeError,
    SiteAccessError,
    TransformError,
)

_TODAS_AS_EXCECOES: list[type[Exception]] = [
    ConfigError,
    SiteAccessError,
    DirectoryError,
    DownloadError,
    DownloadTimeoutError,
    FormFillError,
    EncodingError,
    ParseError,
    ProductNameError,
    NormalizationError,
    DuplicateError,
    NullFieldError,
    RangeError,
    DBConnectionError,
    QueryError,
    LoadError,
    AuditError,
    NotifyError,
]


def test_pipeline_error_base() -> None:
    assert Exception in PipelineError.__bases__
    assert isinstance(PipelineError(), Exception)


def test_todas_herdam_pipeline_error() -> None:
    for cls in _TODAS_AS_EXCECOES:
        assert issubclass(cls, PipelineError), f"{cls.__name__} nao herda de PipelineError"


def test_hierarquia_config() -> None:
    assert issubclass(ConfigError, PipelineError)


def test_hierarquia_check() -> None:
    assert issubclass(SiteAccessError, CheckError)
    assert issubclass(DirectoryError, CheckError)
    assert issubclass(CheckError, PipelineError)


def test_hierarquia_extract() -> None:
    assert issubclass(DownloadError, ExtractError)
    assert issubclass(DownloadTimeoutError, ExtractError)
    assert issubclass(FormFillError, ExtractError)
    assert issubclass(ExtractError, PipelineError)


def test_hierarquia_transform() -> None:
    assert issubclass(EncodingError, TransformError)
    assert issubclass(ParseError, TransformError)
    assert issubclass(ProductNameError, TransformError)
    assert issubclass(NormalizationError, TransformError)
    assert issubclass(TransformError, PipelineError)


def test_hierarquia_quality() -> None:
    assert issubclass(DuplicateError, QualityGateError)
    assert issubclass(NullFieldError, QualityGateError)
    assert issubclass(RangeError, QualityGateError)
    assert issubclass(QualityGateError, PipelineError)


def test_hierarquia_db() -> None:
    assert issubclass(DBConnectionError, DatabaseError)
    assert issubclass(QueryError, DatabaseError)
    assert issubclass(LoadError, DatabaseError)
    assert issubclass(DatabaseError, PipelineError)


def test_hierarquia_audit_notify() -> None:
    assert issubclass(AuditError, PipelineError)
    assert issubclass(NotifyError, PipelineError)


def test_mensagem_e_causa() -> None:
    err = SiteAccessError("site fora do ar")
    assert str(err) == "site fora do ar"

    err2 = ParseError("falha ao parsear")
    assert str(err2) == "falha ao parsear"

    with pytest.raises(ParseError) as exc_info:
        try:
            raise ValueError("causa raiz")
        except ValueError as causa:
            raise ParseError("erro de transformacao") from causa
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert str(exc_info.value.__cause__) == "causa raiz"
