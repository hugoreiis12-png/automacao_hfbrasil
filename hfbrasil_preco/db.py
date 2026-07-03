"""Conexao unica com PostgreSQL (pool simplificado via psycopg2).

Padrao: uma unica conexao por execucao, criada sob demanda e fechada
explicitamente ao final. O Settings define os parametros de conexao.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from hfbrasil_preco.config import DBConfig
from hfbrasil_preco.errors import DBConnectionError


class Database:
    """Gerenciador da conexao PostgreSQL.

    Uso:
        db = Database(config)
        db.connect()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        db.close()
    """

    def __init__(self, config: DBConfig) -> None:
        self._config = config
        self._conn: psycopg2.extensions.connection | None = None

    # ── gerenciamento de ciclo de vida ──

    def connect(self) -> None:
        """Abre (ou reusa) a conexao com o banco."""
        if self._conn is not None and self._conn.closed == 0:
            return
        try:
            self._conn = psycopg2.connect(
                host=self._config.host,
                port=self._config.port,
                dbname=self._config.dbname,
                user=self._config.user,
                password=self._config.password,
            )
            self._conn.autocommit = False
        except psycopg2.Error as exc:
            raise DBConnectionError(
                f"Falha ao conectar em {self._config.host}:{self._config.port}/"
                f"{self._config.dbname}: {exc}"
            ) from exc

    def close(self) -> None:
        """Fecha a conexao se estiver aberta."""
        if self._conn is not None and self._conn.closed == 0:
            self._conn.close()
        self._conn = None

    @property
    def conectado(self) -> bool:
        return self._conn is not None and self._conn.closed == 0

    # ── acesso a cursor ──

    @contextmanager
    def cursor(self) -> Iterator[RealDictCursor]:
        """Retorna um cursor com resultados como dicionarios.

        A transacao deve ser comitada/rollback externamente.
        """
        self.connect()
        assert self._conn is not None
        cur: RealDictCursor = self._conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()

    # ── transacao ──

    def commit(self) -> None:
        if self.conectado:
            assert self._conn is not None
            self._conn.commit()

    def rollback(self) -> None:
        if self.conectado:
            assert self._conn is not None
            self._conn.rollback()

    # ── atalhos para COPY / INSERT em lote ──

    def executar_many(
        self, query: sql.Composable, params: list[tuple[object, ...]]
    ) -> None:
        """Executa um prepared statement para cada tupla em params."""
        with self.cursor() as cur:
            cur.executemany(query, params)

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
