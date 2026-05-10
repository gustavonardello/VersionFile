import difflib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSplitter, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.Qsci import QsciScintilla
import database.models as M

# Índices dos markers de linha
MARKER_REMOVIDO = 0
MARKER_ADICAO   = 1
MARKER_MUDADO   = 2
MARKER_VAZIO    = 3

# Cores de fundo para cada status (fundo branco nos editores)
COR_REMOVIDO = "#FFCCCC"
COR_ADICAO   = "#CCFFCC"
COR_MUDADO   = "#FFFACC"
COR_VAZIO    = "#EEEEEE"


def _calcular_diff(linhas_a: list[str], linhas_b: list[str]):
    """
    Retorna (lado_esq, lado_dir) onde cada lado é list[tuple[str, str]]:
      (texto_da_linha, status)  —  status: 'igual' | 'removido' | 'adicao' | 'mudado' | 'vazio'
    """
    esq, dir_ = [], []
    matcher = difflib.SequenceMatcher(None, linhas_a, linhas_b, autojunk=False)
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            for linha in linhas_a[i1:i2]:
                esq.append((linha,  "igual"))
                dir_.append((linha, "igual"))
        elif opcode == "delete":
            for linha in linhas_a[i1:i2]:
                esq.append((linha,  "removido"))
                dir_.append(("",   "vazio"))
        elif opcode == "insert":
            for linha in linhas_b[j1:j2]:
                esq.append(("",    "vazio"))
                dir_.append((linha,"adicao"))
        elif opcode == "replace":
            bloco_a = linhas_a[i1:i2]
            bloco_b = linhas_b[j1:j2]
            tamanho = max(len(bloco_a), len(bloco_b))
            for k in range(tamanho):
                la = bloco_a[k] if k < len(bloco_a) else None
                lb = bloco_b[k] if k < len(bloco_b) else None
                esq.append((la if la is not None else "", "mudado" if la is not None else "vazio"))
                dir_.append((lb if lb is not None else "", "mudado" if lb is not None else "vazio"))
    return esq, dir_


def _criar_editor() -> QsciScintilla:
    editor = QsciScintilla()
    editor.setReadOnly(True)
    editor.setFont(QFont("Consolas", 10))
    editor.setWrapMode(QsciScintilla.WrapMode.WrapNone)
    editor.setLexer(None)

    editor.setPaper(QColor("#FFFFFF"))
    editor.setColor(QColor("#1E1E1E"))
    editor.setMarginsBackgroundColor(QColor("#F3F3F3"))
    editor.setMarginsForegroundColor(QColor("#999999"))
    editor.setCaretLineVisible(False)

    editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
    editor.setMarginWidth(0, "0000")

    # Define markers de fundo por linha
    for marker, cor in [
        (MARKER_REMOVIDO, COR_REMOVIDO),
        (MARKER_ADICAO,   COR_ADICAO),
        (MARKER_MUDADO,   COR_MUDADO),
        (MARKER_VAZIO,    COR_VAZIO),
    ]:
        editor.markerDefine(QsciScintilla.MarkerSymbol.Background, marker)
        editor.setMarkerBackgroundColor(QColor(cor), marker)

    editor.setStyleSheet("""
        QScrollBar:vertical   { background:#2D2D2D; width:10px; }
        QScrollBar::handle:vertical   { background:#555; border-radius:4px; }
        QScrollBar:horizontal { background:#2D2D2D; height:10px; }
        QScrollBar::handle:horizontal { background:#555; border-radius:4px; }
    """)
    return editor


