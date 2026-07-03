"""Contexto de execucao: RunContext, StageStatus e logging estruturado.

Cada execucao da pipeline ganha um run_id (UUID) que a acompanha ate
o fim, permitindo rastrear logs, auditoria e eventuais falhas.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4, UUID


# ── status de cada etapa ──


class StageStatus(str, Enum):
    """Situacao de uma etapa (extract / transform / load / quality)."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── contexto compartilhado ──


class RunContext:
    """Agrupa metadados da execucao corrente.

    Attributes:
        run_id: UUID unico desta execucao.
        stage_status: Mapa de etapa -> StageStatus.
        inicio: Timestamp de criacao do contexto.
        settings_ref: Referencia opcional ao Settings (evita import circular).
    """

    def __init__(self) -> None:
        self.run_id: UUID = uuid4()
        self.stage_status: dict[str, StageStatus] = {}
        self.inicio: datetime = datetime.now()
        self._logger: logging.Logger | None = None

    # ── gerenciamento de etapas ──

    def iniciar_etapa(self, etapa: str) -> None:
        self.stage_status[etapa] = StageStatus.RUNNING

    def finalizar_etapa(self, etapa: str, status: StageStatus) -> None:
        self.stage_status[etapa] = status

    def etapa_ok(self, etapa: str) -> bool:
        return self.stage_status.get(etapa) == StageStatus.PASSED

    # ── logger ──

    @property
    def logger(self) -> logging.Logger:
        if self._logger is None:
            self._logger = logging.getLogger(f"hfbrasil.{self.run_id}")
        return self._logger

    def configurar_logger(self, level: int = logging.INFO,
                          log_file: Path | None = None) -> None:
        """Configura handler de console e, opcionalmente, arquivo."""
        logger = self.logger
        logger.setLevel(level)

        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # console
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        # arquivo
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(fmt)
            logger.addHandler(fh)

    # ── duracao ──

    @property
    def duracao_segundos(self) -> float:
        return (datetime.now() - self.inicio).total_seconds()

    def __repr__(self) -> str:
        return (f"RunContext(run_id={self.run_id}, "
                f"inicio={self.inicio.isoformat()})")
