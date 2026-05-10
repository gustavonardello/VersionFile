import difflib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QSplitter, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor, QTextBlockFormat
import database.models as M
from core.highlighter import load_theme

# Cores para linhas com alteração (fundo branco, destaque vermelho claro)
COR_IGUAL    = ("#FFFFFF", "#1E1E1E")
COR_REMOVIDO = ("#FFE0E0", "#990000")
COR_ADICAO   = ("#FFE0E0", "#990000")
COR_MUDADO   = ("#FFE0E0", "#990000")
COR_VAZIO    = ("#F5F5F5", "#CCCCCC")


def _set_linha(cursor: QTextCursor, texto: str, bg: str, fg: str):
    block_fmt = QTextBlockFormat()
    block_fmt.setBackground(QColor(bg))
    char_fmt = QTextCharFormat()
    char_fmt.setForeground(QColor(fg))
    char_fmt.setFont(QFont("Consolas", 10))
    cursor.insertBlock(block_fmt, char_fmt)
    cursor.insertText(texto, char_fmt)


def _preencher_editor(editor: QTextEdit, linhas: list[tuple[str, str, str]]):
    editor.clear()
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    primeiro = True
    for texto, bg, fg in linhas:
        if primeiro:
            block_fmt = QTextBlockFormat()
            block_fmt.setBackground(QColor(bg))
            char_fmt = QTextCharFormat()
            char_fmt.setForeground(QColor(fg))
            char_fmt.setFont(QFont("Consolas", 10))
            cursor.setBlockFormat(block_fmt)
            cursor.setBlockCharFormat(char_fmt)
            cursor.insertText(texto, char_fmt)
            primeiro = False
        else:
            _set_linha(cursor, texto, bg, fg)
    editor.setTextCursor(cursor)


def _calcular_diff(linhas_a: list[str], linhas_b: list[str]):
    esq = []
    dir_ = []
    matcher = difflib.SequenceMatcher(None, linhas_a, linhas_b, autojunk=False)
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            for linha in linhas_a[i1:i2]:
                esq.append((linha, *COR_IGUAL))
                dir_.append((linha, *COR_IGUAL))
        elif opcode == "delete":
            for linha in linhas_a[i1:i2]:
                esq.append((linha, *COR_REMOVIDO))
                dir_.append(("", *COR_VAZIO))
        elif opcode == "insert":
            for linha in linhas_b[j1:j2]:
                esq.append(("", *COR_VAZIO))
                dir_.append((linha, *COR_ADICAO))
        elif opcode == "replace":
            bloco_a = linhas_a[i1:i2]
            bloco_b = linhas_b[j1:j2]
            tamanho = max(len(bloco_a), len(bloco_b))
            for k in range(tamanho):
                linha_a = bloco_a[k] if k < len(bloco_a) else None
                linha_b = bloco_b[k] if k < len(bloco_b) else None
                esq.append((linha_a if linha_a is not None else "", *COR_MUDADO))
                dir_.append((linha_b if linha_b is not None else "", *(COR_VAZIO if linha_b is None else COR_MUDADO)))
    return esq, dir_


