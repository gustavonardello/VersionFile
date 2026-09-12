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

    tabelas = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "portas" not in tabelas:
        return True

    colunas_regras = [r[1] for r in conn.execute("PRAGMA table_info(regras)").fetchall()]
    if "porta_id" not in colunas_regras:
        return True

    indices_regras = {
        r[1] for r in conn.execute("PRAGMA index_list(regras)").fetchall()
    }
    if "idx_regra_unica_por_porta" not in indices_regras:
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

    # Webservices possuem um nível adicional entre projeto e regra.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS portas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            projeto_id  INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
            numero      TEXT NOT NULL,
            criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(projeto_id, numero)
        )
    """)
    colunas_regras = [r[1] for r in conn.execute("PRAGMA table_info(regras)").fetchall()]
    if "porta_id" not in colunas_regras:
        conn.execute(
            "ALTER TABLE regras ADD COLUMN porta_id INTEGER REFERENCES portas(id) ON DELETE CASCADE"
        )

    # Regras de Webservice criadas por versões anteriores não tinham porta.
    # Elas são preservadas sob um agrupador explícito, sem inferir um número.
    projetos_legados = conn.execute("""
        SELECT DISTINCT p.id
          FROM projetos p
          JOIN regras r ON r.projeto_id = p.id
         WHERE p.tipo = 'Webservice' AND r.porta_id IS NULL
    """).fetchall()
    for projeto in projetos_legados:
        projeto_id = projeto[0]
        conn.execute(
            "INSERT OR IGNORE INTO portas (projeto_id, numero) VALUES (?, 'Sem porta')",
            (projeto_id,),
        )
        porta_id = conn.execute(
            "SELECT id FROM portas WHERE projeto_id = ? AND numero = 'Sem porta'",
            (projeto_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE regras SET porta_id = ? WHERE projeto_id = ? AND porta_id IS NULL",
            (porta_id, projeto_id),
        )

    # Cada porta representa diretamente um único conteúdo versionado na UI.
    # Se uma versão intermediária agrupou várias regras na mesma porta, mantém
    # a primeira e separa as demais sem descartar conteúdo ou versões.
    portas_com_varias_regras = conn.execute("""
        SELECT po.id, po.projeto_id, po.numero
          FROM portas po
          JOIN regras r ON r.porta_id = po.id
         GROUP BY po.id, po.projeto_id, po.numero
        HAVING COUNT(r.id) > 1
    """).fetchall()
    for porta in portas_com_varias_regras:
        regras = conn.execute(
            "SELECT id, numero FROM regras WHERE porta_id = ? ORDER BY id",
            (porta[0],),
        ).fetchall()
        for regra in regras[1:]:
            base = f"{porta[2]} - {regra[1]}"
            numero = base
            sufixo = 2
            while conn.execute(
                "SELECT 1 FROM portas WHERE projeto_id = ? AND numero = ?",
                (porta[1], numero),
            ).fetchone():
                numero = f"{base} ({sufixo})"
                sufixo += 1
            cur = conn.execute(
                "INSERT INTO portas (projeto_id, numero) VALUES (?, ?)",
                (porta[1], numero),
            )
            conn.execute(
                "UPDATE regras SET porta_id = ? WHERE id = ?",
                (cur.lastrowid, regra[0]),
            )

    # Portas vazias eventualmente criadas antes desta mudança recebem o
    # registro interno necessário para abrir o editor e manter versões.
    portas_vazias = conn.execute("""
        SELECT po.id, po.projeto_id
          FROM portas po
         WHERE NOT EXISTS (SELECT 1 FROM regras r WHERE r.porta_id = po.id)
    """).fetchall()
    for porta in portas_vazias:
        cur = conn.execute(
            "INSERT INTO regras (projeto_id, porta_id, numero) VALUES (?, ?, ?)",
            (porta[1], porta[0], f"porta-{porta[0]}"),
        )
        conn.execute("""
            INSERT INTO versoes (regra_id, numero, conteudo, notas, atual, tipo)
            VALUES (?, 1, '', '', 1, 'Criação')
        """, (cur.lastrowid,))

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_regra_unica_por_porta
            ON regras(porta_id) WHERE porta_id IS NOT NULL
    """)


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

            CREATE TABLE IF NOT EXISTS portas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                projeto_id  INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
                numero      TEXT NOT NULL,
                criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(projeto_id, numero)
            );

            CREATE TABLE IF NOT EXISTS regras (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                projeto_id  INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
                porta_id    INTEGER REFERENCES portas(id) ON DELETE CASCADE,
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
