"""hfbrasil-preco: Pipeline ETL para precos medios hortifruticolas."""

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext, StageStatus
from hfbrasil_preco.orchestrator import executar

__version__ = "0.1.0"

__all__ = [
    "executar",
    "Settings",
    "RunContext",
    "StageStatus",
    "__version__",
]
