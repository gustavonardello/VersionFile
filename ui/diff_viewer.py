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

# Cores de fundo para cada status (fundo escuro nos editores)
COR_REMOVIDO = "#4B1818"
COR_ADICAO   = "#1A3A1A"
COR_MUDADO   = "#3A3000"
COR_VAZIO    = "#2A2A2A"


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

    editor.setPaper(QColor("#1E1E1E"))
    editor.setColor(QColor("#D4D4D4"))
    editor.setMarginsBackgroundColor(QColor("#252526"))
    editor.setMarginsForegroundColor(QColor("#858585"))
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
        self._bg_mode = "black"
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

        # Barra de seleção
        sel = QHBoxLayout()
        sel.setSpacing(8)

        lbl_a = QLabel("Versão A — antes:")
        lbl_a.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        sel.addWidget(lbl_a)

        self.combo_a = QComboBox()
        for v in self.versoes:
            atual = "  [atual]" if v.atual else ""
            self.combo_a.addItem(f"{v.numero}  ·  {v.tipo}{atual}  ({v.criado_em[:10]})", userData=v)
        sel.addWidget(self.combo_a)

        sel.addSpacing(16)

        lbl_b = QLabel("Versão B — depois:")
        lbl_b.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        sel.addWidget(lbl_b)

        self.combo_b = QComboBox()
        for v in self.versoes:
            atual = "  [atual]" if v.atual else ""
            self.combo_b.addItem(f"{v.numero}  ·  {v.tipo}{atual}  ({v.criado_em[:10]})", userData=v)
        sel.addWidget(self.combo_b)

        sel.addSpacing(12)
        btn = QPushButton("Comparar")
        btn.clicked.connect(self._comparar)
        sel.addWidget(btn)
        sel.addStretch()

        self.btn_bg_black = QPushButton()
        self.btn_bg_black.setFixedSize(18, 18)
        self.btn_bg_black.setToolTip("Fundo preto")
        self.btn_bg_black.clicked.connect(lambda: self._set_bg_mode("black"))
        sel.addWidget(self.btn_bg_black)

        self.btn_bg_white = QPushButton()
        self.btn_bg_white.setFixedSize(18, 18)
        self.btn_bg_white.setToolTip("Fundo branco")
        self.btn_bg_white.clicked.connect(lambda: self._set_bg_mode("white"))
        sel.addWidget(self.btn_bg_white)

        self._atualizar_estilo_botoes_bg()
        layout.addLayout(sel)

        # Legenda
        legenda = QHBoxLayout()
        legenda.setSpacing(8)
        legenda.addWidget(self._badge("Removido",      COR_REMOVIDO, "#F48771"))
        legenda.addWidget(self._badge("Adicionado",    COR_ADICAO,   "#89D185"))
        legenda.addWidget(self._badge("Alterado",      COR_MUDADO,   "#E5C07B"))
        legenda.addWidget(self._badge("Sem alteração", "#2D2D2D",    "#858585"))
        legenda.addStretch()
        layout.addLayout(legenda)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3A3A3A; border: none;")
        layout.addWidget(sep)

        # Headers dos painéis
        headers = QHBoxLayout()
        headers.setContentsMargins(0, 2, 0, 2)
        self.label_a = QLabel("? — antes")
        self.label_b = QLabel("? — depois")
        for lbl in (self.label_a, self.label_b):
            lbl.setStyleSheet(
                "color: #FFFFFF; font-weight: bold; font-size: 12px;"
                "padding: 4px 6px; background: #2D2D2D; border-radius: 4px;"
            )
        headers.addWidget(self.label_a)
        headers.addSpacing(4)
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
        self.label_stats.setStyleSheet(
            "color: #D4D4D4; font-size: 11px; padding: 3px 4px;"
            "background: #252526; border-radius: 4px;"
        )
        layout.addWidget(self.label_stats)

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

    def _set_bg_mode(self, mode: str):
        if mode == self._bg_mode:
            return
        self._bg_mode = mode

        if mode == "white":
            bg, fg = QColor("#FFFFFF"), QColor("#1E1E1E")
            margin_bg, margin_fg = QColor("#F3F3F3"), QColor("#999999")
            cores_marker = {
                MARKER_REMOVIDO: "#FFCCCC",
                MARKER_ADICAO:   "#CCFFCC",
                MARKER_MUDADO:   "#FFFACC",
                MARKER_VAZIO:    "#EEEEEE",
            }
        else:
            bg, fg = QColor("#1E1E1E"), QColor("#D4D4D4")
            margin_bg, margin_fg = QColor("#252526"), QColor("#858585")
            cores_marker = {
                MARKER_REMOVIDO: COR_REMOVIDO,
                MARKER_ADICAO:   COR_ADICAO,
                MARKER_MUDADO:   COR_MUDADO,
                MARKER_VAZIO:    COR_VAZIO,
            }

        for editor in (self.editor_a, self.editor_b):
            editor.setPaper(bg)
            editor.setColor(fg)
            editor.setMarginsBackgroundColor(margin_bg)
            editor.setMarginsForegroundColor(margin_fg)
            for marker, cor in cores_marker.items():
                editor.setMarkerBackgroundColor(QColor(cor), marker)

        self._atualizar_estilo_botoes_bg()
        self._comparar()  # re-aplica markers com as novas cores

    def _badge(self, texto: str, bg: str, fg: str) -> QLabel:
        lbl = QLabel(f"  {texto}  ")
        lbl.setFixedHeight(20)
        lbl.setStyleSheet(
            f"background-color:{bg}; color:{fg}; border:none;"
            f"font-family:Consolas; font-size:11px; border-radius:4px; padding:0 4px;"
        )
        return lbl

    def _comparar(self):
        v_a = self.combo_a.currentData()
        v_b = self.combo_b.currentData()
        if not v_a or not v_b:
            return

        self.label_a.setText(f"{v_a.numero} — {v_a.status}")
        self.label_b.setText(f"{v_b.numero} — {v_b.status}")

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
                font-family: Segoe UI;
            }
            QComboBox {
                background-color: #3C3C3C;
                border: 1px solid #4A4A4A;
                color: #D4D4D4;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 220px;
            }
            QComboBox:hover { border-color: #6A6A6A; }
            QComboBox::drop-down { border: none; width: 20px; }
            QLabel { color: #D4D4D4; font-family: Segoe UI; }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 5px 18px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1177BB; }
            QPushButton:pressed { background-color: #0A4F7A; }
            QSplitter::handle { background-color: #3A3A3A; width: 2px; }
        """)
