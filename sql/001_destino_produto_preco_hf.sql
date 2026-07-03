-- ============================================================
-- DDL: tabela destino produto_preco_hf
-- Schema: hfbrasil_preco (criado automaticamente se nao existir)
-- NOTA: DDL gerado a partir do schema real do banco (information_schema)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS hfbrasil_preco;

CREATE TABLE IF NOT EXISTS hfbrasil_preco.produto_preco_hf (
    id_tabela   SERIAL          PRIMARY KEY,
    produto     VARCHAR(355),
    regiao      VARCHAR(355),
    dia         INTEGER,
    mes         INTEGER,
    ano         INTEGER,
    moeda       VARCHAR(255),
    unidade     VARCHAR(255),
    preco       VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_produto_preco_hf_ano
    ON hfbrasil_preco.produto_preco_hf (ano);

CREATE INDEX IF NOT EXISTS idx_produto_preco_hf_produto
    ON hfbrasil_preco.produto_preco_hf (produto);
