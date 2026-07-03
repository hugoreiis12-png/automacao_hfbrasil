"""Catalogo de erros nomeados da pipeline.

Todos os erros do dominio herdam de PipelineError, que por sua vez
herda de Exception. Isso permite ao orchestrator capturar e tratar
qualquer falha prevista de forma uniforme.
"""

from __future__ import annotations


# ── base ──


class PipelineError(Exception):
    """Raiz de toda excecao intencional da pipeline."""


# ── configuracao ──


class ConfigError(PipelineError):
    """Erro ao carregar ou validar a configuracao (.env / Settings)."""


# ── pre-voo (checks) ──


class CheckError(PipelineError):
    """Falha em uma das verificacoes pre-voo."""


class SiteAccessError(CheckError):
    """Site HF Brasil inacessivel ou retornou erro."""


class DirectoryError(CheckError):
    """Diretorio de saida nao pode ser criado ou acessado."""


# ── extracao (Selenium) ──


class ExtractError(PipelineError):
    """Falha generica na etapa de extracao."""


class DownloadError(ExtractError):
    """Arquivo XLS nao foi baixado ou esta corrompido."""


class DownloadTimeoutError(ExtractError):
    """Tempo limite excedido aguardando o download."""


class FormFillError(ExtractError):
    """Nao foi possivel preencher ou submeter o formulario."""


# ── transformacao ──


class TransformError(PipelineError):
    """Falha generica na etapa de transformacao."""


class EncodingError(TransformError):
    """Erro ao detectar / converter encoding do arquivo."""


class ParseError(TransformError):
    """Arquivo XLS/CSV com formato inesperado ou colunas ausentes."""


class ProductNameError(TransformError):
    """Nao foi possivel extrair o nome do produto do rodape."""


class NormalizationError(TransformError):
    """Falha ao normalizar valores (numeros, datas, categorias)."""


# ── qualidade ──


class QualityGateError(PipelineError):
    """Registro reprovou um dos gates de qualidade."""


class DuplicateError(QualityGateError):
    """Registro duplicado na base de destino."""


class NullFieldError(QualityGateError):
    """Campo obrigatorio nulo ou vazio."""


class RangeError(QualityGateError):
    """Valor numerico fora do intervalo aceitavel."""


# ── banco de dados ──


class DatabaseError(PipelineError):
    """Falha generica de banco de dados."""


class DBConnectionError(DatabaseError):
    """Nao foi possivel conectar ao PostgreSQL."""


class QueryError(DatabaseError):
    """Erro ao executar comando SQL (INSERT, DELETE, SELECT)."""


class LoadError(DatabaseError):
    """Falha na etapa de carga (staging / merge)."""


# ── auditoria ──


class AuditError(PipelineError):
    """Falha ao registrar ou consultar a auditoria."""


# ── notificacao ──


class NotifyError(PipelineError):
    """Falha ao enviar notificacao (console / file / canal externo)."""
