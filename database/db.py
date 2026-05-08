import sqlite3
import os
from pathlib import Path
from core.paths import data_path

DB_PATH = data_path() / "versionfile.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrar(conn):
    """Aplica migrações incrementais sem recriar o banco."""
    colunas = [r[1] for r in conn.execute("PRAGMA table_info(versoes)").fetchall()]
    if "tipo" not in colunas:
        conn.execute(
            "ALTER TABLE versoes ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Criação'"
        )
        # Versão 1 de cada regra já é Criação — as demais ficam como Melhoria por padrão
        conn.execute(
            "UPDATE versoes SET tipo = 'Melhoria' WHERE numero > 1"
        )
        conn.commit()


def initialize_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                nome    TEXT NOT NULL UNIQUE,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS projetos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id  INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                nome        TEXT NOT NULL,
                tipo        TEXT NOT NULL CHECK(tipo IN ('DID', 'Projeto')),
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(cliente_id, nome)
            );

            CREATE TABLE IF NOT EXISTS regras (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                projeto_id  INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
                numero      TEXT NOT NULL,
                descricao   TEXT,
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(projeto_id, numero)
            );

            CREATE TABLE IF NOT EXISTS versoes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                regra_id    INTEGER NOT NULL REFERENCES regras(id) ON DELETE CASCADE,
                numero      INTEGER NOT NULL,
                conteudo    TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'Em desenvolvimento'
                                CHECK(status IN (
                                    'Em desenvolvimento',
                                    'Em teste',
                                    'Produção',
                                    'Depreciada'
                                )),
                notas       TEXT,
                atual       INTEGER NOT NULL DEFAULT 0 CHECK(atual IN (0, 1)),
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(regra_id, numero)
            );
        """)
        _migrar(conn)
