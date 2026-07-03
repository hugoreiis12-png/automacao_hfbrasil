"""Verificacoes pre-voo: site acessivel, diretorios viaveis.

Antes de iniciar o pipeline, garante que:
    1. O site HF Brasil esta respondendo (se habilitado)
    2. Os diretorios de saida existem ou podem ser criados
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext, StageStatus
from hfbrasil_preco.errors import DirectoryError, SiteAccessError


def verificar(settings: Settings, ctx: RunContext) -> bool:
    """Executa todas as verificacoes pre-voo.

    Returns:
        True se todas passaram.

    Raises:
        SiteAccessError: site inacessivel ou retornou erro.
        DirectoryError: diretorio nao pode ser criado/acessado.
    """
    ctx.iniciar_etapa("checks")
    ctx.logger.info("Iniciando verificacoes pre-voo")

    try:
        if settings.verificar_site and not settings.dry_run:
            _verificar_site(settings, ctx)

        _verificar_diretorios(settings, ctx)

        ctx.finalizar_etapa("checks", StageStatus.PASSED)
        ctx.logger.info("Todas as verificacoes pre-voo passaram")
        return True
    except Exception:
        ctx.finalizar_etapa("checks", StageStatus.FAILED)
        raise


def _verificar_site(settings: Settings, ctx: RunContext) -> None:
    """Verifica se o site HF Brasil responde HTTP 200."""
    ctx.logger.info("Verificando site: %s", settings.site_url)

    req = Request(
        settings.site_url,
        headers={"User-Agent": "Mozilla/5.0 (compativel; hfbrasil-preco/0.1)"},
    )

    try:
        with urlopen(req, timeout=10) as resp:
            status = resp.status
            if status != 200:
                raise SiteAccessError(
                    f"Site retornou HTTP {status} (esperado 200): "
                    f"{settings.site_url}"
                )
            ctx.logger.info("  Site OK (HTTP %d)", status)
    except URLError as exc:
        raise SiteAccessError(
            f"Nao foi possivel acessar {settings.site_url}: {exc.reason}"
        ) from exc
    except OSError as exc:
        raise SiteAccessError(
            f"Erro de rede ao acessar {settings.site_url}: {exc}"
        ) from exc


def _verificar_diretorios(settings: Settings, ctx: RunContext) -> None:
    """Verifica/cria os diretorios de saida da pipeline."""
    diretorios: list[tuple[str, Path]] = [
        ("xlsx", settings.xlsx_dir),
        ("csv", settings.csv_dir),
        ("logs", settings.logs_dir),
    ]

    for nome, path in diretorios:
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Testa escrita
            teste = path / ".hf_check"
            teste.write_text("")
            teste.unlink()
            ctx.logger.info("  Diretorio %s: %s (OK)", nome, path)
        except OSError as exc:
            raise DirectoryError(
                f"Diretorio '{nome}' em {path} nao pode ser criado/acessado: {exc}"
            ) from exc
