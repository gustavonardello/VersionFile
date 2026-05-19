import json
from pathlib import Path
from PyQt6.Qsci import QsciScintilla, QsciLexerCustom
from PyQt6.QtGui import QColor, QFont
from core.paths import data_path

THEMES_PATH = data_path() / "config" / "themes.json"

# Estilos (índices QScintilla)
STYLE_DEFAULT    = 0
STYLE_KEYWORD    = 1   # palavras-chave de controle/estrutura (azul)
STYLE_FUNCTION   = 2   # funções/métodos chamados com () (roxo)
STYLE_TYPE       = 3   # tipos de dados: alfa, numero, data... (teal)
STYLE_NUMBER     = 4   # literais numéricos (verde claro)
STYLE_STRING     = 5   # strings entre aspas (laranja)
STYLE_COMMENT    = 6   # comentários @ ... @ ou @ ... \n (verde)
STYLE_OPERATOR   = 7   # operadores e pontuação
STYLE_IDENTIFIER = 8   # variáveis e identificadores (azul claro)
STYLE_CONSTANT   = 9   # constantes: cverdadeiro, cfalso (amarelo)

# --- Palavras-chave do grammar oficial (llutti/vscode-language-lsp) ---

# Controle de fluxo e estrutura
KEYWORDS = {
    "se", "senao", "senaose", "enquanto", "para", "continue", "pare",
    "vapara", "vaparacampo", "vaparapagina",
    "definir", "funcao", "retorna", "erro",
    "inicio", "fim", "end", "regra", "tabela",
    "iniciartransacao", "desfazertransacao", "finalizartransacao",
    "chamarfuncao", "mensagem",
    "e", "ou", "nao",
}

# Tipos de dados primitivos
TYPES = {
    "alfa", "numero", "data", "cursor", "lista", "tabela", "logico",
}

# Constantes booleanas
CONSTANTS = {
    "cverdadeiro", "cfalso",
}

# Funções built-in conhecidas (além da detecção automática por `(`)
BUILTIN_FUNCTIONS = {
    # SQL / ExecSQL
    "execsql", "execsqlex", "sql_definircomando",
    # Métodos de cursor/tabela (acessados via .)
    "abrircursor", "achou", "fecharcursor", "naoachou", "proximo",
    "sql", "usaabrangencia", "adicionar", "adicionarcampo",
    "anterior", "cancelar", "chave", "definircampos", "editar",
    "editarchave", "efetivarcampos", "excluir", "fda", "gravar",
    "ida", "inserir", "limpar", "numreg", "primeiro", "qtdregistros",
    "setanumreg", "setarchave", "ultimo", "vaiparachave",
    # Funções de string
    "copiarparte", "tamanho", "maiusculo", "minusculo", "remover",
    "substituir", "posicao", "converter", "formatar", "concatenar",
    # Funções de data/número
    "hoje", "agora", "ano", "mes", "dia", "hora", "minuto",
    "arredondar", "truncar", "absoluto", "potencia", "raiz",
    # Conversão
    "alfaparanumero", "numeroparaalfa", "dataparaalfa", "alfaparadata",
    # I/O
    "imprimir", "limpar", "ler", "abrir", "fechar", "executar",
    "existearquivo", "copiar", "mover", "deletar",
    # Lista
    "tamanholista", "adicionarlista", "removerlista", "limparlista",
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
            STYLE_FUNCTION:   (t["function"],    t["background"], False),
            STYLE_TYPE:       (t["type"],        t["background"], True),
            STYLE_NUMBER:     (t["number"],      t["background"], False),
            STYLE_STRING:     (t["string"],      t["background"], False),
            STYLE_COMMENT:    (t["comment"],     t["background"], False),
            STYLE_OPERATOR:   (t["operator"],    t["background"], False),
            STYLE_IDENTIFIER: (t["identifier"],  t["background"], False),
            STYLE_CONSTANT:   (t["constant"],    t["background"], True),
        }

        for style, (fg, bg, bold) in style_map.items():
            f = QFont("Consolas", 10)
            f.setBold(bold)
            self.setColor(QColor(fg), style)
            self.setPaper(QColor(bg), style)
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
            STYLE_FUNCTION:   "Function",
            STYLE_TYPE:       "Type",
            STYLE_NUMBER:     "Number",
            STYLE_STRING:     "String",
            STYLE_COMMENT:    "Comment",
            STYLE_OPERATOR:   "Operator",
            STYLE_IDENTIFIER: "Identifier",
            STYLE_CONSTANT:   "Constant",
        }
        return names.get(style, "")

    def styleText(self, start, end):
        editor = self.editor()
        if not editor:
            return

        # setUtf8(True) → start/end são offsets de BYTES UTF-8, não de caracteres.
        # Precisamos trabalhar em bytes para que setStyling receba comprimentos corretos.
        source_bytes = editor.text().encode('utf-8')
        text = source_bytes[start:end].decode('utf-8', errors='replace')

        self.startStyling(start)

        def emit(token: str, style: int):
            self.setStyling(len(token.encode('utf-8')), style)

        i = 0
        while i < len(text):
            ch = text[i]

            # Comentário: @ ... @ (inline) ou @ ... \n (até fim de linha)
            if ch == '@':
                j = i + 1
                while j < len(text) and text[j] != '@' and text[j] != '\n':
                    j += 1
                if j < len(text) and text[j] == '@':
                    j += 1  # inclui o @ de fechamento
                emit(text[i:j], STYLE_COMMENT)
                i = j
                continue

            # Comentário linha: // ...
            if ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
                j = i
                while j < len(text) and text[j] != '\n':
                    j += 1
                emit(text[i:j], STYLE_COMMENT)
                i = j
                continue

            # String com aspas duplas
            if ch == '"':
                j = i + 1
                while j < len(text) and text[j] != '"':
                    if text[j] == '\\':
                        j += 1
                    j += 1
                if j < len(text):
                    j += 1
                emit(text[i:j], STYLE_STRING)
                i = j
                continue

            # Número
            if ch.isdigit():
                j = i + 1
                while j < len(text) and (text[j].isdigit() or text[j] == '.'):
                    j += 1
                emit(text[i:j], STYLE_NUMBER)
                i = j
                continue

            # Identificador, palavra-chave, tipo, constante ou função
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                word = text[i:j]
                word_lower = word.lower()

                if word_lower in KEYWORDS:
                    emit(word, STYLE_KEYWORD)
                elif word_lower in TYPES:
                    emit(word, STYLE_TYPE)
                elif word_lower in CONSTANTS:
                    emit(word, STYLE_CONSTANT)
                elif word_lower in BUILTIN_FUNCTIONS:
                    emit(word, STYLE_FUNCTION)
                else:
                    # Detecta chamada de função: identificador seguido de (
                    k = j
                    while k < len(text) and text[k] in ' \t':
                        k += 1
                    if k < len(text) and text[k] == '(':
                        emit(word, STYLE_FUNCTION)
                    else:
                        emit(word, STYLE_IDENTIFIER)
                i = j
                continue

            # Operadores e pontuação
            if ch in '+-*/=<>!&|%()[]{}.,;:':
                emit(ch, STYLE_OPERATOR)
                i += 1
                continue

            emit(ch, STYLE_DEFAULT)
            i += 1
