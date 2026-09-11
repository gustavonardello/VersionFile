import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from core.paths import data_path

DB_PATH = data_path() / "versionfile.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _tem_dados(conn) -> bool:
    """Indica se o banco já tem conteúdo do usuário (banco recém-criado não tem)."""
    return conn.execute("SELECT EXISTS(SELECT 1 FROM clientes)").fetchone()[0] == 1


def _precisa_migrar(conn) -> bool:
    """
    Informa se `_migrar` tem algum trabalho a fazer. Usado para decidir se vale
    gerar um backup — as mesmas condições verificadas lá dentro.
    """
    colunas_versoes = [r[1] for r in conn.execute("PRAGMA table_info(versoes)").fetchall()]
    if "tipo" not in colunas_versoes:
        return True

    colunas_projetos = [r[1] for r in conn.execute("PRAGMA table_info(projetos)").fetchall()]
    if "descricao" not in colunas_projetos:
        return True

    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='projetos'"
    ).fetchone()
    if create_sql and any(
        f"'{tipo}'" not in create_sql[0] for tipo in ("Regra", "Webservice", "Relatório")
    ):
        return True

    return False


def fazer_backup(conn) -> Path:
    """
    Copia o banco inteiro para um arquivo .bak antes de qualquer alteração de
    schema, usando a API de backup do SQLite (segura com a conexão aberta).

    Backups nunca são removidos automaticamente: são raros — só ocorrem quando
    o schema muda — e apagá-los sozinho contraria a garantia de que o programa
    nunca destrói dado do usuário.
    """
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = DB_PATH.parent / f"versionfile.bak-{carimbo}.db"
    destino_conn = sqlite3.connect(destino)
    try:
        conn.backup(destino_conn)
    finally:
        destino_conn.close()
    return destino


def _migrar(conn):
    """Aplica migrações em uma transação e restaura as chaves estrangeiras."""
    if not _precisa_migrar(conn):
        return
    if conn.in_transaction:
        raise RuntimeError("A migração exige uma conexão sem transação pendente.")
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        _migrar_tabelas(conn)
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError("A migração encontrou referências inválidas no banco.")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys = {foreign_keys}")


def _migrar_tabelas(conn):
    colunas_versoes = [r[1] for r in conn.execute("PRAGMA table_info(versoes)").fetchall()]
    if "tipo" not in colunas_versoes:
        conn.execute(
            "ALTER TABLE versoes ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Criação'"
        )
        conn.execute("UPDATE versoes SET tipo = 'Melhoria' WHERE numero > 1")

    # Migração: adicionar coluna descricao e tipo 'Regra' ao CHECK de projetos
    colunas_projetos = [r[1] for r in conn.execute("PRAGMA table_info(projetos)").fetchall()]
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='projetos'"
    ).fetchone()
    precisa_migrar = (
        "descricao" not in colunas_projetos
        or (create_sql and any(
            f"'{tipo}'" not in create_sql[0] for tipo in ("Regra", "Webservice", "Relatório")
        ))
    )
    if precisa_migrar:
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
        descricao = "descricao" if "descricao" in colunas_projetos else "NULL"
        conn.execute(f"""
            INSERT INTO projetos_new (id, cliente_id, nome, tipo, descricao, criado_em)
            SELECT id, cliente_id, nome, tipo, {descricao}, criado_em FROM projetos
        """)
        conn.execute("DROP TABLE projetos")
        conn.execute("ALTER TABLE projetos_new RENAME TO projetos")


def initialize_db():
    with closing(get_connection()) as conn:
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
        if _precisa_migrar(conn) and _tem_dados(conn):
            destino = fazer_backup(conn)
            print(f"Backup criado antes da migração de schema: {destino}")
        _migrar(conn)
