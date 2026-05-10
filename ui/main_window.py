from PyQt6.QtWidgets import QMainWindow, QSplitter, QWidget, QVBoxLayout, QMenuBar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QAction, QIcon
from ui.tree_panel import TreePanel
from ui.editor_panel import EditorPanel
from ui.export_dialog import ExportDialog
from core.paths import base_path


class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.setWindowTitle("VersionFile — Gerenciador de Regras LSP")
        self.resize(1200, 750)

        icone = base_path() / "icone.ico"
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        self._aplicar_estilo()
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

    def _criar_menu(self):
        barra = self.menuBar()
        barra.setStyleSheet(
            "QMenuBar { background:#252526; color:#D4D4D4; }"
            "QMenuBar::item:selected { background:#094771; }"
            "QMenu { background:#252526; color:#D4D4D4; border:1px solid #444; }"
            "QMenu::item:selected { background:#094771; }"
        )

        menu_arquivo = barra.addMenu("Arquivo")

        act_exportar = QAction("Exportar múltiplas regras...", self)
        act_exportar.setShortcut("Ctrl+E")
        act_exportar.triggered.connect(self._abrir_exportacao)
        menu_arquivo.addAction(act_exportar)

        menu_arquivo.addSeparator()

        act_sair = QAction("Sair", self)
        act_sair.setShortcut("Alt+F4")
        act_sair.triggered.connect(self.close)
        menu_arquivo.addAction(act_sair)

    def closeEvent(self, event):
        self.editor_panel.salvar_se_pendente()
        super().closeEvent(event)

    def _abrir_exportacao(self):
        dlg = ExportDialog(self.conn, parent=self)
        dlg.exec()

    def _aplicar_estilo(self):
        self.menuBar().setStyleSheet(
            "QMenuBar { background:#252526; color:#D4D4D4; }"
            "QMenuBar::item:selected { background:#094771; }"
            "QMenu { background:#252526; color:#D4D4D4; border:1px solid #444; }"
            "QMenu::item:selected { background:#094771; }"
        )
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QTreeWidget {
                background-color: #252526;
                border: none;
                font-family: Segoe UI;
                font-size: 12px;
            }
            QTreeWidget::item:selected { background-color: #094771; }
            QTreeWidget::item:hover    { background-color: #2A2D2E; }
            QComboBox, QLineEdit, QTextEdit {
                background-color: #3C3C3C;
                border: 1px solid #555;
                color: #D4D4D4;
                padding: 2px 4px;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 2px;
            }
            QPushButton:hover   { background-color: #1177BB; }
            QPushButton:pressed { background-color: #0A4F82; }
            QLabel { font-family: Segoe UI; }
            QSplitter::handle { background-color: #444; }
            QScrollBar:vertical { background: #252526; width: 10px; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
        """)
