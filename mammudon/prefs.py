# TODO: moving the main functionality of displaying the preferences and changing them into
#       the actual preferences dialog, not the preferences class, seems like a good idea

import os

from PyQt6 import QtCore
from PyQt6.QtCore import QSettings, pyqtSignal, QSize, QPoint, QObject, QUrl
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QCheckBox, QPushButton, QComboBox, QApplication, QSpinBox
from PyQt6.uic import loadUi

from mammudon.debugging import debug
from mammudon.format_post import format_post


class PreferencesDialog(QDialog):
	applied = pyqtSignal()

	def __init__(self, parent=None):
		super().__init__(parent)

		self.dirty = False

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "preferences.ui"), self)

		self.ok_button: QPushButton = self.findChild(QPushButton, "okButton")
		self.apply_button: QPushButton = self.findChild(QPushButton, "applyButton")
		self.cancel_button: QPushButton = self.findChild(QPushButton, "cancelButton")

		self.ok_button.clicked.connect(self.accept)
		self.apply_button.clicked.connect(self.apply)
		self.cancel_button.clicked.connect(self.reject)

	def __del__(self):
		debug("__del__eting PreferencesDialog")

	def apply(self, _checked: bool) -> None:
		self.applied.emit()

	def set_dirty(self, dirty: bool) -> None:
		self.dirty = dirty

	# TODO: record the dirty flag and ask on close if dirty
	def closeEvent(self, e: QCloseEvent) -> None:
		self.rejected.emit()
		e.accept()


