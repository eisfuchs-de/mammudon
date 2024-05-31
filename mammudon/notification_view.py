import os

from PyQt6 import QtCore
from PyQt6.QtCore import QUrl, pyqtSignal, QObject, QEvent, QChildEvent, QSizeF
from PyQt6.QtGui import QAction, QContextMenuEvent
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QMenu, QApplication, QLabel
from PyQt6.uic import loadUi

from mammudon.debugging import debug


# TODO: Why do we need a subclass for this to make installEventFilter work?
class NotificationPage(QWebEnginePage):

	def __init__(self, parent):
		super(QWebEnginePage, self).__init__(parent)


class NotificationView(QWidget):

	mouse_wheel_event = pyqtSignal(object)  # QEvent with type() == Wheel

	def __init__(self, *, notification_id: int):
		super().__init__()

		self.id = notification_id

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "notification_view.ui"), self)

		self.web_view: QWebEngineView = self.findChild(QWebEngineView, "notificationView")
		self.timestamp_label: QLabel = self.findChild(QLabel, "timestampLabel")

		# DEBUG: create debug action to be able to copy the raw post or HTML source to the clipboard
		self.debug_action_copy_html: QAction = self.findChild(QAction, "debugCopyHtml")
		self.debug_action_copy_raw: QAction = self.findChild(QAction, "debugCopyRaw")

		# original post before changing the HTML or anything else
		self.original_post = {}

		# post html code before it got to the QWebEnginePage widget - good for edited comparison
		self.post_html = ""

		# TODO: Why do we need a subclass for this to make installEventFilter work?
		self.web_page: NotificationPage = NotificationPage(self)
		self.web_view.setPage(self.web_page)

		self.web_view.installEventFilter(self)

		# make QWebEngineView too small initially so it resizes properly
		# TODO: Check if this is still needed
		# self.web_view.setMinimumHeight(48)
		# self.web_view.setMinimumWidth(48)

		# allow QWebEnginePage to load local image files from "file:" URLs, needs BaseUrl being set in setHtml()
		self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
		self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

		# this works well for initial sizing
		self.web_page.loadFinished.connect(self.post_load_finished)

		# create resize signal connection, just to make resizing look a bit smoother
		self.web_page.contentsSizeChanged.connect(self.on_contents_size_changed)

		self.debug_action_copy_html.triggered.connect(self.copy_html_to_clipboard)
		self.debug_action_copy_raw.triggered.connect(self.copy_raw_to_clipboard)
		self.web_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
		self.menus: QMenu | None = None

		self.height_bias = self.size().height() - self.web_view.size().height()
		debug(self.height_bias)

	# pass on QWebEngineView events to us, like mouse clicks and ChildAdded events
	def eventFilter(self, o: QObject, e: QEvent) -> bool:
		# debug("event filter")
		if e.type() == QEvent.Type.Wheel:
			# debug("event filter wheel")
			self.mouse_wheel_event.emit(e)
			# do not pass on this event, we don't want anything scrolling by itself
			return True

		# TODO: not needed yet, but probably will be once this class gets fleshed out
		# if e.type() == QEvent.Type.MouseButtonPress:
		# 	e: QMouseEvent
		# 	self.handle_mouse_click(e)
		#
		# 	# pass on this event for drag-selecting, link clicking, profile picture click etc.
		# 	return False

		# install the event filter also on child views that get added to the object
		if e.type() == QEvent.Type.ChildAdded:
			e: QChildEvent
			e.child().installEventFilter(self)

			# ChildAdded seems to fire when we unfold or fold the "Show More" spoiler,
			# so we can use that to adjust the QWebEngineView's height
			if self.web_page:
				if not self.web_page.isLoading():
					self.run_size_check()

			# pass on this event, maybe some other part needs it
			return False

		if e.type() == QEvent.Type.ContextMenu:
			e: QContextMenuEvent

			self.menus = QMenu()
			self.menus.addActions([self.debug_action_copy_raw, self.debug_action_copy_html])
			self.menus.popup(e.globalPos())

			return False

		# pass on any event we are not interested in
		return False

	# TODO - mark as read
	def minimized(self) -> None:
		pass

	def set_original_post(self, post: dict) -> None:
		self.original_post = post
		self.timestamp_label.setText(self.original_post["created_at"].astimezone().strftime("%Y-%m-%d %H:%M"))

	def set_html(self, html: str) -> None:
		self.post_html = html
		self.web_view.setHtml(html, QUrl('file:///' + os.path.dirname(__file__)))

	def get_html(self) -> str:
		return self.post_html

	def post_load_finished(self, _ok_unused: bool) -> None:
		self.run_size_check()

	# slot
	def on_contents_size_changed(self, _size: QSizeF) -> None:
		self.run_size_check()

	def run_size_check(self) -> None:
		if not self.web_page:
			return

		# HACK: run a small javascript that tells us where (in pixels) the end of page is
		debug(self.post_html.replace("\n", " "))
		self.web_page.runJavaScript('if (typeof endofpage !== "undefined") { endofpage.offsetTop; }  else 0;', self.size_callback)

	def size_callback(self, result) -> None:
		if not result:
			return

		if self.web_view.geometry().height() != (result + 2):
			self.web_view.setFixedHeight(result + 2)

	def copy_html_to_clipboard(self) -> None:
		# DEBUG: this should not be here in the final version, it's meant to allow the
		# developer to copy the HTML source of this post to the clipboard so errors can
		# be investigated
		QApplication.clipboard().setText(self.get_html())

	def copy_raw_to_clipboard(self) -> None:
		# DEBUG: this should not be here in the final version, it's meant to allow the
		# developer to copy the raw status dict of this post to the clipboard so errors can
		# be investigated
		QApplication.clipboard().setText(str(self.original_post))

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
