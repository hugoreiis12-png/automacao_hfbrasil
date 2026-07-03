"""Etapa de extracao: Selenium + Chrome baixa XLS do HF Brasil.

Para cada produto definido em Settings.produtos:
    1. Navega ate o formulario
    2. Seleciona produto, regiao, periodo, periodicidade
    3. Submete o formulario
    4. Aguarda download do XLS
    5. Move o arquivo para dados/xlsx/
"""

from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.common import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.wait import WebDriverWait

from hfbrasil_preco.config import Settings
from hfbrasil_preco.context import RunContext, StageStatus
from hfbrasil_preco.errors import (
    DownloadError,
    DownloadTimeoutError,
    FormFillError,
)


def extrair(settings: Settings, ctx: RunContext) -> list[Path]:
    """Executa a extracao completa para todos os produtos configurados.

    Retorna lista de caminhos absolutos dos arquivos XLS baixados.
    """
    ctx.iniciar_etapa("extract")
    settings.xlsx_dir.mkdir(parents=True, exist_ok=True)

    if settings.dry_run:
        ctx.logger.info("[dry-run] Extracao simulado — nenhum download sera realizado")
        ctx.finalizar_etapa("extract", StageStatus.SKIPPED)
        return []

    driver = _init_driver(settings)
    downloads: list[Path] = []

    try:
        for produto_nome, produto_valor in settings.produtos.items():
            arquivo = _extrair_produto_com_retry(
                driver, settings, ctx, produto_nome, produto_valor
            )
            if arquivo:
                downloads.append(arquivo)
    except Exception:
        ctx.finalizar_etapa("extract", StageStatus.FAILED)
        raise
    else:
        ctx.finalizar_etapa("extract", StageStatus.PASSED)
        return downloads
    finally:
        driver.quit()


# ── helpers internos ──


def _init_driver(settings: Settings) -> WebDriver:
    """Configura Chrome com as opcoes da pipeline.

    Dois modos de resolver o driver:
    - settings.chromedriver_path definido (Docker) -> usa o chromedriver do
      sistema (apt), determinístico e sem acesso a rede em runtime.
    - vazio (dev local) -> webdriver-manager baixa o driver compatível. O
      import de webdriver_manager e feito aqui (lazy) de proposito: o modulo
      de config chama load_dotenv() no import, o que injetaria o .env em
      os.environ e faria variaveis PG_* vencerem o --env. Importando so
      quando a extracao realmente roda, o Settings.load(--env) ja foi
      construido e nao e afetado.
    """
    chrome_options = Options()
    if settings.headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    if settings.chrome_binary:
        chrome_options.binary_location = settings.chrome_binary

    prefs = {
        "download.default_directory": str(settings.xlsx_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if settings.chromedriver_path:
        service = Service(settings.chromedriver_path)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def _extrair_produto_com_retry(
    driver: WebDriver,
    settings: Settings,
    ctx: RunContext,
    produto_nome: str,
    produto_valor: int,
) -> Path | None:
    """Tenta extrair um produto com retry e backoff."""
    for tentativa in range(1, settings.max_tentativas + 1):
        try:
            return _extrair_produto(driver, settings, ctx, produto_nome, produto_valor)
        except (FormFillError, DownloadError, DownloadTimeoutError) as exc:
            ctx.logger.warning(
                "Tentativa %d/%d falhou para %s: %s",
                tentativa,
                settings.max_tentativas,
                produto_nome,
                exc,
            )
            if tentativa < settings.max_tentativas:
                time.sleep(settings.backoff_s)
            else:
                ctx.logger.error(
                    "Produto %s esgotou tentativas — pulando", produto_nome
                )
                return None
    return None


def _extrair_produto(
    driver: WebDriver,
    settings: Settings,
    ctx: RunContext,
    produto_nome: str,
    produto_valor: int,
) -> Path:
    """Extrai um unico produto: preenche formulario e baixa XLS."""
    ctx.logger.info("Extraindo: %s (radio value=%s)", produto_nome, produto_valor)

    driver.get(settings.site_url)
    wait: WebDriverWait[WebDriver] = WebDriverWait(driver, settings.postback_timeout)

    try:
        # 1. Selecionar radio do produto
        _selecionar_produto(driver, wait, produto_valor)

        # 2. Aguarda regioes carregarem e marca "Todos"
        _selecionar_todas_regioes(driver, wait)

        # 3. Definir ano inicial / final
        _definir_ano(driver, settings)

        # 4. Definir periodicidade
        _definir_periodicidade(driver, wait, settings)

        # 5. Submeter formulario (apenas exibe os resultados na pagina)
        _clicar_filtrar(driver, wait)

        # 6. Clicar em "Exportar para Excel" (dispara o download do XLS)
        _clicar_exportar(driver, wait)

    except TimeoutException as exc:
        raise FormFillError(
            f"Timeout ao preencher form para {produto_nome}: {exc}"
        ) from exc

    # 7. Aguardar download
    arquivo = _aguardar_download(settings, ctx, produto_nome)
    ctx.logger.info("Download concluido: %s", arquivo)
    return arquivo


def _selecionar_produto(driver: WebDriver, wait: WebDriverWait[WebDriver], valor: int) -> None:
    """Clica no radio do produto."""
    radio = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, f"input[name='produto'][value='{valor}']")
        )
    )
    radio.click()


