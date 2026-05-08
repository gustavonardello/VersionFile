import sys
from PyQt6.QtWidgets import QApplication
from database.db import initialize_db, get_connection
from ui.main_window import MainWindow


def main():
    initialize_db()
    conn = get_connection()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(conn)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
