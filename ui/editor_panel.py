import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QSplitter,
    QMessageBox, QFileDialog, QFrame, QStackedWidget,
)
from PyQt6.QtCore import Qt, QTimer, QObject, QEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.Qsci import QsciScintilla
from PyQt6.QtGui import QColor, QFont

import database.models as M
from core.highlighter import LSPLexer, load_theme, list_themes, save_active_theme
from core.version_manager import diff_versoes, sugerir_tipo_para_regra
from ui.dialogs import DialogVersao
from ui.diff_viewer import DiffViewer
from ui.version_history import VersionHistory

STATUS_CORES = {
    "Em desenvolvimento": "#569CD6",
    "Em teste":           "#DCDCAA",
    "Produção":           "#4EC9B0",
    "Depreciada":         "#808080",
}


def _badge(status: str) -> str:
    return f'<span style="color:{STATUS_CORES.get(status, "#fff")}">{status}</span>'


class EditorPanel(QWidget):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._regra_id = None
        self._versao_atual = None
        self._lexer = None
        self._carregando = False

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1000)
        self._autosave_timer.timeout.connect(self._salvar_tudo)

        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 0, 4)

        # Barra superior
        barra = QHBoxLayout()
        self.label_regra = QLabel("Nenhuma regra selecionada")
        self.label_regra.setStyleSheet("font-weight: bold; font-size: 13px;")
        barra.addWidget(self.label_regra)
        barra.addStretch()

        barra.addWidget(QLabel("Tema:"))
        self.combo_tema = QComboBox()
        self.combo_tema.addItems(list_themes())
        # Seleciona o tema persistido sem disparar o sinal
        from core.paths import data_path
        _themes_json = data_path() / "config" / "themes.json"
        _tema_ativo = json.loads(_themes_json.read_text(encoding="utf-8"))["active_theme"]
        _idx = self.combo_tema.findText(_tema_ativo)
        if _idx >= 0:
            self.combo_tema.setCurrentIndex(_idx)
        self.combo_tema.currentTextChanged.connect(self._trocar_tema)
        barra.addWidget(self.combo_tema)
        layout.addLayout(barra)

        # Splitter: editor | painel versões
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Editor (dentro de um stack para alternar com tela vazia)
        self.editor = QsciScintilla()
        self._setup_editor()
        self.editor.textChanged.connect(self._agendar_autosave)

        self._tela_vazia = QWidget()
        self._tela_vazia.setStyleSheet("background-color: #1E1E1E;")
        lbl_vazio = QLabel("Selecione uma regra para editar")
        lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_vazio.setStyleSheet("color: #3C3C3C; font-size: 14px;")
        lay_vazio = QVBoxLayout(self._tela_vazia)
        lay_vazio.addWidget(lbl_vazio)

        self._stack_editor = QStackedWidget()
        self._stack_editor.addWidget(self._tela_vazia)  # índice 0 — sem regra
        self._stack_editor.addWidget(self.editor)        # índice 1 — com regra
        self._stack_editor.setCurrentIndex(0)
        splitter.addWidget(self._stack_editor)

        # Painel direito (versões + notas)
        painel_versoes = QWidget()
        painel_versoes.setObjectName("painelVersoes")
        pv_layout = QVBoxLayout(painel_versoes)
        pv_layout.setContentsMargins(8, 8, 0, 8)
        pv_layout.setSpacing(6)

        # --- Seção: Versão ---
        lbl_sec_versao = QLabel("VERSÃO")
        lbl_sec_versao.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_versao)

        self.combo_versoes = QComboBox()
        self.combo_versoes.currentIndexChanged.connect(self._carregar_versao)
        self.combo_versoes.setEnabled(False)
        pv_layout.addWidget(self.combo_versoes)

        self.label_status = QLabel("")
        self.label_status.setTextFormat(Qt.TextFormat.RichText)
        self.label_status.setObjectName("labelStatus")
        pv_layout.addWidget(self.label_status)

        pv_layout.addSpacing(2)

        # --- Seção: Status ---
        lbl_sec_status = QLabel("STATUS")
        lbl_sec_status.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_status)

        self.combo_status = QComboBox()
        self.combo_status.addItems(list(STATUS_CORES.keys()))
        self.combo_status.currentTextChanged.connect(self._agendar_autosave)
        self.combo_status.setEnabled(False)
        pv_layout.addWidget(self.combo_status)

        pv_layout.addSpacing(2)

        # --- Seção: Notas ---
        lbl_sec_notas = QLabel("NOTAS")
        lbl_sec_notas.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_notas)

        self.campo_notas = QTextEdit()
        self.campo_notas.setMaximumHeight(90)
        self.campo_notas.setPlaceholderText("Descreva as alterações desta versão...")
        self.campo_notas.textChanged.connect(self._agendar_autosave)
        self.campo_notas.setEnabled(False)
        pv_layout.addWidget(self.campo_notas)

        btn_salvar_tudo = QPushButton("Salvar  Ctrl+S")
        btn_salvar_tudo.setShortcut("Ctrl+S")
        btn_salvar_tudo.setObjectName("btnPrimario")
        btn_salvar_tudo.clicked.connect(self._salvar_tudo)
        pv_layout.addWidget(btn_salvar_tudo)

        pv_layout.addSpacing(4)

        # --- Separador ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3A3A3A;")
        pv_layout.addWidget(sep)

        pv_layout.addSpacing(2)

        # --- Seção: Ações ---
        lbl_sec_acoes = QLabel("AÇÕES")
        lbl_sec_acoes.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_acoes)

        self.btn_nova_versao = QPushButton("+ Nova versão")
        self.btn_nova_versao.clicked.connect(self._nova_versao)
        self.btn_nova_versao.setEnabled(False)
        pv_layout.addWidget(self.btn_nova_versao)

        self.btn_marcar_atual = QPushButton("Marcar como atual")
        self.btn_marcar_atual.clicked.connect(self._marcar_atual)
        self.btn_marcar_atual.setEnabled(False)
        pv_layout.addWidget(self.btn_marcar_atual)

        self.btn_exportar = QPushButton("Exportar .lsp")
        self.btn_exportar.clicked.connect(self._exportar)
        self.btn_exportar.setEnabled(False)
        pv_layout.addWidget(self.btn_exportar)

        self.btn_historico = QPushButton("Ver histórico")
        self.btn_historico.setToolTip("Visualiza todas as versões com opção de carregar ou excluir")
        self.btn_historico.clicked.connect(self._abrir_historico)
        self.btn_historico.setEnabled(False)
        pv_layout.addWidget(self.btn_historico)

        self.btn_diff = QPushButton("Comparar versões")
        self.btn_diff.setToolTip("Abre o diff visual lado a lado entre duas versões")
        self.btn_diff.clicked.connect(self._abrir_diff)
        self.btn_diff.setEnabled(False)
        pv_layout.addWidget(self.btn_diff)

        pv_layout.addSpacing(4)

        btn_excluir_versao = QPushButton("Excluir versão")
        btn_excluir_versao.setObjectName("btnPerigo")
        btn_excluir_versao.clicked.connect(self._excluir_versao)
        pv_layout.addWidget(btn_excluir_versao)

        pv_layout.addStretch()
        painel_versoes.setFixedWidth(210)

        painel_versoes.setStyleSheet("""
            QWidget#painelVersoes {
                background-color: #252526;
                border-left: 1px solid #3A3A3A;
            }
            QLabel#secLabel {
                color: #858585;
                font-size: 10px;
                font-weight: bold;
                font-family: Segoe UI;
                letter-spacing: 1px;
                margin-top: 2px;
            }
            QLabel#labelStatus {
                font-size: 12px;
                padding: 2px 0;
            }
            QComboBox {
                background-color: #3C3C3C;
                border: 1px solid #4A4A4A;
                color: #D4D4D4;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }
            QComboBox:hover { border-color: #6A6A6A; }
            QComboBox:disabled { color: #555555; border-color: #3A3A3A; }
            QComboBox::drop-down { border: none; width: 20px; }
            QTextEdit:disabled { color: #555555; border-color: #3A3A3A; }
            QTextEdit {
                background-color: #3C3C3C;
                border: 1px solid #4A4A4A;
                color: #D4D4D4;
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #4A4A4A;
                padding: 5px 8px;
                border-radius: 4px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover { background-color: #4A4A4A; border-color: #6A6A6A; }
            QPushButton:pressed { background-color: #2A2A2A; }
            QPushButton:disabled { color: #555555; border-color: #3A3A3A; }
            QPushButton#btnPrimario {
                background-color: #0E639C;
                color: white;
                border: none;
                text-align: center;
                font-weight: bold;
            }
            QPushButton#btnPrimario:hover { background-color: #1177BB; }
            QPushButton#btnPerigo {
                background-color: transparent;
                color: #F48771;
                border: 1px solid #5A2A2A;
                text-align: left;
            }
            QPushButton#btnPerigo:hover { background-color: #3A1A1A; border-color: #F48771; }
        """)

        splitter.addWidget(painel_versoes)
        splitter.setStretchFactor(0, 1)

        layout.addWidget(splitter, 1)

        # Barra inferior
        barra_inf = QHBoxLayout()
        self.label_info = QLabel("")
        self.label_info.setStyleSheet("color: #858585; font-size: 11px;")
        barra_inf.addWidget(self.label_info)
        layout.addLayout(barra_inf)

    def _setup_editor(self):
        self._lexer = LSPLexer(self.editor)
        self.editor.setLexer(self._lexer)

        t = self._lexer._theme
        self.editor.setMarginsBackgroundColor(QColor(t["margin_background"]))
        self.editor.setMarginsForegroundColor(QColor(t["margin_foreground"]))
        self.editor.setCaretLineBackgroundColor(QColor(t["caret_line"]))
        self.editor.setCaretLineVisible(True)
        self.editor.setSelectionBackgroundColor(QColor(t["selection"]))

        self.editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.editor.setMarginWidth(0, "0000")

        self.editor.setIndentationsUseTabs(False)
        self.editor.setTabWidth(4)
        self.editor.setAutoIndent(True)
        self.editor.setUtf8(True)

        self.editor.setFont(QFont("Consolas", 10))

        self.editor.setStyleSheet("""
            QScrollBar:vertical {
                background: #252526;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal {
                background: #252526;
                height: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background: #555;
                border-radius: 4px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal { width: 0px; }
        """)

    def _trocar_tema(self, nome: str):
        if self._lexer:
            self._lexer.apply_theme(nome)
            t = self._lexer._theme
            self.editor.setMarginsBackgroundColor(QColor(t["margin_background"]))
            self.editor.setMarginsForegroundColor(QColor(t["margin_foreground"]))
            self.editor.setCaretLineBackgroundColor(QColor(t["caret_line"]))
            self.editor.setSelectionBackgroundColor(QColor(t["selection"]))
            save_active_theme(nome)

    def salvar_se_pendente(self):
        """Salva imediatamente se houver um autosave pendente ou versão aberta."""
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
            self._salvar_tudo()

    def abrir_regra(self, regra_id: int):
        self.salvar_se_pendente()
        self._regra_id = regra_id
        regra = self.conn.execute(
            "SELECT r.numero, r.descricao, p.nome as proj, c.nome as cli "
            "FROM regras r "
            "JOIN projetos p ON p.id = r.projeto_id "
            "JOIN clientes c ON c.id = p.cliente_id "
            "WHERE r.id = ?", (regra_id,)
        ).fetchone()

        if regra:
            desc = f" — {regra['descricao']}" if regra["descricao"] else ""
            self.label_regra.setText(
                f"{regra['cli']} / {regra['proj']} / Regra {regra['numero']}{desc}"
            )

        self._set_acoes_habilitadas(True)
        self._recarregar_versoes()

    def _set_acoes_habilitadas(self, habilitado: bool):
        self._stack_editor.setCurrentIndex(1 if habilitado else 0)
        self.combo_versoes.setEnabled(habilitado)
        self.combo_status.setEnabled(habilitado)
        self.campo_notas.setEnabled(habilitado)
        self.btn_nova_versao.setEnabled(habilitado)
        self.btn_marcar_atual.setEnabled(habilitado)
        self.btn_exportar.setEnabled(habilitado)
        self.btn_historico.setEnabled(habilitado)
        self.btn_diff.setEnabled(habilitado)

    def desabilitar_acoes(self):
        self._regra_id = None
        self._versao_atual = None
        self._set_acoes_habilitadas(False)

    def _recarregar_versoes(self):
        self.combo_versoes.blockSignals(True)
        self.combo_versoes.clear()
        versoes = M.listar_versoes(self.conn, self._regra_id)
        for v in versoes:
            atual = "  [atual]" if v.atual else ""
            self.combo_versoes.addItem(f"{v.numero}  ·  {v.tipo}{atual}", userData=v)
        self.combo_versoes.blockSignals(False)
        if versoes:
            # Seleciona a versão atual por padrão
            idx = next((i for i, v in enumerate(versoes) if v.atual), 0)
            self.combo_versoes.setCurrentIndex(idx)
            self._carregar_versao(idx)

    def _on_focus_changed(self, old, new):
        """Salva imediatamente quando o foco sai do editor ou das notas."""
        saiu_do_editor = old in (self.editor, self.campo_notas, self.combo_status)
        if saiu_do_editor and not self._carregando and self._versao_atual:
            self._autosave_timer.stop()
            self._salvar_tudo()

    def _agendar_autosave(self):
        if not self._carregando and self._versao_atual:
            self._autosave_timer.start()

    def _carregar_versao(self, index: int):
        versao = self.combo_versoes.itemData(index)
        if not versao:
            return
        self._carregando = True
        self._autosave_timer.stop()
        self._versao_atual = versao
        self.editor.setText(versao.conteudo)
        self.combo_status.setCurrentText(versao.status)
        self.campo_notas.setPlainText(versao.notas or "")
        self.label_status.setText(_badge(versao.status))
        self.label_info.setText(f"v{versao.numero}  |  {versao.criado_em}")
        self._carregando = False

    def _salvar_tudo(self):
        if not self._versao_atual:
            return
        M.salvar_conteudo_versao(self.conn, self._versao_atual.id, self.editor.text())
        M.atualizar_versao(
            self.conn,
            self._versao_atual.id,
            self.combo_status.currentText(),
            self.campo_notas.toPlainText(),
        )
        num = self._versao_atual.numero
        self._recarregar_versoes()
        self.label_info.setText(f"v{num}  |  Salvo automaticamente")

    def _nova_versao(self):
        if not self._regra_id:
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        proximo_numero = (versoes[0].numero + 1) if versoes else 1
        # Usa conteúdo atual apenas para sugerir o tipo — o editor começa em branco
        conteudo_ref = self._versao_atual.conteudo if self._versao_atual else ""
        tipo_sugerido = sugerir_tipo_para_regra(self.conn, self._regra_id, conteudo_ref)
        dlg = DialogVersao(self, tipo_sugerido=tipo_sugerido, numero_versao=proximo_numero)
        if dlg.exec():
            M.criar_versao(self.conn, self._regra_id, "", dlg.notas, dlg.tipo)
            self._recarregar_versoes()

    def _marcar_atual(self):
        if not self._versao_atual:
            return
        M.definir_versao_atual(self.conn, self._regra_id, self._versao_atual.id)
        self._recarregar_versoes()

    def _exportar(self):
        if not self._versao_atual:
            return
        regra = self.conn.execute(
            "SELECT numero, descricao FROM regras WHERE id = ?", (self._regra_id,)
        ).fetchone()
        import re
        def _sanitizar(t): return re.sub(r'[\\/:*?"<>|]', "", t).strip()
        numero = regra["numero"] if regra else "regra"
        desc = _sanitizar(regra["descricao"] or "") if regra else ""
        base = f"{numero} - {desc}" if desc else numero
        nome_sugerido = f"{base}_v{self._versao_atual.numero}.lsp"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar", nome_sugerido,
            "LSP (*.lsp);;Texto (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._versao_atual.conteudo)

    def _excluir_versao(self):
        if not self._versao_atual:
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        if len(versoes) <= 1:
            QMessageBox.warning(self, "Excluir versão", "Não é possível excluir a única versão da regra.")
            return
        v = self._versao_atual
        resp = QMessageBox.question(
            self, "Excluir versão",
            f"Excluir v{v.numero} ({v.status})?\nEsta ação não pode ser desfeita.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        era_atual = v.atual
        M.deletar_versao(self.conn, v.id)
        # Se era a atual, promove a versão mais recente restante
        if era_atual:
            restantes = M.listar_versoes(self.conn, self._regra_id)
            if restantes:
                M.definir_versao_atual(self.conn, self._regra_id, restantes[0].id)
        self._recarregar_versoes()

    def _abrir_historico(self):
        if not self._regra_id:
            return
        label = self.label_regra.text()
        dlg = VersionHistory(self.conn, self._regra_id, regra_label=label, parent=self)
        dlg.versao_carregada.connect(self._carregar_versao_por_id)
        dlg.exec()
        # Recarrega combo caso versões tenham sido excluídas no histórico
        self._recarregar_versoes()

    def _carregar_versao_por_id(self, versao_id: int):
        versoes = M.listar_versoes(self.conn, self._regra_id)
        for i, v in enumerate(versoes):
            if v.id == versao_id:
                self.combo_versoes.blockSignals(True)
                self.combo_versoes.setCurrentIndex(i)
                self.combo_versoes.blockSignals(False)
                self._carregar_versao(i)
                break

    def _abrir_diff(self):
        if not self._regra_id:
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        if len(versoes) < 2:
            QMessageBox.information(self, "Diff", "É necessário ao menos 2 versões para comparar.")
            return
        dlg = DiffViewer(self.conn, self._regra_id, parent=self)
        dlg.exec()
