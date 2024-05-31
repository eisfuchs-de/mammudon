# TODO: show which account you are replying to, not just the text
# TODO: create M icon with "new_post.png" on top - can be set in Designer
# TODO: show maximum post length and current length:
# 		max_characters = instance.get("configuration", {}).get("statuses", {}).get("max_characters", 500)

import os

import ffmpeg

from datetime import datetime, timedelta

from PyQt6.uic import loadUi

from PyQt6 import QtCore

from PyQt6.QtCore import pyqtSignal, QMimeDatabase, QSettings, QPoint, QSize, QDateTime, QMimeType

from PyQt6.QtGui import QIcon, QImage, QTextCursor, QCloseEvent

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDateTimeEdit, QFileDialog, QGridLayout, QLineEdit, QMessageBox, \
	QPlainTextEdit, QPushButton, QTextEdit, QWidget, QLabel

from mammudon.account import Account
from mammudon.debugging import debug
from mammudon.prefs import preferences

from mammudon.html_to_text import HtmlToText
from mammudon.languages import Languages
from mammudon.media_attachment import MediaAttachment
from mammudon.media_editor import MediaEditor


class NewPost(QWidget):

	publish = pyqtSignal(QWidget)
	cancel = pyqtSignal(QWidget)

	def __init__(self, parent, account: Account, reply_to_post: dict = None):  # parent: MainWindow - gives import error >.<
		super().__init__()

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "new_post.ui"), self)

		settings = QSettings()

		settings.beginGroup("NewPostWindow")
		self.resize(QSize(settings.value("size", QSize(362, 560))))
		self.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		self.spoiler_text_edit = self.findChild(QLineEdit, "spoilerText")

		self.in_reply_to_text: QPlainTextEdit = self.findChild(QPlainTextEdit, "inReplyToText")
		self.post_edit: QTextEdit = self.findChild(QTextEdit, "postEdit")
		self.attach_button: QPushButton = self.findChild(QPushButton, "attachBtn")
		self.media_grid: QGridLayout = self.findChild(QGridLayout, "mediaGridBox")
		self.language_combo: QComboBox = self.findChild(QComboBox, "languageCombo")
		self.visibility_combo: QComboBox = self.findChild(QComboBox, "visibilityCombo")
		self.content_type_combo: QComboBox = self.findChild(QComboBox, "contentTypeCombo")
		self.sensitive_checkbox: QCheckBox = self.findChild(QCheckBox, "sensitiveCheckBox")
		self.scheduled_button: QPushButton = self.findChild(QPushButton, "scheduledBtn")
		self.publish_button: QPushButton = self.findChild(QPushButton, "publishBtn")
		self.cancel_button: QPushButton = self.findChild(QPushButton, "cancelBtn")
		self.username_label: QLabel = self.findChild(QLabel, "usernameLabel")

		self.content_type_combo.setVisible(preferences.values["feature_set"] == "pleroma")

		self.attach_button.clicked.connect(self.attach_media)
		self.scheduled_button.toggled.connect(self.schedule)
		self.publish_button.clicked.connect(self.publish_clicked)
		self.cancel_button.clicked.connect(self.cancel_clicked)

		self.account = account
		self.account.is_composing_post = self

		self.attachments: list[MediaAttachment] = []
		self.media_editor: MediaEditor | None = None
		self.scheduled_datetime: QDateTime | None = None
		self.calendar: QDateTimeEdit | None = None

		self.media_upload_errors = ""

		self.username_label.setText(self.account.account_username)
		self.layout_media()

		# TODO: use calculated maximum width
		self.language_combo.view().setFixedWidth(300)

		# TODO: put this into its own file/module/class
		visibilities = {
			"public":   ["Public",         "visibility_public.png"],
			"unlisted": ["Unlisted",       "visibility_unlisted.png"],
			"private":  ["Followers Only", "visibility_private.png"],
			"direct":   ["Only Mentioned", "visibility_direct.png"],
		}

		# fill visibility combo box with icons and list of visibility names
		current_index = 0
		vis: str
		names: list[str]
		for vis, names in visibilities.items():
			# TODO: calculate maximum width
			self.visibility_combo.addItem(
				QIcon(
					os.path.join(os.path.dirname(__file__), "icons", names[1])
				), names[0], vis
			)

			if vis == preferences.values["preferred_post_visibility"]:
				self.visibility_combo.setCurrentIndex(current_index)

			current_index += 1

		# TODO: use calculated maximum width
		self.visibility_combo.view().setFixedWidth(150)

		# doesn't seem to be listed in the mastodon.py documentation, but my instance returns this
		mime_type: str
		for mime_type in self.account.instance.get(
				"configuration", {}).get("statuses", {}).get("supported_mime_types", ["text/plain"]):
			self.content_type_combo.addItem(mime_type)

		# set up reply ID and replied post text if applicable
		# TODO: use status_reply() to auto retain all mentions, or roll our own
		self.in_reply_to_id = None
		if reply_to_post:
			parser = HtmlToText()
			parser.feed(reply_to_post["content"])
			parser.close()

			self.in_reply_to_id = reply_to_post["id"]
			self.in_reply_to_text.setPlainText(parser.text)
			self.in_reply_to_text.setVisible(True)
			self.visibility_combo.setCurrentText(visibilities[reply_to_post["visibility"]][0])

			if reply_to_post["spoiler_text"]:
				self.spoiler_text_edit.setText("re: " + reply_to_post["spoiler_text"])

			mentions: list[str] = ["@" + reply_to_post["account"]["acct"]]
			mention: dict
			for mention in reply_to_post["mentions"]:
				mentions.append("@" + mention["acct"])
			self.post_edit.setText(" ".join(mentions) + " ")
		else:
			self.in_reply_to_text.setVisible(False)

		self.post_edit.setFocus()
		self.post_edit.moveCursor(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.MoveAnchor)

		# fill languages combo box with list of supported languages and codes
		current_index = 0
		lang: str
		names: list[str]
		for lang, names in Languages.language_list.items():
			# TODO: calculate maximum width
			self.language_combo.addItem(lang + " - " + names[1] + " (" + names[0] + ")", lang)

			if lang == preferences.values["preferred_post_language"]:
				self.language_combo.setCurrentIndex(current_index)

			current_index += 1

		# TODO: this should really be done by the parent itself and use a closed signal
		# mark new post widget as being displayed in main window
		parent.new_post_popup = None

	def __del__(self):
		debug("__del__eting NewPost for", self.account.account_username)

	def get_post(self) -> dict:

		self.enable_publish(False)

		published_post = {
			"content": self.post_edit.toPlainText(),
			"in_reply_to_id": self.in_reply_to_id,
			"media_files": self.attachments,
			"sensitive": self.sensitive_checkbox.isChecked(),

			# The visibility parameter is a string value and accepts any of:
			# - ‘direct’   - post will be visible only to mentioned users
			# - ‘private’  - post will be visible only to followers
			# - ‘unlisted’ - post will be public but not appear on the public timeline
			# - ‘public’   - post will be public
			"visibility": self.visibility_combo.currentData(),
			"spoiler_text": self.spoiler_text_edit.text(),
			"language": self.language_combo.currentData(),  # None, "de", "it" ...
			"idempotency_key": None,  # TODO: if you use the same key for multiple publish attempts, only one status will be created
			# for "pleroma" - ‘text/plain’ (default), ‘text/markdown’, ‘text/html’ and ‘text/bbcode’
			"content_type": self.content_type_combo.currentText(),
		}

		if self.scheduled_button.isChecked():
			published_post["scheduled_at"] = self.scheduled_datetime  # at least 5 minutes in the future
		else:
			published_post["scheduled_at"] = None

		published_post["poll"] = None      # TODO: use make_poll()
		published_post["quote_id"] = None  # TODO: for "fedibird" - quoted post id

		return published_post

	def publish_clicked(self) -> None:
		preferences.preferred_post_visibility = self.visibility_combo.currentData()
		preferences.preferred_post_language = self.language_combo.currentData()
		self.publish.emit(self)

	def cancel_clicked(self) -> None:
		self.cancel.emit(self)

	def closeEvent(self, e: QCloseEvent) -> None:
		preferences.last_post_language = self.language_combo.currentData()
		preferences.last_post_visibility = self.visibility_combo.currentData()

		self.cancel.emit(self)

		settings = QSettings()

		settings.beginGroup("NewPostWindow")
		settings.setValue("size", self.size())
		settings.setValue("pos", self.pos())
		settings.endGroup()

		self.account.is_composing_post = None

		e.accept()

	def layout_media(self) -> None:
		while self.media_grid.count():
			# we don't keep a pointer to the QLayoutItem, so it should self-delete, right?
			self.media_grid.takeAt(0)

		num_media = len(self.attachments)

		# we could do some sophisticated placement here, but as we only have 4 slots,
		# this is so much easier to read
		if num_media == 1:
			self.media_grid.addWidget(self.attachments[0], 0, 0, 1, 1)
		elif num_media == 2:
			self.media_grid.addWidget(self.attachments[0], 0, 0, 1, 1)
			self.media_grid.addWidget(self.attachments[1], 0, 1, 1, 1)
		elif num_media == 3:
			self.media_grid.addWidget(self.attachments[0], 0, 0, 1, 1)
			self.media_grid.addWidget(self.attachments[1], 0, 1, 1, 1)
			self.media_grid.addWidget(self.attachments[2], 1, 0, 1, 2)
		elif num_media == 4:
			self.media_grid.addWidget(self.attachments[0], 0, 0, 1, 1)
			self.media_grid.addWidget(self.attachments[1], 0, 1, 1, 1)
			self.media_grid.addWidget(self.attachments[2], 1, 0, 1, 1)
			self.media_grid.addWidget(self.attachments[3], 1, 1, 1, 1)

		self.attach_button.setEnabled(num_media != 4)
		self.sensitive_checkbox.setVisible(num_media != 0)

	def edit_media(self) -> None:
		media: MediaAttachment | None = self.sender()
		self.media_editor = MediaEditor(self, media)
		self.media_editor.rejected.connect(self.on_edit_media_closed)
		self.media_editor.show()

	def on_edit_media_closed(self) -> None:
		self.media_editor = None

	def remove_media(self) -> None:
		media: MediaAttachment | None = self.sender()

		attachment_index = self.attachments.index(media)

		self.attachments.remove(media)
		self.media_grid.removeWidget(media)

		# swap some items after deleting so the result looks less confusing
		if len(self.attachments) == 2:
			if attachment_index == 0:
				self.attachments[0], self.attachments[1] = self.attachments[1], self.attachments[0]
		elif len(self.attachments) == 3:
			if attachment_index == 0:
				self.attachments[0], self.attachments[1] = self.attachments[1], self.attachments[0]
			elif attachment_index == 1:
				self.attachments[1], self.attachments[2] = self.attachments[2], self.attachments[1]

		self.layout_media()

	def attach_media(self) -> None:
		# button should be disabled, but an extra check doesn't hurt
		if len(self.attachments) == 4:
			return

		file_name: str
		chosen_filter: str
		file_name, chosen_filter = QFileDialog.getOpenFileName(
			self,
			"Choose Media File",
			"",
			"All Supported File Types (*.png *.jpeg *.jpg *.gif *.webp *.bmp *.mp4 *.gifv *.wav *.mp3 *.ogg *.flac *.aac);;" +
			"Images (*.png *.jpeg *.jpg *.gif *.webp *.bmp);;" +
			"Videos (*.mp4);;" +
			"GIFV Files (*.gifv);;" +
			"Audio Files (*.wav *.mp3 *.ogg *.flac *.aac)"
		)

		if not file_name:
			return

		debug(file_name)

		db = QMimeDatabase()
		mime: QMimeType = db.mimeTypeForFile(file_name, QMimeDatabase.MatchMode.MatchContent)
		debug(mime.name())             # mimetype: "audio/mpeg"
		debug(mime.suffixes())         # suffixes: ["mp3", "mpga"]
		debug(mime.preferredSuffix())  # preferred suffix: "mp3"

		new_image: QImage

		if mime.name().startswith("audio/"):
			new_image = QImage(os.path.join(os.path.dirname(__file__), "images", "image_audio.png"))
		else:
			# try using the file as an image, 
			new_image = QImage(file_name)

		# not working as an image, try loading it as a video
		if new_image.isNull():
			# declare everything local so it will get discarded automatically

			# NOTE: needs gstreamer-plugins-libav (and gstreamer-plugins-vaapi?) to work with h264
			#       also: qt6-multimedia

			out, _ = (
				ffmpeg.input(file_name).output(
					'pipe:', vframes=1, format='image2', vcodec='mjpeg'
				).run(capture_stdout=True)
			)

			new_image = QImage()
			new_image.loadFromData(out, "image/jpg")

		# type hint, it will be set in one of the if-blocks later
		preview: QImage

		if new_image:
			image_width = new_image.size().width()
			image_height = new_image.size().height()

			new_width = 320
			new_height = 180

			if image_width / image_height < new_width / new_height:
				new_width = new_height * image_width // image_height
			else:
				new_height = new_width * image_height // image_width

			# not sure if we need to do this speed-saving thing, but it's not hard to keep it in
			if image_width * image_height > (800 * 600):
				preview = new_image.scaled(800, 600).scaled(new_width, new_height, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
			else:
				preview = new_image.scaled(new_width, new_height, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
		else:
			# still not working? we get no preview
			# TODO: normal for non-images, we should provide something for audio
			preview = QImage(os.path.join(os.path.dirname(__file__), "images", "images_media.png"))
			QMessageBox.information(self, "Mammudon", f"Could not load media preview:\n{file_name}.")

		new_media = MediaAttachment()
		new_media.set_media(file_name, preview)

		self.attachments.append(new_media)
		self.layout_media()

		new_media.edit_requested.connect(self.edit_media)
		new_media.remove_requested.connect(self.remove_media)

	def media_uploaded(self, name, success, message="") -> None:
		# TODO: mark media with a checkmark/error box or something
		debug("media upload successful?", name, success)
		if not success:
			self.media_upload_errors += name + ": " + message + "\n"

	def enable_publish(self, enabled: bool) -> None:
		self.publish_button.setEnabled(enabled)
		if self.media_upload_errors:
			QMessageBox.information(self, "Mammudon - Media upload error:", self.media_upload_errors)
			self.media_upload_errors = ""

	def schedule(self, checked: bool):
		if checked:
			self.calendar = QDateTimeEdit()
			self.calendar.setCalendarPopup(True)
			self.calendar.setMinimumDateTime(datetime.now() + timedelta(minutes=5))
			self.calendar.setDisplayFormat("ddd dd MMMM yyyy - HH:mm:ss ")
			self.calendar.dateTimeChanged.connect(self.scheduled_time)

			if not self.scheduled_datetime:
				self.calendar.setDateTime(datetime.now() + timedelta(minutes=15))
			else:
				self.calendar.setDateTime(self.scheduled_datetime)

			self.calendar.show()
		else:
			self.calendar = None
			self.publish_button.setText("Publish")

	def scheduled_time(self, scheduled_datetime: QDateTime) -> None:
		self.scheduled_datetime = scheduled_datetime.toPyDateTime()
		self.publish_button.setText("Schedule")
		debug(scheduled_datetime)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
