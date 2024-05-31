import os

from PyQt6 import QtCore

from PyQt6.uic import loadUi

from PyQt6.QtCore import pyqtSignal

from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QPushButton

from mammudon.debugging import debug


# this class does not hold the actual media data, only a preview image
class MediaAttachment(QLabel):
	# signals
	edit_requested = pyqtSignal()
	remove_requested = pyqtSignal()

	def __init__(self):
		super().__init__()

		# pre-declare attributes that are set in the functions below
		self.media_file_name = ""
		self.media_description = ""
		self.media_preview: QImage | None = None

		# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
		# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
		self.focus: tuple[float, float] = (0.5, 0.5)

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "media_attachment.ui"), self)

		self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

		self.findChild(QPushButton, "editButton").clicked.connect(self.edit)
		self.findChild(QPushButton, "deleteButton").clicked.connect(self.remove)

		self.description_label = self.findChild(QLabel, "descriptionLabel")

		self.set_media("", QImage())
		self.set_description("")

	def __del__(self):
		debug("__del__eting media attachment", self.media_file_name)

	def description(self) -> str:
		return self.media_description

	def set_description(self, desc: str) -> None:
		self.media_description = desc
		if desc:
			if len(desc) > 50:
				desc = desc[:46] + " ..."
			self.description_label.setText(desc)
			self.description_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
		else:
			self.description_label.setText("* No Description Added *")
			self.description_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

	def file_name(self) -> str:
		return self.media_file_name

	def set_media(self, file_name: str, preview: QImage) -> None:
		self.media_preview: QImage = preview
		self.media_file_name = file_name
		self.setPixmap(QPixmap.fromImage(self.media_preview))
		self.setToolTip(self.media_file_name)

	# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
	# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
	def set_focus_point(self, focus: tuple[float, float]) -> None:
		self.focus = focus

	# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
	# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
	def focus_point(self) -> tuple[float, float]:
		return self.focus

	def edit(self) -> None:
		self.edit_requested.emit()

	def remove(self) -> None:
		self.remove_requested.emit()

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
