"""Notificacoes: exibe resumo da pipeline ao final.

Canais suportados:
    - "console" → stdout via logger (sempre ativo como fallback)
    - "file"    → arquivo em dados/logs/notify_{run_id}.txt
    - "none"    → apenas log interno
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from hfbrasil_preco.context import StageStatus
from hfbrasil_preco.errors import NotifyError

if TYPE_CHECKING:
    from hfbrasil_preco.config import Settings
    from hfbrasil_preco.context import RunContext


def notificar(
    ctx: RunContext,
    settings: Settings,
    total_registros: int = 0,
) -> None:
    """Dispara notificacao com resumo da pipeline.

    Args:
        ctx: Contexto da execucao.
        settings: Configuracao (canal, notificar_sucesso).
        total_registros: Total de registros inseridos no banco.
    """
    if not _deve_notificar(ctx, settings):
        return

    status_global = _status_pipeline(ctx)
    resumo = _montar_resumo(ctx, status_global, total_registros)

    canal = settings.canal.lower()
    try:
        if canal == "console":
            _notificar_console(ctx, resumo)
        elif canal == "file":
            _notificar_arquivo(ctx, settings, resumo)
        elif canal == "none":
            ctx.logger.info("Notificacao desabilitada (canal=none)")
        else:
            ctx.logger.warning("Canal de notificacao desconhecido: %s", canal)
            _notificar_console(ctx, resumo)
    except Exception as exc:
        raise NotifyError(f"Falha ao notificar pelo canal '{canal}': {exc}") from exc


# ── helpers ──


def _deve_notificar(ctx: RunContext, settings: Settings) -> bool:
    """Decide se deve notificar baseado nas configuracoes."""
    if not settings.notificar_sucesso:
        # So notifica se alguma etapa falhou
        falhou = any(
            s == StageStatus.FAILED for s in ctx.stage_status.values()
        )
        if not falhou:
            ctx.logger.info(
                "Notificacao suprimida (notificar_sucesso=False, todas etapas OK)"
            )
            return False
    return True


def _status_pipeline(ctx: RunContext) -> str:
    """Retorna status consolidado da pipeline."""
    if any(s == StageStatus.FAILED for s in ctx.stage_status.values()):
        return "FALHA"
    if any(s == StageStatus.SKIPPED for s in ctx.stage_status.values()):
        return "CONCLUIDO COM SKIPS"
    if all(s == StageStatus.PASSED for s in ctx.stage_status.values()):
        return "CONCLUIDO"
    return "PARCIAL"


def _montar_resumo(
    ctx: RunContext, status_global: str, total_registros: int
) -> str:
    """Monta o texto do relatorio de execucao."""
    linhas: list[str] = []
    linhas.append("=" * 50)
    linhas.append("  PIPELINE hfbrasil-preco")
    linhas.append("=" * 50)
    linhas.append(f"  Run ID:     {ctx.run_id}")
    linhas.append(f"  Inicio:     {ctx.inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    linhas.append(f"  Duracao:    {ctx.duracao_segundos:.1f}s")
    linhas.append(f"  Status:     {status_global}")
    if total_registros:
        linhas.append(f"  Registros:  {total_registros}")
    linhas.append("")
    linhas.append("  Etapas:")
    for etapa, status in ctx.stage_status.items():
        linhas.append(f"    {etapa:<12} → {status.value}")
    linhas.append("=" * 50)
    return "\n".join(linhas)


def _notificar_console(ctx: RunContext, resumo: str) -> None:
    """Exibe o resumo no console via logger."""
    ctx.logger.info("\n%s", resumo)


def _notificar_arquivo(
    ctx: RunContext, settings: Settings, resumo: str
) -> None:
    """Escreve o resumo em arquivo em dados/logs/."""
    log_dir = settings.logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    arquivo = log_dir / f"notify_{ctx.run_id}.txt"
    try:
        arquivo.write_text(resumo, encoding="utf-8")
        ctx.logger.info("Notificacao salva em: %s", arquivo)
    except OSError as exc:
        raise NotifyError(
            f"Nao foi possivel escrever notificacao em {arquivo}: {exc}"
        ) from exc