def _preencher_editor(editor: QsciScintilla, linhas: list[tuple[str, str]]):
    editor.setReadOnly(False)
    editor.setText("\n".join(t for t, _ in linhas))
    editor.setReadOnly(True)

    for m in [MARKER_REMOVIDO, MARKER_ADICAO, MARKER_MUDADO, MARKER_VAZIO]:
        editor.markerDeleteAll(m)

    status_marker = {
        "removido": MARKER_REMOVIDO,
        "adicao":   MARKER_ADICAO,
        "mudado":   MARKER_MUDADO,
        "vazio":    MARKER_VAZIO,
    }
    for i, (_, status) in enumerate(linhas):
        if status in status_marker:
            editor.markerAdd(i, status_marker[status])


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
        sel = QHBoxLayout()
        sel.setSpacing(6)
        sel.addWidget(QLabel("Versão A (antes):"))
        self.combo_a = QComboBox()
        for v in self.versoes:
            self.combo_a.addItem(f"v{v.numero} — {v.status}  ({v.criado_em[:10]})", userData=v)
        sel.addWidget(self.combo_a)
        sel.addSpacing(12)
        sel.addWidget(QLabel("Versão B (depois):"))
        self.combo_b = QComboBox()
        for v in self.versoes:
            self.combo_b.addItem(f"v{v.numero} — {v.status}  ({v.criado_em[:10]})", userData=v)
        sel.addWidget(self.combo_b)
        sel.addSpacing(12)
        btn = QPushButton("Comparar")
        btn.clicked.connect(self._comparar)
        sel.addWidget(btn)
        sel.addStretch()
        layout.addLayout(sel)

        # Legenda
        legenda = QHBoxLayout()
        legenda.setSpacing(6)
        legenda.addWidget(self._badge("Removido",      COR_REMOVIDO, "#990000"))
        legenda.addWidget(self._badge("Adicionado",    COR_ADICAO,   "#006600"))
        legenda.addWidget(self._badge("Alterado",      COR_MUDADO,   "#806600"))
        legenda.addWidget(self._badge("Sem alteração", "#FFFFFF",    "#1E1E1E"))
        legenda.addStretch()
        layout.addLayout(legenda)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Headers
        headers = QHBoxLayout()
        headers.setContentsMargins(0, 0, 0, 0)
        self.label_a = QLabel("v? — antes")
        self.label_b = QLabel("v? — depois")
        for lbl in (self.label_a, self.label_b):
            lbl.setStyleSheet("font-weight:bold; font-size:11px; padding:0 2px;")
        headers.addWidget(self.label_a)
        headers.addWidget(self.label_b)
        layout.addLayout(headers)

        # Editores
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_a = _criar_editor()
        self.editor_b = _criar_editor()
        splitter.addWidget(self.editor_a)
        splitter.addWidget(self.editor_b)
        layout.addWidget(splitter, 1)

        # Sincronizar scroll
        self.editor_a.verticalScrollBar().valueChanged.connect(
            self.editor_b.verticalScrollBar().setValue)
        self.editor_b.verticalScrollBar().valueChanged.connect(
            self.editor_a.verticalScrollBar().setValue)
        self.editor_a.horizontalScrollBar().valueChanged.connect(
            self.editor_b.horizontalScrollBar().setValue)
        self.editor_b.horizontalScrollBar().valueChanged.connect(
            self.editor_a.horizontalScrollBar().setValue)

        # Rodapé
        self.label_stats = QLabel("")
        self.label_stats.setStyleSheet("color:#858585; font-size:11px; padding:1px 2px;")
        layout.addWidget(self.label_stats)

    def _badge(self, texto: str, bg: str, fg: str) -> QLabel:
        lbl = QLabel(f" {texto} ")
        lbl.setFixedHeight(18)
        lbl.setStyleSheet(
            f"background-color:{bg}; color:{fg}; border:1px solid #BBBBBB;"
            f"font-family:Consolas; font-size:11px; border-radius:2px; padding:0 4px;"
        )
        return lbl

    def _comparar(self):
        v_a = self.combo_a.currentData()
        v_b = self.combo_b.currentData()
        if not v_a or not v_b:
            return

        self.label_a.setText(f"v{v_a.numero} — {v_a.status}")
        self.label_b.setText(f"v{v_b.numero} — {v_b.status}")

        esq, dir_ = _calcular_diff(v_a.conteudo.splitlines(), v_b.conteudo.splitlines())
        _preencher_editor(self.editor_a, esq)
        _preencher_editor(self.editor_b, dir_)

        removidas   = sum(1 for _, s in esq  if s == "removido")
        adicionadas = sum(1 for _, s in dir_ if s == "adicao")
        alteradas   = sum(1 for _, s in esq  if s == "mudado")
        self.label_stats.setText(
            f"  -{removidas} removidas   +{adicionadas} adicionadas   ~{alteradas} alteradas"
        )

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QComboBox {
                background-color: #3C3C3C;
                border: 1px solid #555;
                color: #D4D4D4;
                padding: 2px 6px;
                border-radius: 2px;
            }
            QLabel { color: #D4D4D4; font-family: Segoe UI; }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 4px 14px;
                border-radius: 2px;
            }
            QPushButton:hover { background-color: #1177BB; }
            QSplitter::handle { background-color: #444; width: 2px; }
            QFrame { color: #444; }
        """)
