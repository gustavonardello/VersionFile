from PyQt6.QtWidgets import QMainWindow, QSplitter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from ui.tree_panel import TreePanel
from ui.editor_panel import EditorPanel
from ui.export_dialog import ExportDialog
from core.paths import base_path
from core.highlighter import load_theme, gerar_stylesheet_ui


class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.setWindowTitle("VersionFile — Gerenciador de Regras LSP")
        self.resize(1200, 750)

        icone = base_path() / "icone.ico"
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        self._criar_menu()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree_panel = TreePanel(conn)
        self.tree_panel.setMinimumWidth(220)
        self.tree_panel.setMaximumWidth(360)
        splitter.addWidget(self.tree_panel)

        self.editor_panel = EditorPanel(conn)
        splitter.addWidget(self.editor_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])

        self.setCentralWidget(splitter)

        self.tree_panel.regra_selecionada.connect(self.editor_panel.abrir_regra)
        self.tree_panel.regra_desmarcada.connect(self.editor_panel.desabilitar_acoes)
        self.editor_panel.tema_alterado.connect(self._aplicar_tema_ui)

        # Aplica o tema salvo na inicialização
        self._aplicar_tema_ui(load_theme())

    def _criar_menu(self):
        menu_arquivo = self.menuBar().addMenu("Arquivo")

        act_exportar = QAction("Exportar múltiplas regras...", self)
        act_exportar.setShortcut("Ctrl+E")
        act_exportar.triggered.connect(self._abrir_exportacao)
        menu_arquivo.addAction(act_exportar)

        menu_arquivo.addSeparator()

        act_sair = QAction("Sair", self)
        act_sair.setShortcut("Alt+F4")
        act_sair.triggered.connect(self.close)
        menu_arquivo.addAction(act_sair)

    def _aplicar_tema_ui(self, tema: dict):
        self.setStyleSheet(gerar_stylesheet_ui(tema))

    def closeEvent(self, event):
        self.editor_panel.salvar_se_pendente()
        super().closeEvent(event)

    def _abrir_exportacao(self):
        dlg = ExportDialog(self.conn, parent=self)
        dlg.exec()
