import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QSplitter,
    QMessageBox, QFileDialog, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.Qsci import QsciScintilla
from PyQt6.QtGui import QColor, QFont

import database.models as M
from core.highlighter import LSPLexer, load_theme, list_themes, save_active_theme
from core.version_manager import diff_versoes, sugerir_tipo_para_regra
from ui.dialogs import DialogVersao
from ui.diff_viewer import DiffViewer

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

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

        # Editor
        self.editor = QsciScintilla()
        self._setup_editor()
        splitter.addWidget(self.editor)

        # Painel direito (versões + notas)
        painel_versoes = QWidget()
        painel_versoes.setObjectName("painelVersoes")
        pv_layout = QVBoxLayout(painel_versoes)
        pv_layout.setContentsMargins(8, 8, 8, 8)
        pv_layout.setSpacing(6)

        # --- Seção: Versão ---
        lbl_sec_versao = QLabel("VERSÃO")
        lbl_sec_versao.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_versao)

        self.combo_versoes = QComboBox()
        self.combo_versoes.currentIndexChanged.connect(self._carregar_versao)
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
        pv_layout.addWidget(self.combo_status)

        pv_layout.addSpacing(2)

        # --- Seção: Notas ---
        lbl_sec_notas = QLabel("NOTAS")
        lbl_sec_notas.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_notas)

        self.campo_notas = QTextEdit()
        self.campo_notas.setMaximumHeight(90)
        self.campo_notas.setPlaceholderText("Descreva as alterações desta versão...")
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

        btn_nova_versao = QPushButton("+ Nova versão")
        btn_nova_versao.clicked.connect(self._nova_versao)
        pv_layout.addWidget(btn_nova_versao)

        btn_marcar_atual = QPushButton("Marcar como atual")
        btn_marcar_atual.clicked.connect(self._marcar_atual)
        pv_layout.addWidget(btn_marcar_atual)

        btn_exportar = QPushButton("Exportar .lsp")
        btn_exportar.clicked.connect(self._exportar)
        pv_layout.addWidget(btn_exportar)

        btn_importar = QPushButton("Importar arquivo")
        btn_importar.clicked.connect(self._importar)
        pv_layout.addWidget(btn_importar)

        btn_diff = QPushButton("Comparar versões")
        btn_diff.setToolTip("Abre o diff visual lado a lado entre duas versões")
        btn_diff.clicked.connect(self._abrir_diff)
        pv_layout.addWidget(btn_diff)

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
            QComboBox::drop-down { border: none; width: 20px; }
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

        layout.addWidget(splitter)

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

    def _trocar_tema(self, nome: str):
        if self._lexer:
            self._lexer.apply_theme(nome)
            t = self._lexer._theme
            self.editor.setMarginsBackgroundColor(QColor(t["margin_background"]))
            self.editor.setMarginsForegroundColor(QColor(t["margin_foreground"]))
            self.editor.setCaretLineBackgroundColor(QColor(t["caret_line"]))
            self.editor.setSelectionBackgroundColor(QColor(t["selection"]))
            save_active_theme(nome)

    def abrir_regra(self, regra_id: int):
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

        self._recarregar_versoes()

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

    def _carregar_versao(self, index: int):
        versao = self.combo_versoes.itemData(index)
        if not versao:
            return
        self._versao_atual = versao
        self.editor.setText(versao.conteudo)
        self.combo_status.setCurrentText(versao.status)
        self.campo_notas.setPlainText(versao.notas or "")
        self.label_status.setText(_badge(versao.status))
        self.label_info.setText(f"v{versao.numero}  |  {versao.criado_em}")

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
        self._recarregar_versoes()
        self.label_info.setText(f"v{self._versao_atual.numero}  |  Salvo")

    def _nova_versao(self):
        if not self._regra_id:
            return
        conteudo_atual = self._versao_atual.conteudo if self._versao_atual else ""
        versoes = M.listar_versoes(self.conn, self._regra_id)
        proximo_numero = (versoes[0].numero + 1) if versoes else 1
        tipo_sugerido = sugerir_tipo_para_regra(self.conn, self._regra_id, conteudo_atual)
        dlg = DialogVersao(self, tipo_sugerido=tipo_sugerido, numero_versao=proximo_numero)
        if dlg.exec():
            M.criar_versao(self.conn, self._regra_id, conteudo_atual, dlg.notas, dlg.tipo)
            self._recarregar_versoes()

    def _marcar_atual(self):
        if not self._versao_atual:
            return
        M.definir_versao_atual(self.conn, self._regra_id, self._versao_atual.id)
        self._recarregar_versoes()

    def _exportar(self):
        if not self._versao_atual:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar", f"regra_v{self._versao_atual.numero}.lsp",
            "LSP (*.lsp);;Texto (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._versao_atual.conteudo)

    def _importar(self):
        if not self._regra_id:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar", "", "Texto (*.txt *.lsp);;Todos (*.*)"
        )
        if path:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                conteudo = f.read()
            versoes = M.listar_versoes(self.conn, self._regra_id)
            proximo_numero = (versoes[0].numero + 1) if versoes else 1
            tipo_sugerido = sugerir_tipo_para_regra(self.conn, self._regra_id, conteudo)
            dlg = DialogVersao(self, tipo_sugerido=tipo_sugerido, numero_versao=proximo_numero)
            if dlg.exec():
                M.criar_versao(self.conn, self._regra_id, conteudo, dlg.notas, dlg.tipo)
                self._recarregar_versoes()

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

    def _abrir_diff(self):
        if not self._regra_id:
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        if len(versoes) < 2:
            QMessageBox.information(self, "Diff", "É necessário ao menos 2 versões para comparar.")
            return
        dlg = DiffViewer(self.conn, self._regra_id, parent=self)
        dlg.exec()
