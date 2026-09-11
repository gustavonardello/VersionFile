"""Regressões com bancos e arquivos temporários; sem rede ou dados reais.

Executar: py -3.11 -m unittest discover -s tests -v
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sqlite3
from contextlib import closing
import tempfile
import unittest
import ast
import hashlib
import json
from pathlib import Path
from unittest.mock import patch, Mock

from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

import database.db as DB
import database.models as M
from core.importer import (
    ItemCliente, ItemProjeto, ArquivoRegra, importar_para_banco, escanear_pasta,
)
from core.exporter import sanitizar_nome, exportar_arquivo
from core import migration
from core.version_manager import nova_versao_de_arquivo
from core.text_utils import normalizar_busca
from ui.diff_viewer import _calcular_diff, _linhas_diff
import core.highlighter as highlighter
import core.updater as updater
from ui.dialogs import DialogCliente
from ui.editor_panel import EditorPanel
from ui.tree_panel import TreePanel
from ui.export_dialog import ExportDialog
from ui.import_dialog import _WorkerImport, ImportDialog
from ui.main_window import MainWindow


APP = QApplication.instance() or QApplication([])


class BancoTemporario(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.caminho = self.raiz / "versionfile.db"
        self.patch_db = patch.object(DB, "DB_PATH", self.caminho)
        self.patch_db.start()
        self.addCleanup(self.patch_db.stop)
        DB.initialize_db()
        self.conn = DB.get_connection()
        self.addCleanup(self.conn.close)

    def hierarquia(self):
        c = M.criar_cliente(self.conn, "Cliente")
        p = M.criar_projeto(self.conn, c.id, "Projeto", "Projeto", "Descrição")
        r = M.criar_regra(self.conn, p.id, "800")
        v = M.criar_versao(self.conn, r.id, "original")
        return c, p, r, v

    def test_cliente_persistido_e_normalizado(self):
        cliente = M.criar_cliente(self.conn, "  João  ")
        with closing(sqlite3.connect(self.caminho)) as outra:
            self.assertEqual(outra.execute("SELECT nome FROM clientes").fetchone()[0], "João")
        self.assertIsNotNone(cliente.id)

    def test_duplicidade_nao_deixa_transacao_aberta(self):
        M.criar_cliente(self.conn, "Cliente")
        with self.assertRaises(sqlite3.IntegrityError):
            M.criar_cliente(self.conn, "Cliente")
        self.assertFalse(self.conn.in_transaction)
        M.criar_cliente(self.conn, "Outro")
        self.assertEqual(len(M.listar_clientes(self.conn)), 2)

    def test_nome_vazio_rejeitado(self):
        with self.assertRaises(ValueError):
            M.criar_cliente(self.conn, "   ")
        self.assertEqual(M.listar_clientes(self.conn), [])

    def test_renomear_duplicado_preserva_nome(self):
        c = M.criar_cliente(self.conn, "Primeiro")
        M.criar_cliente(self.conn, "Segundo")
        with self.assertRaises(sqlite3.IntegrityError):
            M.renomear_cliente(self.conn, c.id, "Segundo")
        self.assertEqual(M.listar_clientes(self.conn)[0].nome, "Primeiro")
        self.assertFalse(self.conn.in_transaction)

    def test_operacao_composta_faz_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with M.transacao(self.conn):
                M.criar_cliente(self.conn, "Cliente")
                M.criar_cliente(self.conn, "Cliente")
        self.assertEqual(M.listar_clientes(self.conn), [])

    def test_falha_nova_versao_preserva_atual(self):
        _, _, r, v = self.hierarquia()
        self.conn.execute("""CREATE TRIGGER falhar BEFORE INSERT ON versoes
            BEGIN SELECT RAISE(ABORT, 'falha simulada'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            M.criar_versao(self.conn, r.id, "novo")
        self.assertTrue(M.listar_versoes(self.conn, r.id)[0].atual)
        self.assertFalse(self.conn.in_transaction)

    def test_nao_marcar_versao_de_outra_regra(self):
        _, p, r, v = self.hierarquia()
        outra = M.criar_regra(self.conn, p.id, "801")
        outro_v = M.criar_versao(self.conn, outra.id)
        with self.assertRaises(ValueError):
            M.definir_versao_atual(self.conn, r.id, outro_v.id)
        self.assertTrue(M.listar_versoes(self.conn, r.id)[0].atual)

    def test_excluir_versao_promove_restante(self):
        _, _, r, v = self.hierarquia()
        novo = M.criar_versao(self.conn, r.id)
        M.deletar_versao(self.conn, novo.id)
        self.assertTrue(M.listar_versoes(self.conn, r.id)[0].atual)
        with self.assertRaises(ValueError):
            M.deletar_versao(self.conn, v.id)

    def test_excluir_cliente_cascata(self):
        c, _, _, _ = self.hierarquia()
        M.deletar_cliente(self.conn, c.id)
        for tabela in ("clientes", "projetos", "regras", "versoes"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0], 0)

    def test_importacao_falha_nao_deixa_regras_vazias(self):
        arquivo = self.raiz / "800.lsp"
        arquivo.write_text("conteúdo", encoding="utf-8")
        clientes = [ItemCliente("Importado", [ItemProjeto("P", "Projeto", [
            ArquivoRegra(arquivo, "800"), ArquivoRegra(self.raiz / "ausente.lsp", "801")
        ])])]
        with self.assertRaises(FileNotFoundError):
            importar_para_banco(self.conn, clientes)
        self.assertEqual(M.listar_clientes(self.conn), [])

    def test_importacao_thread_e_repeticao(self):
        arquivo = self.raiz / "800.lsp"
        arquivo.write_text("conteúdo", encoding="utf-8")
        clientes = [ItemCliente("Importado", [ItemProjeto("P", "Projeto", [ArquivoRegra(arquivo, "800")])])]
        worker = _WorkerImport(str(self.caminho), clientes, "Notas")
        resultados, erros = [], []
        worker.concluido.connect(resultados.append)
        worker.erro.connect(erros.append)
        worker.start()
        self.assertTrue(worker.wait(5000))
        APP.processEvents()
        self.assertEqual(erros, [])
        self.assertEqual(resultados[0]["regras"], 1)
        self.assertEqual(importar_para_banco(self.conn, clientes)["pulados"], 1)

    def test_importacao_estrutura_mista(self):
        (self.raiz / "solta.lsp").write_text("raiz", encoding="utf-8")
        projeto = self.raiz / "Projeto direto"
        projeto.mkdir()
        (projeto / "direta.lsp").write_text("direta", encoding="utf-8")
        projeto_cliente = self.raiz / "Cliente A" / "DID 10"
        projeto_cliente.mkdir(parents=True)
        (projeto_cliente / "profunda.lsp").write_text("profunda", encoding="utf-8")
        encontrados = escanear_pasta(self.raiz)
        mapa = {
            (cliente.nome, projeto.nome): [a.numero for a in projeto.regras]
            for cliente in encontrados for projeto in cliente.projetos
        }
        self.assertEqual(mapa[(self.raiz.name, self.raiz.name)], ["solta"])
        self.assertEqual(mapa[(self.raiz.name, "Projeto direto")], ["direta"])
        self.assertEqual(mapa[("Cliente A", "DID 10")], ["profunda"])

    def test_arquivo_latin1_sem_corrupcao(self):
        _, _, r, _ = self.hierarquia()
        arquivo = self.raiz / "latin1.lsp"
        arquivo.write_bytes("ação".encode("latin-1"))
        v = nova_versao_de_arquivo(self.conn, r.id, str(arquivo))
        self.assertEqual(v.conteudo, "ação")

    def test_migracao_preserva_descricao_e_dependentes(self):
        c, p, r, v = self.hierarquia()
        self.conn.execute("PRAGMA foreign_keys = OFF")
        self.conn.execute("""CREATE TABLE projetos_antigos (
            id INTEGER PRIMARY KEY, cliente_id INTEGER REFERENCES clientes(id), nome TEXT,
            tipo TEXT CHECK(tipo IN ('DID', 'Projeto')), descricao TEXT, criado_em TEXT)""")
        self.conn.execute("INSERT INTO projetos_antigos SELECT * FROM projetos")
        self.conn.execute("DROP TABLE projetos")
        self.conn.execute("ALTER TABLE projetos_antigos RENAME TO projetos")
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys = ON")
        DB._migrar(self.conn)
        self.assertEqual(M.listar_projetos(self.conn, c.id)[0].descricao, "Descrição")
        self.assertEqual(M.listar_versoes(self.conn, r.id)[0].conteudo, "original")
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertFalse(DB._precisa_migrar(self.conn))
        M.criar_projeto(self.conn, c.id, "Relatório", "Relatório")

    def test_migracao_rollback_e_restaura_foreign_keys(self):
        self.hierarquia()
        schema = self.conn.execute("SELECT sql FROM sqlite_master WHERE name='projetos'").fetchone()[0]
        with patch.object(DB, "_precisa_migrar", return_value=True):
            def falhar(conn):
                conn.execute("DROP TABLE projetos")
                raise RuntimeError("falha simulada")
            with patch.object(DB, "_migrar_tabelas", side_effect=falhar):
                with self.assertRaises(RuntimeError):
                    DB._migrar(self.conn)
        self.assertEqual(self.conn.execute("SELECT sql FROM sqlite_master WHERE name='projetos'").fetchone()[0], schema)
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_snapshot_inclui_wal_e_nao_sobrescreve(self):
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.hierarquia()
        destino = self.raiz / "novo"
        with patch.object(migration, "data_path", return_value=destino):
            self.assertIn("versionfile.db", migration.importar_de(self.caminho))
            M.criar_cliente(self.conn, "Depois")
            self.assertNotIn("versionfile.db", migration.importar_de(self.caminho))
        with closing(sqlite3.connect(destino / "versionfile.db")) as copia:
            self.assertEqual(copia.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 1)
            self.assertEqual(copia.execute("SELECT conteudo FROM versoes").fetchone()[0], "original")

    def painel_editor(self):
        with patch.object(EditorPanel, "_carregar_prefs", return_value={}):
            painel = EditorPanel(self.conn)
        self.addCleanup(painel.deleteLater)
        return painel

    def painel_arvore(self):
        p = patch("ui.tree_panel._TREE_STATE_PATH", self.raiz / "tree_state.json")
        p.start()
        self.addCleanup(p.stop)
        painel = TreePanel(self.conn)
        self.addCleanup(painel.deleteLater)
        return painel

    def test_autosave_mantem_versao_antiga_e_undo(self):
        _, _, r, antiga = self.hierarquia()
        atual = M.criar_versao(self.conn, r.id, "atual")
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.combo_versoes.setCurrentIndex(1)
        painel.editor.setCursorPosition(0, len("original"))
        QTest.keyClicks(painel.editor, " editado")
        painel._salvar_tudo()
        self.assertEqual(painel._versao_atual.id, antiga.id)
        self.assertEqual(painel.editor.text(), "original editado")
        self.assertTrue(painel.editor.isUndoAvailable())
        self.assertEqual(M.listar_versoes(self.conn, r.id)[0].conteudo, "atual")

    def test_trocar_versao_salva_pendencia(self):
        _, _, r, antiga = self.hierarquia()
        M.criar_versao(self.conn, r.id, "atual")
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.editor.append(" editado")
        painel.combo_versoes.setCurrentIndex(1)
        self.assertEqual(painel.editor.text(), "original")
        self.assertEqual(M.listar_versoes(self.conn, r.id)[0].conteudo, "atual editado")

    def test_falha_autosave_preserva_edicao_e_permite_tentar_novamente(self):
        _, _, r, v = self.hierarquia()
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.editor.append(" pendente")
        with patch.object(M, "salvar_conteudo_versao", side_effect=sqlite3.OperationalError("database is locked")), patch.object(QMessageBox, "warning") as aviso:
            self.assertFalse(painel.salvar_se_pendente())
            painel.desabilitar_acoes()
        self.assertEqual(painel.editor.text(), "original pendente")
        self.assertEqual(painel._versao_atual.id, v.id)
        self.assertTrue(painel.salvar_se_pendente())
        self.assertEqual(M.listar_versoes(self.conn, r.id)[0].conteudo, "original pendente")

    def test_falha_salvamento_impede_troca_de_versao(self):
        _, _, r, v = self.hierarquia()
        atual = M.criar_versao(self.conn, r.id, "atual")
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.editor.append(" pendente")
        with patch.object(M, "salvar_conteudo_versao", side_effect=sqlite3.OperationalError("locked")), patch.object(QMessageBox, "warning"):
            painel.combo_versoes.setCurrentIndex(1)
        self.assertEqual(painel.combo_versoes.currentIndex(), 0)
        self.assertEqual(painel._versao_atual.id, atual.id)
        self.assertEqual(painel.editor.text(), "atual pendente")

    def test_falha_salvamento_impede_fechamento(self):
        janela = Mock()
        janela.editor_panel.salvar_se_pendente.return_value = False
        evento = Mock()
        MainWindow.closeEvent(janela, evento)
        evento.ignore.assert_called_once()

    def test_thread_ativa_adia_fechamento(self):
        janela = Mock()
        janela.editor_panel.salvar_se_pendente.return_value = True
        janela._worker_update.isRunning.return_value = True
        evento = Mock()
        with patch("ui.main_window.QTimer.singleShot") as agendar:
            MainWindow.closeEvent(janela, evento)
        evento.ignore.assert_called_once()
        agendar.assert_called_once()

    def test_desmarcar_salva_pendencia(self):
        _, _, r, _ = self.hierarquia()
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.editor.append(" editado")
        painel.desabilitar_acoes()
        self.assertEqual(M.listar_versoes(self.conn, r.id)[0].conteudo, "original editado")
        self.assertFalse(painel._autosave_timer.isActive())

    def test_regra_sem_versoes_limpa_editor(self):
        _, p, r, _ = self.hierarquia()
        vazia = M.criar_regra(self.conn, p.id, "801")
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        painel.abrir_regra(vazia.id)
        self.assertIsNone(painel._versao_atual)
        self.assertEqual(painel.editor.text(), "")

    def test_historico_carrega_id_apos_exclusao(self):
        _, _, r, antiga = self.hierarquia()
        meio = M.criar_versao(self.conn, r.id, "meio")
        M.criar_versao(self.conn, r.id, "atual")
        painel = self.painel_editor()
        painel.abrir_regra(r.id)
        M.deletar_versao(self.conn, meio.id)
        painel._carregar_versao_por_id(antiga.id)
        self.assertEqual(painel._versao_atual.id, antiga.id)
        self.assertEqual(painel.editor.text(), "original")

    def test_cliente_duplicado_na_ui_permite_corrigir(self):
        M.criar_cliente(self.conn, "Cliente")
        painel = self.painel_arvore()
        dlg = Mock()
        nomes = iter(["Cliente", "Outro"])
        def aceitar():
            dlg.nome = next(nomes)
            return 1
        dlg.exec.side_effect = aceitar
        with patch("ui.tree_panel.DialogCliente", return_value=dlg), patch.object(QMessageBox, "warning") as aviso:
            painel._novo_cliente()
        self.assertIn("Já existe um cliente", aviso.call_args.args[2])
        self.assertEqual([c.nome for c in M.listar_clientes(self.conn)], ["Cliente", "Outro"])

    def test_arvore_preserva_selecao_e_limpa_apos_excluir(self):
        c, p, r, _ = self.hierarquia()
        painel = self.painel_arvore()
        painel._selecionar_regra(r.id)
        painel.carregar()
        self.assertEqual(painel._dados(painel.tree.currentItem())["id"], r.id)
        sinal = Mock()
        painel.regra_desmarcada.connect(sinal)
        M.deletar_cliente(self.conn, c.id)
        painel.carregar()
        sinal.assert_called_once()

    def test_arvore_restaura_sinais_apos_erro(self):
        painel = self.painel_arvore()
        with patch.object(M, "listar_clientes", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                painel.carregar()
        self.assertFalse(painel.tree.signalsBlocked())

    def test_busca_literal_unicode_em_conteudo(self):
        _, _, r, _ = self.hierarquia()
        M.salvar_conteudo_versao(self.conn, M.listar_versoes(self.conn, r.id)[0].id, "Ação com 100% e campo_x")
        painel = self.painel_arvore()
        painel.check_conteudo.setChecked(True)
        for termo in ("acao", "%", "campo_"):
            painel.campo_busca.setText(termo)
            painel._aplicar_filtro()
            regra = painel.tree.topLevelItem(0).child(0).child(0)
            self.assertFalse(regra.isHidden(), termo)

    def test_exportacao_selecao_parcial(self):
        _, p, _, _ = self.hierarquia()
        M.criar_regra(self.conn, p.id, "801")
        dlg = ExportDialog(self.conn)
        self.addCleanup(dlg.deleteLater)
        cliente = dlg.tree.topLevelItem(0)
        cliente.child(0).child(0).setCheckState(0, Qt.CheckState.Checked)
        self.assertEqual(cliente.checkState(0), Qt.CheckState.PartiallyChecked)

    def test_importacao_falha_scan_limpa_anterior(self):
        dlg = ImportDialog(self.conn)
        self.addCleanup(dlg.deleteLater)
        dlg._clientes_escaneados = [ItemCliente("Antigo")]
        dlg.btn_importar.setEnabled(True)
        with patch("ui.import_dialog.escanear_pasta", side_effect=OSError("falha")), patch.object(QMessageBox, "critical"):
            dlg._escanear()
        self.assertEqual(dlg._clientes_escaneados, [])
        self.assertFalse(dlg.btn_importar.isEnabled())

    def test_janela_principal_inicia(self):
        with patch.object(MainWindow, "_iniciar_checagem_atualizacao"), patch.object(EditorPanel, "_carregar_prefs", return_value={}), patch("ui.tree_panel._TREE_STATE_PATH", self.raiz / "tree_state.json"):
            janela = MainWindow(self.conn)
        janela.show()
        APP.processEvents()
        self.assertTrue(janela.isVisible())
        janela.close()
        janela.deleteLater()

    def test_menu_expoe_importacao_e_cores(self):
        with patch.object(MainWindow, "_iniciar_checagem_atualizacao"), patch.object(EditorPanel, "_carregar_prefs", return_value={}), patch("ui.tree_panel._TREE_STATE_PATH", self.raiz / "tree_state.json"):
            janela = MainWindow(self.conn)
        self.addCleanup(janela.deleteLater)
        textos = [
            item.text()
            for acao_menu in janela.menuBar().actions()
            if acao_menu.menu() is not None
            for item in acao_menu.menu().actions()
        ]
        self.assertIn("Importar estrutura de pastas...", textos)
        self.assertIn("Personalizar cores do editor...", textos)


class ArquivosEDialogos(unittest.TestCase):
    def test_sintaxe_todos_modulos(self):
        raiz = Path(__file__).resolve().parents[1]
        arquivos = [raiz / "main.py"]
        for pasta in ("core", "database", "ui", "scripts", "tests"):
            arquivos.extend((raiz / pasta).rglob("*.py"))
        for arquivo in arquivos:
            with self.subTest(arquivo=arquivo.relative_to(raiz)):
                ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))

    def test_cliente_vazio_desabilita_ok(self):
        dlg = DialogCliente()
        try:
            self.assertFalse(dlg._botao_ok.isEnabled())
            dlg.campo_nome.setText("   ")
            self.assertFalse(dlg._botao_ok.isEnabled())
            dlg.campo_nome.setText("Novo")
            self.assertTrue(dlg._botao_ok.isEnabled())
        finally:
            dlg.deleteLater()

    def test_nomes_windows(self):
        for nome in ("..", "", "CON", "LPT1.txt", "Titulo / Antes de Imprimir", "A\\B", "X:\\Y"):
            with self.subTest(nome=nome):
                resultado = sanitizar_nome(nome)
                self.assertNotIn("/", resultado)
                self.assertNotIn("\\", resultado)
                self.assertNotIn(":", resultado)
                self.assertNotIn(resultado, ("", ".", "..", "CON", "LPT1.txt"))

    def test_exportacao_colisao_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as temp:
            # O runner do GitHub pode devolver o diretório temporário com o
            # alias 8.3 do Windows; o exportador retorna o caminho canônico.
            raiz = Path(temp).resolve()
            a = exportar_arquivo(raiz, ["..", "X:/Y"], "Titulo / Antes.lsp", "primeiro")
            b = exportar_arquivo(raiz, ["..", "X:/Y"], "Titulo / Antes.lsp", "segundo")
            self.assertTrue(a.is_relative_to(raiz))
            self.assertNotEqual(a, b)
            self.assertEqual(a.read_text(encoding="utf-8"), "primeiro")
            self.assertEqual(b.read_text(encoding="utf-8"), "segundo")

    def test_normalizacao_busca(self):
        self.assertEqual(normalizar_busca("AÇÃO"), "acao")

    def test_diff_excedentes_e_quebra_final(self):
        esq, direita = _calcular_diff(["a", "b", "c"], ["x"])
        self.assertEqual([s for _, s in esq], ["mudado", "removido", "removido"])
        self.assertEqual([s for _, s in direita], ["mudado", "vazio", "vazio"])
        self.assertNotEqual(_linhas_diff("linha"), _linhas_diff("linha\n"))

    def test_tema_invalido_usa_fallback_e_preserva_backup_ao_salvar(self):
        with tempfile.TemporaryDirectory() as temp:
            caminho = Path(temp) / "themes.json"
            caminho.write_text("{inválido", encoding="utf-8")
            with patch.object(highlighter, "THEMES_PATH", caminho):
                tema = highlighter.load_theme()
                self.assertEqual(tema["background"], "#1E1E1E")
                highlighter.salvar_cores_tema({"keyword": "#123456"})
            self.assertEqual(json.loads(caminho.read_text(encoding="utf-8"))["themes"]["Escuro"]["keyword"], "#123456")
            self.assertEqual(len(list(Path(temp).glob("themes.invalid-*.json"))), 1)

    def test_preferencias_com_tipo_invalido_usam_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config"
            config.mkdir()
            (config / "ui_prefs.json").write_text("[]", encoding="utf-8")
            with patch("ui.editor_panel.data_path", return_value=Path(temp)):
                self.assertEqual(EditorPanel._carregar_prefs(Mock()), {})

    def test_atualizador_exige_checksum_na_release(self):
        dados = {
            "tag_name": "v9.0.0", "html_url": "https://github.com/exemplo/release",
            "assets": [{"name": "VersionFile-9.0.0-Setup.exe", "browser_download_url": "https://github.com/a.exe", "size": 3}],
        }
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = json.dumps(dados).encode()
        with patch.object(updater, "__version__", "1.0.0"), patch("core.updater.urllib.request.urlopen", return_value=resposta):
            self.assertIsNone(updater.verificar_atualizacao(forcar=True))

    def test_download_valida_sha256_e_usa_pasta_exclusiva(self):
        conteudo = b"exe"
        digest = hashlib.sha256(conteudo).hexdigest()
        checksum = Mock()
        checksum.__enter__ = Mock(return_value=checksum)
        checksum.__exit__ = Mock(return_value=False)
        checksum.read.return_value = f"{digest}  setup.exe".encode()
        instalador = Mock()
        instalador.read.side_effect = [conteudo, b""]
        instalador.close = Mock()
        info = updater.InfoAtualizacao(
            "2.0.0", "https://github.com/r", "https://github.com/r/setup.exe",
            "https://github.com/r/setup.exe.sha256", len(conteudo), "",
        )
        with patch("core.updater.urllib.request.urlopen", side_effect=[checksum, instalador]), patch("core.updater.subprocess.Popen") as popen:
            updater.baixar_e_instalar(info)
        caminho = Path(popen.call_args.args[0][0])
        self.assertTrue(caminho.parent.name.startswith("versionfile-update-"))

    def test_download_rejeita_origem_e_hash_incorreto(self):
        info = updater.InfoAtualizacao(
            "2.0.0", "https://github.com/r", "http://exemplo.com/setup.exe",
            "https://github.com/r/setup.exe.sha256", 3, "",
        )
        with self.assertRaises(updater.ErroAtualizacao):
            updater.baixar_e_instalar(info)

        checksum = Mock()
        checksum.__enter__ = Mock(return_value=checksum)
        checksum.__exit__ = Mock(return_value=False)
        checksum.read.return_value = ("0" * 64).encode()
        instalador = Mock()
        instalador.read.side_effect = [b"exe", b""]
        instalador.close = Mock()
        info.url_download = "https://github.com/r/setup.exe"
        with patch("core.updater.urllib.request.urlopen", side_effect=[checksum, instalador]), patch("core.updater.subprocess.Popen") as popen:
            with self.assertRaises(updater.ErroAtualizacao):
                updater.baixar_e_instalar(info)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
