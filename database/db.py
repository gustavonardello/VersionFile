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
    colunas_versoes = [r[1] for r in conn.execute("PRAGMA table_info(versoes)").fetchall()]
    if "tipo" not in colunas_versoes:
        conn.execute(
            "ALTER TABLE versoes ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Criação'"
        )
        conn.execute("UPDATE versoes SET tipo = 'Melhoria' WHERE numero > 1")
        conn.commit()

    # Migração: adicionar coluna descricao e tipo 'Regra' ao CHECK de projetos
    colunas_projetos = [r[1] for r in conn.execute("PRAGMA table_info(projetos)").fetchall()]
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='projetos'"
    ).fetchone()
    precisa_migrar = (
        "descricao" not in colunas_projetos
        or (create_sql and "'Regra'" not in create_sql[0])
    )
    if precisa_migrar:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE projetos_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id  INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                nome        TEXT NOT NULL,
                tipo        TEXT NOT NULL CHECK(tipo IN ('DID', 'Projeto', 'Regra', 'Webservice', 'Relatório')),
                descricao   TEXT,
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(cliente_id, nome)
            )
        """)
        conn.execute("""
            INSERT INTO projetos_new (id, cliente_id, nome, tipo, criado_em)
            SELECT id, cliente_id, nome, tipo, criado_em FROM projetos
        """)
        conn.execute("DROP TABLE projetos")
        conn.execute("ALTER TABLE projetos_new RENAME TO projetos")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")

    # Migração: adicionar tipos 'Webservice' e 'Relatório' ao CHECK de projetos
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='projetos'"
    ).fetchone()
    if create_sql and "'Webservice'" not in create_sql[0]:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE projetos_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id  INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                nome        TEXT NOT NULL,
                tipo        TEXT NOT NULL CHECK(tipo IN ('DID', 'Projeto', 'Regra', 'Webservice', 'Relatório')),
                descricao   TEXT,
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(cliente_id, nome)
            )
        """)
        conn.execute("""
            INSERT INTO projetos_new (id, cliente_id, nome, tipo, descricao, criado_em)
            SELECT id, cliente_id, nome, tipo, descricao, criado_em FROM projetos
        """)
        conn.execute("DROP TABLE projetos")
        conn.execute("ALTER TABLE projetos_new RENAME TO projetos")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


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
                tipo        TEXT NOT NULL CHECK(tipo IN ('DID', 'Projeto', 'Regra', 'Webservice', 'Relatório')),
                descricao   TEXT,
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
