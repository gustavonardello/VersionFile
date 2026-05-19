import sys
import shutil
from PyQt6.QtWidgets import QApplication
from database.db import initialize_db, get_connection, DB_PATH
from ui.main_window import MainWindow
from core.paths import base_path, data_path


def _bootstrap():
    """Garante que arquivos de configuração existam ao lado do .exe."""
    dest = data_path() / "config"
    dest.mkdir(parents=True, exist_ok=True)
    themes_dest = dest / "themes.json"
    if not themes_dest.exists():
        themes_src = base_path() / "config" / "themes.json"
        if themes_src.exists():
            shutil.copy2(themes_src, themes_dest)


def main():
    _bootstrap()
    db_is_new = not DB_PATH.exists()
    initialize_db()
    if db_is_new:
        print(f"Banco de dados criado em: {DB_PATH}")
    else:
        print(f"Banco de dados existente preservado: {DB_PATH}")
    conn = get_connection()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(conn)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
