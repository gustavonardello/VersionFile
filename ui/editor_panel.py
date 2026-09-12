import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSplitter,
    QMessageBox, QFileDialog, QFrame, QStackedWidget,
)
from PyQt6.QtCore import Qt, QTimer, QObject, QEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.Qsci import QsciScintilla
from PyQt6.QtGui import QColor, QFont

import database.models as M
from core.highlighter import (
    LSPLexer, load_theme,
    STYLE_DEFAULT, STYLE_KEYWORD, STYLE_FUNCTION, STYLE_TYPE,
    STYLE_NUMBER, STYLE_STRING, STYLE_COMMENT, STYLE_OPERATOR,
    STYLE_IDENTIFIER, STYLE_CONSTANT,
)
from core.version_manager import diff_versoes, sugerir_tipo_para_regra
from core.paths import data_path
from core.exporter import sanitizar_nome
from ui.dialogs import DialogVersao, DialogEditarVersao
from ui.diff_viewer import DiffViewer
from ui.version_history import VersionHistory
from ui.errors import mostrar_erro

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
        self._salvando = False

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1000)
        self._autosave_timer.timeout.connect(self._salvar_tudo)

        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 0, 4)

        self._bg_mode = self._carregar_prefs().get("bg_mode", "black")

        # Barra superior
        barra = QHBoxLayout()
        self.label_regra = QLabel("Nenhuma regra selecionada")
        self.label_regra.setStyleSheet("font-weight: bold; font-size: 13px;")
        barra.addWidget(self.label_regra)
        barra.addStretch()

        self.btn_bg_black = QPushButton()
        self.btn_bg_black.setFixedSize(18, 18)
        self.btn_bg_black.setToolTip("Fundo preto")
        self.btn_bg_black.clicked.connect(lambda: self._set_editor_background("black"))
        barra.addWidget(self.btn_bg_black)

        self.btn_bg_white = QPushButton()
        self.btn_bg_white.setFixedSize(18, 18)
        self.btn_bg_white.setToolTip("Fundo branco")
        self.btn_bg_white.clicked.connect(lambda: self._set_editor_background("white"))
        barra.addWidget(self.btn_bg_white)

        self._atualizar_estilo_botoes_bg()
        layout.addLayout(barra)

        # Splitter: editor | painel versões
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Editor (dentro de um stack para alternar com tela vazia)
        self.editor = QsciScintilla()
        self._setup_editor()
        self.editor.textChanged.connect(self._agendar_autosave)
        # Restaura o fundo salvo — _setup_editor sempre inicializa com tema escuro
        if self._bg_mode != "black":
            modo = self._bg_mode
            self._bg_mode = "black"
            self._set_editor_background(modo)

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

        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        self.btn_versao_ant = QPushButton("‹")
        self.btn_versao_ant.setObjectName("btnNav")
        self.btn_versao_ant.setFixedSize(28, 28)
        self.btn_versao_ant.setToolTip("Versão mais antiga")
        self.btn_versao_ant.clicked.connect(self._versao_anterior)
        self.btn_versao_ant.setEnabled(False)
        nav_row.addWidget(self.btn_versao_ant)

        self.combo_versoes = QComboBox()
        self.combo_versoes.currentIndexChanged.connect(self._carregar_versao)
        self.combo_versoes.setEnabled(False)
        nav_row.addWidget(self.combo_versoes, 1)

        self.btn_versao_prox = QPushButton("›")
        self.btn_versao_prox.setObjectName("btnNav")
        self.btn_versao_prox.setFixedSize(28, 28)
        self.btn_versao_prox.setToolTip("Versão mais recente")
        self.btn_versao_prox.clicked.connect(self._proxima_versao)
        self.btn_versao_prox.setEnabled(False)
        nav_row.addWidget(self.btn_versao_prox)

        pv_layout.addLayout(nav_row)

        self.btn_editar_versao = QPushButton("Editar versão")
        self.btn_editar_versao.clicked.connect(self._editar_versao)
        self.btn_editar_versao.setEnabled(False)
        pv_layout.addWidget(self.btn_editar_versao)

        self.label_versao_info = QLabel("")
        self.label_versao_info.setStyleSheet("font-size: 11px; color: #858585; padding: 0;")
        pv_layout.addWidget(self.label_versao_info)

        self.label_status = QLabel("")
        self.label_status.setTextFormat(Qt.TextFormat.RichText)
        self.label_status.setObjectName("labelStatus")
        pv_layout.addWidget(self.label_status)

        lbl_sec_notas = QLabel("NOTAS")
        lbl_sec_notas.setObjectName("secLabel")
        pv_layout.addWidget(lbl_sec_notas)

        self.label_notas = QLabel("")
        self.label_notas.setWordWrap(True)
        self.label_notas.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label_notas.setObjectName("labelNotas")
        pv_layout.addWidget(self.label_notas)

        self.btn_salvar_tudo = QPushButton("Salvar  Ctrl+S")
        self.btn_salvar_tudo.setShortcut("Ctrl+S")
        self.btn_salvar_tudo.setObjectName("btnPrimario")
        self.btn_salvar_tudo.setEnabled(False)
        self.btn_salvar_tudo.clicked.connect(self._salvar_tudo)
        pv_layout.addWidget(self.btn_salvar_tudo)

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
            QLabel#labelNotas {
                font-size: 11px;
                color: #A0A0A0;
                padding: 4px 6px;
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                font-style: italic;
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
            QPushButton#btnNav {
                text-align: center;
                padding: 0;
                font-size: 16px;
                font-weight: bold;
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

    def _carregar_prefs(self) -> dict:
        try:
            p = data_path() / "config" / "ui_prefs.json"
            if p.exists():
                prefs = json.loads(p.read_text(encoding="utf-8"))
                return prefs if isinstance(prefs, dict) else {}
        except Exception:
            pass
        return {}

    def recarregar_tema(self):
        """Aplica novamente o tema ativo após a personalização de cores."""
        self._lexer._theme = load_theme()
        self._lexer._apply_theme()
        modo = self._bg_mode
        self._bg_mode = "white" if modo == "black" else "black"
        self._set_editor_background(modo)
        self.editor.recolor()

    def _salvar_prefs(self, prefs: dict):
        try:
            p = data_path() / "config" / "ui_prefs.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

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

    def _atualizar_estilo_botoes_bg(self):
        ativo  = "2px solid #CCCCCC"
        inativo = "2px solid #555555"
        borda_black = ativo  if self._bg_mode == "black" else inativo
        borda_white = ativo  if self._bg_mode == "white" else inativo
        self.btn_bg_black.setStyleSheet(f"""
            QPushButton {{
                background-color: #1E1E1E;
                border: {borda_black};
                border-radius: 9px;
                padding: 0;
            }}
            QPushButton:hover {{ border-color: #AAAAAA; }}
        """)
        self.btn_bg_white.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: {borda_white};
                border-radius: 9px;
                padding: 0;
            }}
            QPushButton:hover {{ border-color: #AAAAAA; }}
        """)

    def _set_editor_background(self, mode: str):
        if mode == self._bg_mode:
            return
        self._bg_mode = mode
        self._salvar_prefs({**self._carregar_prefs(), "bg_mode": mode})
        t = self._lexer._theme
        if mode == "white":
            bg         = QColor("#FFFFFF")
            caret_fg   = QColor("#000000")
            caret_line = QColor("#F0F0F0")
            margin_bg  = QColor("#EEEEEE")
            margin_fg  = QColor("#555555")
            fg_map = {
                STYLE_DEFAULT:    "#1E1E1E",  # texto padrão
                STYLE_KEYWORD:    "#0000FF",  # azul forte
                STYLE_FUNCTION:   "#795E26",  # marrom/dourado
                STYLE_TYPE:       "#267F99",  # teal escuro
                STYLE_NUMBER:     "#098658",  # verde escuro
                STYLE_STRING:     "#A31515",  # vermelho escuro
                STYLE_COMMENT:    "#008000",  # verde
                STYLE_OPERATOR:   "#1E1E1E",  # preto
                STYLE_IDENTIFIER: "#1E1E1E",  # preto
                STYLE_CONSTANT:   "#0070C1",  # azul médio
            }
        else:
            bg         = QColor(t["background"])
            caret_fg   = QColor("#FFFFFF")
            caret_line = QColor(t["caret_line"])
            margin_bg  = QColor(t["margin_background"])
            margin_fg  = QColor(t["margin_foreground"])
            fg_map = {
                STYLE_DEFAULT:    t["foreground"],
                STYLE_KEYWORD:    t["keyword"],
                STYLE_FUNCTION:   t["function"],
                STYLE_TYPE:       t["type"],
                STYLE_NUMBER:     t["number"],
                STYLE_STRING:     t["string"],
                STYLE_COMMENT:    t["comment"],
                STYLE_OPERATOR:   t["operator"],
                STYLE_IDENTIFIER: t["identifier"],
                STYLE_CONSTANT:   t["constant"],
            }

        self._lexer.setDefaultPaper(bg)
        self._lexer.setDefaultColor(QColor(fg_map[0]))
        for style, fg in fg_map.items():
            self._lexer.setPaper(bg, style)
            self._lexer.setColor(QColor(fg), style)
        self.editor.setCaretForegroundColor(caret_fg)
        self.editor.setCaretLineBackgroundColor(caret_line)
        self.editor.setMarginsBackgroundColor(margin_bg)
        self.editor.setMarginsForegroundColor(margin_fg)
        self._atualizar_estilo_botoes_bg()

    def salvar_se_pendente(self):
        """Salva imediatamente se houver um autosave pendente ou versão aberta."""
        if self._versao_atual and self.editor.text() != self._versao_atual.conteudo:
            self._autosave_timer.stop()
            return self._salvar_tudo()
        return True

    def abrir_regra(self, regra_id: int):
        if not self.salvar_se_pendente():
            return
        self._regra_id = regra_id
        regra = self.conn.execute(
            "SELECT r.numero, r.descricao, p.nome as proj, p.tipo as proj_tipo, "
            "       po.numero as porta, c.nome as cli "
            "FROM regras r "
            "JOIN projetos p ON p.id = r.projeto_id "
            "JOIN clientes c ON c.id = p.cliente_id "
            "LEFT JOIN portas po ON po.id = r.porta_id "
            "WHERE r.id = ?", (regra_id,)
        ).fetchone()

        if regra:
            desc = f" — {regra['descricao']}" if regra["descricao"] else ""
            if regra["proj_tipo"] == "Webservice" and regra["porta"]:
                self.label_regra.setText(
                    f"{regra['cli']} / {regra['proj']} / Porta {regra['porta']}"
                )
            else:
                self.label_regra.setText(
                    f"{regra['cli']} / {regra['proj']} / Regra {regra['numero']}{desc}"
                )

        self._set_acoes_habilitadas(True)
        self._recarregar_versoes()

    def _set_acoes_habilitadas(self, habilitado: bool):
        self._stack_editor.setCurrentIndex(1 if habilitado else 0)
        self.combo_versoes.setEnabled(habilitado)
        self.btn_versao_ant.setEnabled(False)   # corrigido em _carregar_versao
        self.btn_versao_prox.setEnabled(False)
        self.btn_editar_versao.setEnabled(habilitado)
        self.btn_salvar_tudo.setEnabled(habilitado)
        self.btn_nova_versao.setEnabled(habilitado)
        self.btn_marcar_atual.setEnabled(habilitado)
        self.btn_exportar.setEnabled(habilitado)
        self.btn_historico.setEnabled(habilitado)
        self.btn_diff.setEnabled(habilitado)

    def desabilitar_acoes(self):
        if not self.salvar_se_pendente():
            return
        self._regra_id = None
        self._versao_atual = None
        self._set_acoes_habilitadas(False)

    def _recarregar_versoes(self, versao_id=None):
        if not self.salvar_se_pendente():
            return
        self.combo_versoes.blockSignals(True)
        self.combo_versoes.clear()
        versoes = M.listar_versoes(self.conn, self._regra_id)
        for v in versoes:
            self.combo_versoes.addItem(str(v.numero), userData=v)
            idx = self.combo_versoes.count() - 1
            self.combo_versoes.setItemData(
                idx, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole
            )
        self.combo_versoes.blockSignals(False)
        if versoes:
            # Seleciona a versão atual por padrão
            idx = next((i for i, v in enumerate(versoes) if v.atual), 0)
            if versao_id is not None:
                idx = next((i for i, v in enumerate(versoes) if v.id == versao_id), idx)
            self.combo_versoes.blockSignals(True)
            self.combo_versoes.setCurrentIndex(idx)
            self.combo_versoes.blockSignals(False)
            self._carregar_versao(idx)
        else:
            self._versao_atual = None
            self._carregando = True
            self.editor.clear()
            self._carregando = False
            self.label_status.clear()
            self.label_notas.clear()
            self.label_info.clear()
            self.label_versao_info.clear()

    def _on_focus_changed(self, old, new):
        """Salva imediatamente quando o foco sai do editor."""
        if old is self.editor and not self._carregando and not self._salvando and self._versao_atual:
            self._autosave_timer.stop()
            self._salvar_tudo()

    def _agendar_autosave(self):
        if not self._carregando and self._versao_atual:
            self._autosave_timer.start()

    def _carregar_versao(self, index: int):
        versao = self.combo_versoes.itemData(index)
        if not versao:
            return
        if not self.salvar_se_pendente():
            self.combo_versoes.blockSignals(True)
            for idx in range(self.combo_versoes.count()):
                if self.combo_versoes.itemData(idx).id == self._versao_atual.id:
                    self.combo_versoes.setCurrentIndex(idx)
                    break
            self.combo_versoes.blockSignals(False)
            return
        self._carregando = True
        self._autosave_timer.stop()
        self._versao_atual = versao
        self.editor.setText(versao.conteudo)
        self.label_status.setText(_badge(versao.status))
        self.label_notas.setText(versao.notas or "—")
        self.label_info.setText(f"v{versao.numero}  |  {versao.criado_em}")

        total = self.combo_versoes.count()
        atual_tag = "  (Atual)" if versao.atual else ""
        self.label_versao_info.setText(f"{versao.numero} de {total}  ·  {versao.tipo}{atual_tag}")
        # combo ordena DESC (index 0 = mais recente); ‹ vai para mais antiga (idx+1)
        self.btn_versao_ant.setEnabled(index < total - 1)
        self.btn_versao_prox.setEnabled(index > 0)
        self._carregando = False

    def _editar_versao(self):
        if not self._versao_atual:
            return
        if not self.salvar_se_pendente():
            return
        dlg = DialogEditarVersao(self, versao=self._versao_atual)
        if dlg.exec():
            try:
                M.atualizar_meta_versao(
                    self.conn, self._versao_atual.id, dlg.tipo, dlg.status, dlg.notas,
                )
            except Exception as erro:
                mostrar_erro(self, "Versão não atualizada", erro)
                return
            idx = self.combo_versoes.currentIndex()
            self._recarregar_versoes()
            self.combo_versoes.setCurrentIndex(idx)

    def _versao_anterior(self):
        """Navega para a versão mais antiga (índice maior no combo DESC)."""
        idx = self.combo_versoes.currentIndex()
        if idx < self.combo_versoes.count() - 1:
            self.combo_versoes.setCurrentIndex(idx + 1)

    def _proxima_versao(self):
        """Navega para a versão mais recente (índice menor no combo DESC)."""
        idx = self.combo_versoes.currentIndex()
        if idx > 0:
            self.combo_versoes.setCurrentIndex(idx - 1)

    def _salvar_tudo(self):
        if self._salvando:
            return False
        if not self._versao_atual:
            return True
        self._autosave_timer.stop()
        conteudo = self.editor.text()
        if conteudo == self._versao_atual.conteudo:
            return True
        self._salvando = True
        try:
            M.salvar_conteudo_versao(self.conn, self._versao_atual.id, conteudo)
        except Exception as erro:
            QMessageBox.warning(
                self, "Falha ao salvar",
                f"Não foi possível salvar a versão. O conteúdo permanece no editor.\n\n{erro}",
            )
            return False
        finally:
            self._salvando = False
        self._versao_atual.conteudo = conteudo
        num = self._versao_atual.numero
        for idx in range(self.combo_versoes.count()):
            versao = self.combo_versoes.itemData(idx)
            if versao.id == self._versao_atual.id:
                versao.conteudo = conteudo
                self.combo_versoes.setItemData(idx, versao)
                break
        self.label_info.setText(f"v{num}  |  Salvo automaticamente")
        return True

    def _nova_versao(self):
        if not self._regra_id:
            return
        if not self.salvar_se_pendente():
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        proximo_numero = (versoes[0].numero + 1) if versoes else 1
        # Usa conteúdo atual apenas para sugerir o tipo — o editor começa em branco
        conteudo_ref = self._versao_atual.conteudo if self._versao_atual else ""
        tipo_sugerido = sugerir_tipo_para_regra(self.conn, self._regra_id, conteudo_ref)
        dlg = DialogVersao(self, tipo_sugerido=tipo_sugerido, numero_versao=proximo_numero)
        if dlg.exec():
            try:
                M.criar_versao(self.conn, self._regra_id, "", dlg.notas, dlg.tipo)
            except Exception as erro:
                mostrar_erro(self, "Versão não criada", erro)
                return
            self._recarregar_versoes()

    def _marcar_atual(self):
        if not self._versao_atual:
            return
        if not self.salvar_se_pendente():
            return
        try:
            M.definir_versao_atual(self.conn, self._regra_id, self._versao_atual.id)
        except Exception as erro:
            mostrar_erro(self, "Versão atual não alterada", erro)
            return
        self._recarregar_versoes()

    def _exportar(self):
        if not self._versao_atual:
            return
        regra = self.conn.execute(
            "SELECT numero, descricao FROM regras WHERE id = ?", (self._regra_id,)
        ).fetchone()
        if not self.salvar_se_pendente():
            return
        numero = sanitizar_nome(regra["numero"]) if regra else "regra"
        desc = sanitizar_nome(regra["descricao"]) if regra and regra["descricao"] else ""
        base = f"{numero} - {desc}" if desc else numero
        nome_sugerido = f"{base}_v{self._versao_atual.numero}.lsp"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar", nome_sugerido,
            "LSP (*.lsp);;Texto (*.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._versao_atual.conteudo)
            except OSError as erro:
                mostrar_erro(self, "Regra não exportada", erro)

    def _excluir_versao(self):
        if not self._versao_atual:
            return
        if not self.salvar_se_pendente():
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
        try:
            M.deletar_versao(self.conn, v.id)
        except Exception as erro:
            mostrar_erro(self, "Versão não excluída", erro)
            return
        self._recarregar_versoes()

    def _abrir_historico(self):
        if not self._regra_id:
            return
        if not self.salvar_se_pendente():
            return
        label = self.label_regra.text()
        dlg = VersionHistory(self.conn, self._regra_id, regra_label=label, parent=self)
        dlg.versao_carregada.connect(self._carregar_versao_por_id)
        dlg.exec()
        # Recarrega combo caso versões tenham sido excluídas no histórico
        self._recarregar_versoes(self._versao_atual.id if self._versao_atual else None)

    def _carregar_versao_por_id(self, versao_id: int):
        if not self.salvar_se_pendente():
            return
        self._recarregar_versoes(versao_id)

    def _abrir_diff(self):
        if not self._regra_id:
            return
        if not self.salvar_se_pendente():
            return
        versoes = M.listar_versoes(self.conn, self._regra_id)
        if len(versoes) < 2:
            QMessageBox.information(self, "Diff", "É necessário ao menos 2 versões para comparar.")
            return
        dlg = DiffViewer(self.conn, self._regra_id, parent=self)
        dlg.exec()
