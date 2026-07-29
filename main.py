import sys
import shutil
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from database.db import initialize_db, get_connection, DB_PATH
from ui.main_window import MainWindow
from ui.migracao_dialog import garantir_dados
from core.paths import base_path, data_path


def _bootstrap():
    """Garante que os arquivos de configuração existam na pasta de dados."""
    dest = data_path() / "config"
    dest.mkdir(parents=True, exist_ok=True)
    themes_dest = dest / "themes.json"
    if not themes_dest.exists():
        themes_src = base_path() / "config" / "themes.json"
        if themes_src.exists():
            shutil.copy2(themes_src, themes_dest)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icone = base_path() / "icone.ico"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))

    # Precisa vir antes de qualquer acesso ao banco: resolve de onde os dados
    # devem ser lidos quando o local mudou entre versões do app.
    if not garantir_dados():
        sys.exit(0)

    _bootstrap()
    db_is_new = not DB_PATH.exists()
    initialize_db()
    if db_is_new:
        print(f"Banco de dados criado em: {DB_PATH}")
    else:
        print(f"Banco de dados existente preservado: {DB_PATH}")
    conn = get_connection()

    window = MainWindow(conn)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
