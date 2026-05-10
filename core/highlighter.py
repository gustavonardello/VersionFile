import json
from pathlib import Path
from PyQt6.Qsci import QsciScintilla, QsciLexerCustom
from PyQt6.QtGui import QColor, QFont
from core.paths import data_path

THEMES_PATH = data_path() / "config" / "themes.json"

# Estilos (índices QScintilla)
STYLE_DEFAULT    = 0
STYLE_KEYWORD    = 1
STYLE_KEYWORD2   = 2
STYLE_TYPE       = 3
STYLE_NUMBER     = 4
STYLE_STRING     = 5
STYLE_COMMENT    = 6
STYLE_OPERATOR   = 7
STYLE_IDENTIFIER = 8

# Palavras-chave LSP
KEYWORDS = {
    "definir", "funcao", "se", "senao", "senaose", "enquanto", "para",
    "retornar", "retorne", "inicio", "fim", "fimse", "fimenquanto",
    "fimpara", "fimfuncao", "nao", "e", "ou", "verdadeiro", "falso",
    "vazio", "interromper", "continuar", "chamar",
}

KEYWORDS2 = {
    "imprimir", "limpar", "ler", "abrir", "fechar", "executar",
    "existearquivo", "copiar", "mover", "deletar",
}

TYPES = {
    "Alfa", "Numero", "Data", "Logico", "Cursor",
}


def load_theme(name: str = None) -> dict:
    data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    active = name or data["active_theme"]
    return data["themes"].get(active, list(data["themes"].values())[0])


def list_themes() -> list[str]:
    data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    return list(data["themes"].keys())


def save_active_theme(name: str):
    data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    data["active_theme"] = name
    THEMES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def gerar_stylesheet_ui(tema: dict) -> str:
    u = tema.get("ui", {})
    ab  = u.get("app_background",     "#F0F0F0")
    pb  = u.get("panel_background",   "#FAFAFA")
    tb  = u.get("tree_background",    "#FFFFFF")
    mb  = u.get("menubar_background", "#E8E8E8")
    tx  = u.get("text",               "#1E1E1E")
    mt  = u.get("text_muted",         "#666666")
    bd  = u.get("border",             "#CCCCCC")
    sel = u.get("item_selected",      "#ADD6FF")
    hov = u.get("item_hover",         "#E5EEF8")
    inp = u.get("input_background",   "#FFFFFF")
    bp  = u.get("button_primary",     "#0E639C")
    bt  = u.get("button_text",        "#FFFFFF")
    sp  = u.get("splitter",           "#CCCCCC")
    sh  = u.get("scrollbar_handle",   "#BBBBBB")

    return f"""
        QMainWindow, QWidget {{
            background-color: {ab};
            color: {tx};
        }}
        QMenuBar {{
            background-color: {mb};
            color: {tx};
        }}
        QMenuBar::item:selected {{ background: {sel}; }}
        QMenu {{
            background-color: {pb};
            color: {tx};
            border: 1px solid {bd};
        }}
        QMenu::item:selected {{ background-color: {sel}; }}
        QTreeWidget {{
            background-color: {tb};
            color: {tx};
            border: none;
            font-family: Segoe UI;
            font-size: 12px;
        }}
        QTreeWidget::item:selected {{ background-color: {sel}; color: {tx}; }}
        QTreeWidget::item:hover    {{ background-color: {hov}; }}
        QHeaderView::section {{
            background-color: {pb};
            color: {mt};
            border: none;
            padding: 2px 4px;
        }}
        QComboBox, QLineEdit, QTextEdit {{
            background-color: {inp};
            border: 1px solid {bd};
            color: {tx};
            padding: 2px 4px;
            border-radius: 2px;
        }}
        QComboBox:disabled, QLineEdit:disabled, QTextEdit:disabled {{
            color: {mt};
            border-color: {bd};
        }}
        QPushButton {{
            background-color: {bp};
            color: {bt};
            border: none;
            padding: 4px 10px;
            border-radius: 2px;
        }}
        QPushButton:hover   {{ background-color: #1177BB; }}
        QPushButton:pressed {{ background-color: #0A4F82; }}
        QPushButton:disabled {{ background-color: {bd}; color: {mt}; }}
        QLabel {{ font-family: Segoe UI; color: {tx}; }}
        QCheckBox {{ color: {tx}; }}
        QSplitter::handle {{ background-color: {sp}; }}
        QScrollBar:vertical {{
            background: {ab};
            width: 10px;
        }}
        QScrollBar::handle:vertical {{
            background: {sh};
            border-radius: 4px;
        }}
        QScrollBar:horizontal {{
            background: {ab};
            height: 10px;
        }}
        QScrollBar::handle:horizontal {{
            background: {sh};
            border-radius: 4px;
        }}
    """


