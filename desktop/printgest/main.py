import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from printgest import APP_NAME, __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {__version__}")
        self.setMinimumSize(1024, 640)
        self.setCentralWidget(QLabel(f"{APP_NAME} — Fase 0 (skeleton)"))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()