class Preferences(QObject):
	def __init__(self):
		super().__init__()

		self.preferences_dialog: PreferencesDialog | None = None
		self.app: QApplication | None = None

		self.values = {}

	def __del__(self):
		debug("__del__eting Preferences")

	def show_dialog(self) -> None:
		if self.preferences_dialog:
			self.preferences_dialog.activateWindow()
			return

		self.preferences_dialog = PreferencesDialog()

		self.preferences_dialog.accepted.connect(self.on_ok)
		self.preferences_dialog.applied.connect(self.on_apply)
		self.preferences_dialog.rejected.connect(self.on_cancel)

		self.feature_set_combo: QComboBox = self.preferences_dialog.findChild(QComboBox, "featureSetCombo")
		self.max_timeline_length_spinner: QSpinBox = self.preferences_dialog.findChild(QSpinBox, "maxTimelineLengthSpinner")
		self.expand_spoilers_check: QCheckBox = self.preferences_dialog.findChild(QCheckBox, "expandSpoilersCheck")
		self.show_media_combo: QComboBox = self.preferences_dialog.findChild(QComboBox, "showMediaCombo")
		self.theme_combo: QComboBox = self.preferences_dialog.findChild(QComboBox, "themeCombo")
		self.layout_combo: QComboBox = self.preferences_dialog.findChild(QComboBox, "layoutCombo")
		self.minimize_to_tray_check: QCheckBox = self.preferences_dialog.findChild(QCheckBox, "minimizeToTrayCheck")

		self.post_preview: QWebEngineView = self.preferences_dialog.findChild(QWebEngineView, "postPreview")

		# since Designer doesn't let us define user data per combo item, we do it
		# ourselves by splitting the text at the ":"
		num_items: int = self.show_media_combo.count()
		for item in range(num_items):
			text: str = self.show_media_combo.itemText(item)
			self.show_media_combo.setItemText(item, text.split(":")[0])
			self.show_media_combo.setItemData(item, text.split(":")[1])

		# TODO: Scan themes folder for themes, read theme.txt
		# since Designer doesn't let us define user data per combo item, we do it
		# ourselves by splitting the text at the ":"
		num_items: int = self.theme_combo.count()
		for item in range(num_items):
			text: str = self.theme_combo.itemText(item)
			self.theme_combo.setItemText(item, text.split(":")[0])
			self.theme_combo.setItemData(item, text.split(":")[1])

		# TODO: Scan layouts folder for layouts, read layout.txt
		# since Designer doesn't let us define user data per combo item, we do it
		# ourselves by splitting the text at the ":"
		num_items: int = self.layout_combo.count()
		for item in range(num_items):
			text: str = self.layout_combo.itemText(item)
			self.layout_combo.setItemText(item, text.split(":")[0])
			self.layout_combo.setItemData(item, text.split(":")[1])

		# since Designer doesn't let us define user data per combo item, we do it
		# ourselves by using the lower case of the name
		num_items = self.feature_set_combo.count()
		for item in range(num_items):
			self.feature_set_combo.setItemData(item, self.feature_set_combo.itemText(item).lower())

		self.post_preview.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
		page: QWebEnginePage = self.post_preview.page()

		# allow QWebEnginePage to load local image files from "file:" URLs, needs BaseUrl being set in setHtml()
		page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

		self.feature_set_combo.currentIndexChanged.connect(self.set_dirty)
		self.max_timeline_length_spinner.valueChanged.connect(self.set_dirty)
		self.expand_spoilers_check.stateChanged.connect(self.set_dirty)
		self.show_media_combo.currentIndexChanged.connect(self.set_dirty)
		self.theme_combo.currentIndexChanged.connect(self.set_dirty)
		self.layout_combo.currentIndexChanged.connect(self.set_dirty)
		self.minimize_to_tray_check.stateChanged.connect(self.set_dirty)

		self.update_ui()
		self.update_preview()

		self.preferences_dialog.set_dirty(False)

		settings = QSettings()
		settings.beginGroup("PreferencesDialog")
		self.preferences_dialog.resize(QSize(settings.value("size", QSize(1024, 768))))
		self.preferences_dialog.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		self.preferences_dialog.show()

	def set_dirty(self, *_args) -> None:
		self.preferences_dialog.set_dirty(True)

		o: QObject = self.sender()

		if o is self.feature_set_combo:
			o: QComboBox
			self.values["feature_set"] = str(o.currentData())

		elif o is self.max_timeline_length_spinner:
			o: QSpinBox
			self.values["max_timeline_length"] = o.value()

		elif o is self.expand_spoilers_check:
			o: QCheckBox
			self.values["expand_spoilers"] = bool(o.checkState() == QtCore.Qt.CheckState.Checked)

		elif o is self.show_media_combo:
			o: QComboBox
			self.values["show_media_policy"] = str(o.currentData())

		elif o is self.theme_combo:
			o: QComboBox
			self.values["theme"] = str(o.currentData())

		elif o is self.layout_combo:
			o: QComboBox
			self.values["layout"] = str(o.currentData())

		# TODO: actually add/remove the systray icon at runtime
		elif o is self.minimize_to_tray_check:
			o: QCheckBox
			self.values["minimize_to_tray"] = bool(o.checkState() == QtCore.Qt.CheckState.Checked)
			# TODO: check if this does what I think it does
			self.app.setQuitOnLastWindowClosed(not preferences.values["minimize_to_tray"])

		self.update_preview()

	def update_ui(self) -> None:
		self.feature_set_combo.setCurrentIndex(self.feature_set_combo.findData(self.values["feature_set"]))
		self.expand_spoilers_check.setChecked(self.values["expand_spoilers"])
		self.max_timeline_length_spinner.setValue(self.values["max_timeline_length"])
		self.show_media_combo.setCurrentIndex(self.show_media_combo.findData(self.values["show_media_policy"]))
		self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.values["theme"]))
		self.layout_combo.setCurrentIndex(self.layout_combo.findData(self.values["layout"]))
		self.minimize_to_tray_check.setChecked(self.values["minimize_to_tray"])

	def load_settings(self) -> None:
		settings = QSettings()
		settings.beginGroup("Preferences")

		# TODO: could probably be a dict at some point, might make saving/loading easier, but it has
		#       the issue of data types not really translating well to QSettings and back.

		# default for new accounts
		self.values["feature_set"]: str = settings.value("feature_set", "mainline")  # mainline, fedibird, pleroma
		self.values["max_timeline_length"]: int = int(settings.value("max_timeline_length", 50))
		self.values["expand_spoilers"]: bool = bool(int(settings.value("expand_spoilers", True)))  # why on earth does bool() by itself not suffice?
		self.values["show_media_policy"]: str = settings.value("show_media_policy", "show")
		self.values["theme"]: str = settings.value("theme", "light")
		self.values["layout"]: str = settings.value("layout", "default")
		self.values["minimize_to_tray"]: bool = bool(int(settings.value("minimize_to_tray", True)))  # why on earth does bool() by itself not suffice?

		self.values["preferred_post_language"]: str = settings.value("preferred_post_language", "en")
		self.values["preferred_post_visibility"]: str = settings.value("preferred_post_visibility", "public")

		settings.endGroup()

		settings.beginGroup("UI")

		# tried .setSizes() with height calculation etc. but it didn't work,
		# so just apply a previously determined saveState() that approximately
		# sets the top box at 1/3, the bottom at 2/3
		self.values["history_splitter_pos"]: bytes = settings.value("history_splitter_pos", b'\x00\x00\x00\xff\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\xbc\x00\x00\x01W\x00\xff\xff\xff\xff\x01\x00\x00\x00\x02\x00')

		settings.endGroup()

	def save_settings(self) -> None:
		settings = QSettings()
		settings.beginGroup("Preferences")

		settings.setValue("feature_set", self.values["feature_set"])
		settings.setValue("max_timeline_length", self.values["max_timeline_length"])
		settings.setValue("expand_spoilers", int(self.values["expand_spoilers"]))
		settings.setValue("show_media_policy", self.values["show_media_policy"])
		settings.setValue("theme", self.values["theme"])
		settings.setValue("layout", self.values["layout"])
		settings.setValue("minimize_to_tray", int(self.values["minimize_to_tray"]))

		settings.setValue("preferred_post_language", self.values["preferred_post_language"])
		settings.setValue("preferred_post_visibility", self.values["preferred_post_visibility"])

		settings.endGroup()

		settings.beginGroup("UI")
		settings.setValue("history_splitter_pos", self.values["history_splitter_pos"])
		settings.endGroup()

	def on_ok(self) -> None:
		self.on_apply()
		self.close_dialog(self.preferences_dialog)

	def on_apply(self) -> None:
		self.save_settings()

	def on_cancel(self) -> None:
		self.load_settings()
		self.close_dialog(self.preferences_dialog)

	def close_dialog(self, _dialog: QDialog) -> None:
		settings = QSettings()
		settings.beginGroup("PreferencesDialog")
		settings.setValue("size", self.preferences_dialog.size())
		settings.setValue("pos", self.preferences_dialog.pos())
		settings.endGroup()

		self.preferences_dialog = None

	def update_preview(self) -> None:
		demo_status: dict
		demo_boosted_by: dict

		with open(os.path.join(os.path.dirname(__file__), "res", "demo_status.dict"), 'r') as file:
			demo_status = eval(file.read())

		with open(os.path.join(os.path.dirname(__file__), "res", "demo_boosted_by.dict"), 'r') as file:
			demo_boosted_by = eval(file.read())

		html = format_post(self.values, demo_status, demo_boosted_by, [])

		# make sure the preview doesn't allow clicking of links
		html = html.replace(" href=", " off=")
		self.post_preview.setHtml(html, QUrl('file:///' + os.path.dirname(__file__)))

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False


# offer global "preferences" to all other modules
preferences: Preferences = Preferences()
