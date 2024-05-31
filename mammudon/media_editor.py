import os

from PyQt6 import QtCore
from PyQt6.QtCore import QPoint, QObject, QEvent
from PyQt6.uic import loadUi

from PyQt6.QtGui import QPixmap, QResizeEvent, QMouseEvent
from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QLabel, QWidget

from mammudon.media_attachment import MediaAttachment


class MediaEditor(QDialog):
	def __init__(self, parent: QWidget, media: MediaAttachment):
		super().__init__(parent)

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "edit_media_attachment.ui"), self)

		self.media: MediaAttachment = media

		self.description_edit: QPlainTextEdit = self.findChild(QPlainTextEdit, "descriptionEdit")
		self.description_edit.setPlainText(self.media.description())

		# TODO: not all media are images

		self.media_canvas: QWidget = self.findChild(QWidget, "mediaCanvas")
		self.media_label: QLabel = self.findChild(QLabel, "mediaLabel")
		self.focus_label: QLabel = self.findChild(QLabel, "focusLabel")

		self.media_label.setPixmap(QPixmap.fromImage(media.media_preview))

		self.media_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
		self.focus_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

		self.findChild(QPushButton, "applyButton").clicked.connect(self.apply_changes)
		self.findChild(QPushButton, "cancelButton").clicked.connect(self.discard_changes)

		self.media_canvas.installEventFilter(self)

		self.dragging_focus: bool = False

		# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
		# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
		self.focus_pos: tuple[float, float] = (0.5, 0.5)
		self.set_focus_point_normalized(self.media.focus_point())

	def resizeEvent(self, e: QResizeEvent):
		self.media_label.setFixedSize(self.media_canvas.geometry().size())
		self.media_label.move(QPoint(0, 0))
		self.set_focus_point_normalized(self.focus_pos)

	# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
	# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
	def set_focus_point_normalized(self, focus: tuple[float, float]):
		focus_x: float = focus[0] * float(self.media_canvas.size().width())
		focus_y: float = focus[1] * float(self.media_canvas.size().height())

		self.set_focus_point(int(focus_x), int(focus_y))
		self.focus_pos = focus

	def set_focus_point(self, x_pos: int, y_pos: int):
		focus_width: int = self.focus_label.width()
		focus_height: int = self.focus_label.height()
		self.focus_label.move(QPoint(x_pos - focus_width // 2, y_pos - focus_height // 2))

		# focus is a tuple[float, float] in the range of 0.0..1.0 - remember that
		# mastodon media uses -1.0..1.0 so, it needs to be recalculated on upload
		focus_x: float = float(x_pos) / float(self.media_canvas.geometry().size().width())
		focus_y: float = float(y_pos) / float(self.media_canvas.geometry().size().height())
		self.focus_pos = (focus_x, focus_y)

	def eventFilter(self, o: QObject, e: QEvent) -> bool:
		if o is not self.media_canvas:
			return False

		if e.type() == QtCore.QEvent.Type.MouseButtonPress:
			self.dragging_focus = True
		elif e.type() == QtCore.QEvent.Type.MouseButtonRelease:
			self.dragging_focus = False
			return False
		elif e.type() != QtCore.QEvent.Type.MouseMove:
			return False

		if self.dragging_focus:
			e: QMouseEvent
			self.set_focus_point(e.pos().x(), e.pos().y())

		return False

	def apply_changes(self) -> None:
		self.media.set_focus_point(self.focus_pos)
		self.media.set_description(self.description_edit.toPlainText())
		self.discard_changes()

	def discard_changes(self) -> None:
		self.rejected.emit()
		self.media = None
		self.close()

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