class LSPLexer(QsciLexerCustom):
    def __init__(self, parent=None, theme_name: str = None):
        super().__init__(parent)
        self._theme = load_theme(theme_name)
        self._apply_theme()

    def _apply_theme(self):
        t = self._theme
        font = QFont("Consolas", 10)

        self.setDefaultPaper(QColor(t["background"]))
        self.setDefaultColor(QColor(t["foreground"]))
        self.setDefaultFont(font)

        style_map = {
            STYLE_DEFAULT:    (t["foreground"],  t["background"], False),
            STYLE_KEYWORD:    (t["keyword"],     t["background"], True),
            STYLE_KEYWORD2:   (t["keyword2"],    t["background"], True),
            STYLE_TYPE:       (t["type"],        t["background"], True),
            STYLE_NUMBER:     (t["number"],      t["background"], False),
            STYLE_STRING:     (t["string"],      t["background"], False),
            STYLE_COMMENT:    (t["comment"],     t["background"], False),
            STYLE_OPERATOR:   (t["operator"],    t["background"], False),
            STYLE_IDENTIFIER: (t["identifier"],  t["background"], False),
        }

        for style, (fg, bg, bold) in style_map.items():
            f = QFont("Consolas", 10)
            f.setBold(bold)
            self.setColor(QColor(fg), style)
            setPaperOf = QColor(bg)
            self.setPaper(setPaperOf, style)
            self.setFont(f, style)

    def apply_theme(self, theme_name: str):
        self._theme = load_theme(theme_name)
        self._apply_theme()
        if self.editor():
            self.editor().recolor()

    def language(self):
        return "LSP"

    def description(self, style):
        names = {
            STYLE_DEFAULT:    "Default",
            STYLE_KEYWORD:    "Keyword",
            STYLE_KEYWORD2:   "Keyword2",
            STYLE_TYPE:       "Type",
            STYLE_NUMBER:     "Number",
            STYLE_STRING:     "String",
            STYLE_COMMENT:    "Comment",
            STYLE_OPERATOR:   "Operator",
            STYLE_IDENTIFIER: "Identifier",
        }
        return names.get(style, "")

    def styleText(self, start, end):
        editor = self.editor()
        if not editor:
            return

        text = editor.text()[start:end]
        self.startStyling(start)

        i = 0
        while i < len(text):
            ch = text[i]

            # Comentário linha (// ou @)
            if ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
                j = i
                while j < len(text) and text[j] != '\n':
                    j += 1
                self.setStyling(j - i, STYLE_COMMENT)
                i = j
                continue

            if ch == '@':
                j = i
                while j < len(text) and text[j] != '\n':
                    j += 1
                self.setStyling(j - i, STYLE_COMMENT)
                i = j
                continue

            # String com aspas duplas
            if ch == '"':
                j = i + 1
                while j < len(text) and text[j] != '"':
                    if text[j] == '\\':
                        j += 1
                    j += 1
                j += 1
                self.setStyling(j - i, STYLE_STRING)
                i = j
                continue

            # Número
            if ch.isdigit() or (ch == '-' and i + 1 < len(text) and text[i + 1].isdigit()):
                j = i + 1 if ch == '-' else i
                while j < len(text) and (text[j].isdigit() or text[j] == '.'):
                    j += 1
                self.setStyling(j - i, STYLE_NUMBER)
                i = j
                continue

            # Operadores
            if ch in '+-*/=<>!&|%()[]{}.,;:':
                self.setStyling(1, STYLE_OPERATOR)
                i += 1
                continue

            # Identificadores e palavras-chave
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                word = text[i:j]
                word_lower = word.lower()

                if word_lower in KEYWORDS:
                    self.setStyling(j - i, STYLE_KEYWORD)
                elif word_lower in KEYWORDS2:
                    self.setStyling(j - i, STYLE_KEYWORD2)
                elif word in TYPES:
                    self.setStyling(j - i, STYLE_TYPE)
                else:
                    self.setStyling(j - i, STYLE_IDENTIFIER)
                i = j
                continue

            self.setStyling(1, STYLE_DEFAULT)
            i += 1
