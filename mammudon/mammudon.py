#!/usr/bin/env python3
import sys

from PyQt6.QtWidgets import QApplication

from mammudon.prefs import preferences
from mammudon.main_window import MainWindow


def main() -> int:
	app = QApplication(sys.argv)

	app.setOrganizationName("Mammudon")
	app.setApplicationName("Mammudon")

	preferences.app = app
	preferences.load_settings()

	app.setQuitOnLastWindowClosed(not preferences.values["minimize_to_tray"])

	window = MainWindow()
	window.show()

	return app.exec()