class DiffViewer(QDialog):
    def __init__(self, conn, regra_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.regra_id = regra_id
        self.versoes = M.listar_versoes(conn, regra_id)

        self.setWindowTitle("Comparar Versões")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self._build_ui()
        self._aplicar_estilo()

        if len(self.versoes) >= 2:
            self.combo_b.setCurrentIndex(0)
            self.combo_a.setCurrentIndex(1)
            self._comparar()

        self.showMaximized()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 6)

        # Seleção de versões
        sel_layout = QHBoxLayout()
        sel_layout.setSpacing(6)
        sel_layout.addWidget(QLabel("Versão A (antes):"))
        self.combo_a = QComboBox()
        for v in self.versoes:
            self.combo_a.addItem(f"v{v.numero} — {v.status}  ({v.criado_em[:10]})", userData=v)
        sel_layout.addWidget(self.combo_a)
        sel_layout.addSpacing(12)
        sel_layout.addWidget(QLabel("Versão B (depois):"))
        self.combo_b = QComboBox()
        for v in self.versoes:
            self.combo_b.addItem(f"v{v.numero} — {v.status}  ({v.criado_em[:10]})", userData=v)
        sel_layout.addWidget(self.combo_b)
        sel_layout.addSpacing(12)
        btn = QPushButton("Comparar")
        btn.clicked.connect(self._comparar)
        sel_layout.addWidget(btn)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        # Legenda
        legenda = QHBoxLayout()
        legenda.setSpacing(6)
        legenda.addWidget(self._badge("Removido",     COR_REMOVIDO))
        legenda.addWidget(self._badge("Adicionado",   COR_ADICAO))
        legenda.addWidget(self._badge("Alterado",     COR_MUDADO))
        legenda.addWidget(self._badge("Sem alteração", COR_IGUAL))
        legenda.addStretch()
        layout.addLayout(legenda)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Headers das versões
        headers = QHBoxLayout()
        headers.setContentsMargins(0, 0, 0, 0)
        self.label_a = QLabel("v? — antes")
        self.label_b = QLabel("v? — depois")
        self.label_a.setStyleSheet("font-weight: bold; font-size: 11px; padding: 0px 2px;")
        self.label_b.setStyleSheet("font-weight: bold; font-size: 11px; padding: 0px 2px;")
        headers.addWidget(self.label_a)
        headers.addWidget(self.label_b)
        layout.addLayout(headers)

        # Editores lado a lado
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.editor_a = QTextEdit()
        self.editor_a.setReadOnly(True)
        self.editor_a.setFont(QFont("Consolas", 10))
        self.editor_a.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self.editor_b = QTextEdit()
        self.editor_b.setReadOnly(True)
        self.editor_b.setFont(QFont("Consolas", 10))
        self.editor_b.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        splitter.addWidget(self.editor_a)
        splitter.addWidget(self.editor_b)
        layout.addWidget(splitter, 1)   # stretch=1: ocupa todo o espaço restante

        # Sincronizar scroll
        self.editor_a.verticalScrollBar().valueChanged.connect(
            self.editor_b.verticalScrollBar().setValue
        )
        self.editor_b.verticalScrollBar().valueChanged.connect(
            self.editor_a.verticalScrollBar().setValue
        )
        self.editor_a.horizontalScrollBar().valueChanged.connect(
            self.editor_b.horizontalScrollBar().setValue
        )
        self.editor_b.horizontalScrollBar().valueChanged.connect(
            self.editor_a.horizontalScrollBar().setValue
        )

        # Rodapé
        self.label_stats = QLabel("")
        self.label_stats.setStyleSheet("font-size: 11px; padding: 1px 2px;")
        layout.addWidget(self.label_stats)

    def _badge(self, texto: str, cores: tuple) -> QLabel:
        bg, fg = cores
        label = QLabel(f" {texto} ")
        label.setStyleSheet(
            f"background-color: {bg}; color: {fg}; "
            f"font-family: Consolas; font-size: 11px; "
            f"border-radius: 2px; padding: 0px 4px;"
        )
        label.setFixedHeight(18)
        return label

    def _comparar(self):
        v_a = self.combo_a.currentData()
        v_b = self.combo_b.currentData()
        if not v_a or not v_b:
            return

        self.label_a.setText(f"v{v_a.numero} — {v_a.status}")
        self.label_b.setText(f"v{v_b.numero} — {v_b.status}")

        linhas_a = v_a.conteudo.splitlines()
        linhas_b = v_b.conteudo.splitlines()

        esq, dir_ = _calcular_diff(linhas_a, linhas_b)
        _preencher_editor(self.editor_a, esq)
        _preencher_editor(self.editor_b, dir_)

        removidas   = sum(1 for _, bg, _ in esq  if bg == COR_REMOVIDO[0])
        adicionadas = sum(1 for _, bg, _ in dir_ if bg == COR_ADICAO[0])
        alteradas   = sum(1 for _, bg, _ in esq  if bg == COR_MUDADO[0])

        tema = load_theme()
        u = tema.get("ui", {})
        mt = u.get("text_muted", "#666666")
        self.label_stats.setStyleSheet(f"color: {mt}; font-size: 11px; padding: 1px 2px;")
        self.label_stats.setText(
            f"  -{removidas} removidas   +{adicionadas} adicionadas   ~{alteradas} alteradas"
        )

    def _aplicar_estilo(self):
        tema = load_theme()
        u = tema.get("ui", {})
        ab  = u.get("app_background",   "#F0F0F0")
        pb  = u.get("panel_background", "#FAFAFA")
        tx  = u.get("text",             "#1E1E1E")
        bd  = u.get("border",           "#CCCCCC")
        sel = u.get("item_selected",    "#ADD6FF")
        inp = u.get("input_background", "#FFFFFF")
        sh  = u.get("scrollbar_handle", "#BBBBBB")

        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {ab};
                color: {tx};
            }}
            QTextEdit {{
                background-color: {inp};
                color: {tx};
                border: 1px solid {bd};
            }}
            QComboBox, QLabel {{
                color: {tx};
                font-family: Segoe UI;
            }}
            QComboBox {{
                background-color: {inp};
                border: 1px solid {bd};
                padding: 2px 6px;
                border-radius: 2px;
            }}
            QPushButton {{
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 4px 14px;
                border-radius: 2px;
            }}
            QPushButton:hover {{ background-color: #1177BB; }}
            QSplitter::handle {{ background-color: {bd}; }}
            QScrollBar:vertical {{ background: {pb}; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {sh}; border-radius: 4px; }}
            QScrollBar:horizontal {{ background: {pb}; height: 10px; }}
            QScrollBar::handle:horizontal {{ background: {sh}; border-radius: 4px; }}
            QFrame {{ color: {bd}; }}
        """)