def _selecionar_todas_regioes(driver: WebDriver, wait: WebDriverWait[WebDriver]) -> None:
    """Aguarda o carregamento das regioes (AJAX) e marca 'Todos'.

    A div #frm-check-regiao passa por 'Selecione um produto' -> 'Carregando...'
    -> lista de checkboxes (postback apos selecionar o produto). Esperar so o
    texto mudar nao basta: 'Carregando...' ja satisfaz essa condicao e o form
    e preenchido cedo demais. Aguardamos os checkboxes de regiao REAIS
    aparecerem (>= 2) e o texto nao estar mais 'Carregando...'.
    """
    def _regioes_carregadas(d: WebDriver) -> bool:
        try:
            div = d.find_element(By.ID, "frm-check-regiao")
            if "Carregando" in div.text:
                return False
            checkboxes = div.find_elements(By.CSS_SELECTOR, "input[type=checkbox]")
            return len(checkboxes) >= 2
        except (NoSuchElementException, StaleElementReferenceException):
            return False

    wait.until(_regioes_carregadas)
    # Marca "Todos" (mini-checkbox)
    todos = driver.find_element(By.CSS_SELECTOR, "input[name='todos_regiao']")
    if not todos.is_selected():
        todos.click()


def _definir_ano(driver: WebDriver, settings: Settings) -> None:
    """Seleciona ano_inicial e ano_final nos dropdowns."""
    Select(
        driver.find_element(By.ID, "imagenet-txt-formulario-ano-inicial")
    ).select_by_value(str(settings.ano))
    Select(
        driver.find_element(By.ID, "imagenet-txt-formulario-ano-final")
    ).select_by_value(str(settings.ano))


def _definir_periodicidade(
    driver: WebDriver, wait: WebDriverWait[WebDriver], settings: Settings
) -> None:
    """Seleciona o radio de periodicidade (diario/mensal/anual)."""
    valor = settings.periodicidade.lower()
    radio = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, f"input[name='periodicidade'][value='{valor}']")
        )
    )
    if not radio.is_selected():
        radio.click()


def _clicar_filtrar(driver: WebDriver, wait: WebDriverWait[WebDriver]) -> None:
    """Clica no botao 'Filtrar' e aguarda o inicio do download."""
    btn = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button.imagenet-btn-busca-preco")
        )
    )
    btn.click()


def _clicar_exportar(driver: WebDriver, wait: WebDriverWait[WebDriver]) -> None:
    """Clica em 'Exportar para Excel' — e este clique que baixa o XLS.

    O botao 'Filtrar' apenas renderiza os resultados na pagina; o arquivo de
    dados filtrados so e baixado ao clicar neste link (a.imagenet-exportar),
    que aponta para /br/estatistica/preco/exportar.aspx e aparece somente
    apos o filtro retornar resultados.
    """
    link = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "a.imagenet-exportar")
        )
    )
    link.click()


def _aguardar_download(
    settings: Settings, ctx: RunContext, produto_nome: str
) -> Path:
    """Monitora o diretorio de download ate um novo XLS aparecer.

    Retorna o caminho absoluto do arquivo baixado.
    """
    xlsx_dir = settings.xlsx_dir.resolve()
    antes = {p.name for p in xlsx_dir.glob("*.xlsx")}

    fim = time.time() + settings.download_timeout
    while time.time() < fim:
        time.sleep(1)
        novos = [
            p for p in xlsx_dir.glob("*.xlsx")
            if p.name not in antes and p.stat().st_size > 0
        ]
        if len(novos) >= 1:
            arquivo = novos[0]
            if arquivo.stat().st_size < 1024:
                raise DownloadError(
                    f"Arquivo corrompido / muito pequeno: {arquivo.name} "
                    f"({arquivo.stat().st_size} bytes)"
                )
            return _renomear_arquivo(arquivo, settings, produto_nome)

    raise DownloadTimeoutError(
        f"Timeout de {settings.download_timeout}s aguardando XLS "
        f"para produto '{produto_nome}' em {xlsx_dir}"
    )


def _renomear_arquivo(
    arquivo: Path, settings: Settings, produto_nome: str
) -> Path:
    """Renomeia o XLS baixado para um nome padrao (com retry no Windows)."""
    novo_nome = settings.xlsx_dir / f"{produto_nome}_{settings.ano}.xlsx"
    for tentativa in range(5):
        try:
            if novo_nome.exists():
                novo_nome.unlink()
            arquivo.rename(novo_nome)
            return novo_nome.resolve()
        except PermissionError:
            if tentativa < 4:
                time.sleep(2)
                continue
            raise
    # Nunca deve chegar aqui (ou retorna ou raise no ultimo ciclo)
    raise RuntimeError(f"Nao foi possivel renomear {arquivo.name} para {novo_nome.name} apos 5 tentativas")
