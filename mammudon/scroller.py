# TODO: The naming of "Scroller" and "Timeline" classes appears to be a bit confusing

import os

from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, QEvent
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QWidget, QPushButton, QScrollArea, QLabel, QVBoxLayout
from PyQt6.uic import loadUi
from mastodon import Mastodon

from mammudon.account import Account
from mammudon.listener import Listener


class Scroller(QWidget):

	current_account = pyqtSignal(Account)  # fires on mouse entry
	open_profile = pyqtSignal(object)  # account_id: int as object because 64bit
	reply_to_post = pyqtSignal(object, bool)  # dict with the post to reply to inside
	close_scroller = pyqtSignal(QWidget, int)  # int - num unread posts
	minimized = pyqtSignal()
	unread_changed = pyqtSignal(bool)

	def __init__(self, *, name: str, friendly_name: str, account: Account):
		super().__init__()

		self.scroller_name = name
		self.friendly_name = friendly_name + " (" + account.account_username + ")"
		self.account = account

		# TODO: needs to be renamed to scroller.ui
		loadUi(os.path.join(os.path.dirname(__file__), "ui", "timeline.ui"), self)

		self.timeline_icon_widget: QWidget = self.findChild(QWidget, "timelineIconWidget")
		self.unread_label: QLabel = self.findChild(QLabel, "unreadLabel")
		self.reload_button: QPushButton = self.findChild(QPushButton, "timelineReloadBtn")
		self.scroll_area: QScrollArea = self.findChild(QScrollArea, "timelineScrollArea")
		self.label: QLabel = self.findChild(QLabel, "accountLabel")
		self.close_button: QPushButton = self.findChild(QPushButton, "closeBtn")

		self.label.setText(self.account.account_username)

		# TODO: currently duplicated in MainWindow()
		# TODO: add comprehensive description to show on tooltip(s)
		self.preset_timelines = {
			"home": "Home",
			"notifications": "Notifications",
			"local": "Local",
			"public": "Federated",
			"conversations": "Conversations",
			"favorites": "Favorites",
			"bookmarks": "Bookmarks",
		}

		self.account: Account = account
		self.mastodon: Mastodon = account.mastodon    # convenience
		self.my_id: int = account.account["id"]  # convenience

		if self.scroller_name in self.preset_timelines:
			# this is a bit convoluted because background-image does not work on QWidget, and we
			# apparently also need the absolute path to the image for the style sheet to work
			file_path = os.path.abspath(__file__)
			icon_path = os.path.join(os.path.abspath(os.path.dirname(file_path)), "icons", "timeline_" + self.scroller_name + ".png")
			style_sheet = "border-image: url(" + icon_path + ") 0 0 0 0 stretch stretch;"
			self.timeline_icon_widget.setStyleSheet(style_sheet)
		else:
			self.unread_label.setText(self.preset_timelines[self.scroller_name])

		# connect signals
		self.timeline_view: QWidget = self.scroll_area.widget()

		# self.timeline_view.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.MinimumExpanding) # DO NOT DO THIS , it expands ALL POSTS vertically
		self.timeline_view.setLayout(QVBoxLayout(self.timeline_view))
		self.timeline_view.layout().setContentsMargins(0, 0, 0, 0)

		self.unread_count = 0
		self.unread_label.setVisible(False)
		self.unread_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

	def on_post_unread_changed(self, unread: bool) -> None:
		if unread:
			self.unread_count += 1
		else:
			self.unread_count -= 1

		# TODO: find a way to do this with stylesheets that adapt automatically
		label = str(self.unread_count)
		self.unread_label.setText(label)
		self.unread_label.setVisible(bool(self.unread_count))
		self.unread_label.setFixedWidth(len(label) * 6 + 8)
		self.timeline_icon_widget.layout().setContentsMargins(31 - len(label) * 6 - 8, 20, 0, 0)
		self.unread_changed.emit(unread)

	def on_close_button_clicked(self) -> None:
		self.close_scroller.emit(self, self.unread_count)

	def scroll_event(self, e: QWheelEvent) -> None:
		# debug("scroll!", e)
		self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - e.pixelDelta().y())

	def event(self, e: QEvent) -> bool:
		# TODO: check if we need any other events to switch the current account
		if e.type() in [
			# QEvent.Type.MouseButtonPress,
			# QEvent.Type.MouseButtonRelease,
			# QEvent.Type.MouseButtonDblClick,
			# QEvent.Type.Wheel,
			# QEvent.Type.KeyPress,
			# QEvent.Type.KeyRelease,
			# QEvent.Type.Scroll,
			QEvent.Type.Enter
		]:
			self.current_account.emit(self.account)

		return super().event(e)

	# slot
	def application_minimized(self) -> None:
		self.minimized.emit()

	# needs to be re-implemented by the superclass to connect to its needed Listener signal
	def connect_to_stream_listener(self, stream_name: str, stream_listener: Listener):
		pass

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
