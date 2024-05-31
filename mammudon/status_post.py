# TODO: Display post visibility (Public, Unlisted, ...)
# TODO: Display post language

import gc
import os
import sys
import webbrowser

from PyQt6 import QtCore
from PyQt6.QtGui import QAction, QMouseEvent, QContextMenuEvent
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget, QMenu, QApplication
from PyQt6.QtCore import QEvent, QUrl, QObject, QSizeF, QChildEvent, pyqtSignal
from PyQt6.uic import loadUi

from mammudon.debugging import debug
from mammudon.image_browser import ImageBrowser
from mammudon.media_playback import MediaPlayback


class PostPage(QWebEnginePage):

	# signals
	link_clicked = pyqtSignal(QUrl)

	def __init__(self, parent):
		super(QWebEnginePage, self).__init__(parent)

	# DEBUG: catch all events and print info on them
	# def event(self, e):
	# 	debug(e.type())
	# 	return super().event(e)

	def acceptNavigationRequest(self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool) -> bool:

		# any links clicked on the page should be caught and stopped, so we can deal with them
		if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
			self.link_clicked.emit(url)
			return False

		# initial page load, we want to pass on this event
		if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
			return True

		# DEBUG: otherwise report the nav type and url to the log
		debug(nav_type, url)

		if nav_type == QWebEnginePage.NavigationType.NavigationTypeOther:
			return True

		# don't pass on any other events by default
		return False


class PostView(QWidget):

	# signals
	post_context_requested = pyqtSignal(object)
	post_clicked = pyqtSignal(object)                  # currently nobody is listening to this signal
	show_history_clicked = pyqtSignal(object)
	reply_to_post_clicked = pyqtSignal(object)
	boost_post = pyqtSignal(object, bool)       # TODO: boost with visibility
	favorite_post = pyqtSignal(object, bool)
	bookmark_post = pyqtSignal(object, bool)
	delete_post = pyqtSignal(object)
	mute_post = pyqtSignal(object, bool)
	in_browser = pyqtSignal(object)
	reload_post = pyqtSignal(object)
	was_destroyed = pyqtSignal(object)
	account_clicked = pyqtSignal(object)
	is_unread = pyqtSignal(bool)
	mouse_wheel_event = pyqtSignal(object)  # QEvent with type() == Wheel
	poll_vote = pyqtSignal(object, object)  # poll_id: int, voted_options: list[int]
	poll_refresh = pyqtSignal(object)  # poll_id: int
	poll_show_results = pyqtSignal(object)  # poll_id: int

	def __init__(self, *, authored_by_me: bool, post_id: int, threaded=False, count_as_unread=True):
		super(QWidget, self).__init__()

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "postview.ui"), self)

		# pre-declare attributes that get set in the functions below
		self.threaded = False  # bool that tells us if this post is threaded under another post

		self.authored_by_me = authored_by_me
		self.id = post_id

		self.conversation_button: QPushButton = self.findChild(QPushButton, "conversationBtn")
		self.reply_button: QPushButton = self.findChild(QPushButton, "replyBtn")
		self.boost_button: QPushButton = self.findChild(QPushButton, "boostBtn")  # TODO: boost with visibility
		self.favorite_button: QPushButton = self.findChild(QPushButton, "favoriteBtn")
		self.bookmark_button: QPushButton = self.findChild(QPushButton, "bookmarkBtn")

		self.post_options_button: QToolButton = self.findChild(QToolButton, "postOptionsBtn")  # TODO: more post options

		self.post_action_delete: QAction = self.findChild(QAction, "postActionDelete")  # TODO: delete and redraft
		self.post_action_mute: QAction = self.findChild(QAction, "postActionMute")
		self.post_action_copy_link: QAction = self.findChild(QAction, "postActionCopyLink")
		self.post_action_browser: QAction = self.findChild(QAction, "postActionBrowser")
		self.post_action_reload: QAction = self.findChild(QAction, "postActionReload")

		self.unread_marker: QWidget = self.findChild(QWidget, "unreadColor")
		self.threading_marker: QWidget = self.findChild(QWidget, "threadingMarker")
		self.edited_button: QPushButton = self.findChild(QPushButton, "editedBtn")
		self.posted_with_label: QLabel = self.findChild(QLabel, "postedWithLabel")

		self.reply_count: QLabel = self.findChild(QLabel, "replyCount")
		self.boost_count: QLabel = self.findChild(QLabel, "boostCount")
		self.favorite_count: QLabel = self.findChild(QLabel, "favoriteCount")

		self.threaded_layout: QVBoxLayout = self.findChild(QVBoxLayout, "threadVLayout")

		self.web_view: QWebEngineView = self.findChild(QWebEngineView, "postView")

		# DEBUG: create debug action to be able to copy the raw post or HTML source to the clipboard
		self.debug_action_copy_html: QAction = self.findChild(QAction, "debugCopyHtml")
		self.debug_action_copy_raw: QAction = self.findChild(QAction, "debugCopyRaw")

		self.unread = False                     # bool that holds this post's "unread" status
		self.count_as_unread = count_as_unread  # timelines like e.g. federated/local don't count unread, it gets too busy

		self.set_threaded(threaded)

		# original post before changing the HTML or anything else
		self.original_post = {}

		# post html code before it got to the QWebEnginePage widget - good for edited comparison
		self.post_html = ""

		# dicts of this post's history
		self.history: list[dict] = []

		self.web_page: PostPage | None = PostPage(self)
		self.web_view.setPage(self.web_page)

		self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
		self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
		# allow QWebEnginePage to load local image files from "file:" URLs, needs BaseUrl being set in setHtml()
		# self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

		# pass on any events from the QWebEngineView to us
		# this is needed for changes in focusProxy when we do the setPage() call below
		# we catch the ChildAdded event to install an event filter on the focusProxy
		# which then gives us mouse clicks performed on the PostPage
		# Thanks to https://github.com/qutebrowser/qutebrowser and their eventfilter.py
		self.web_view.installEventFilter(self)

		# make QWebEngineView too small initially so it resizes properly
		# TODO: Check if this is still needed
		self.web_view.setMinimumHeight(48)
		self.web_view.setMinimumWidth(48)

		# this works well for initial sizing
		self.web_page.loadFinished.connect(self.post_load_finished)
		self.web_page.link_clicked.connect(self.link_clicked)

		# create resize signal connection, just to make resizing look a bit smoother
		self.web_page.contentsSizeChanged.connect(self.on_contents_size_changed)

		self.image_browser: ImageBrowser | None = None
		self.media_playback: MediaPlayback | None = None

		self.conversation_button.setEnabled(False)
		self.conversation_button.setChecked(False)

		self.conversation_button.clicked.connect(self.expand_post_context)
		self.edited_button.clicked.connect(self.show_history)
		self.reply_button.clicked.connect(self.reply_to_post)
		self.boost_button.clicked.connect(self.boost_clicked)  # TODO: boost with visibility
		self.favorite_button.clicked.connect(self.favorite_clicked)
		self.bookmark_button.clicked.connect(self.bookmark_clicked)

		self.debug_action_copy_html.triggered.connect(self.copy_html_to_clipboard)
		self.debug_action_copy_raw.triggered.connect(self.copy_raw_to_clipboard)
		self.web_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)

		self.post_action_delete.triggered.connect(self.delete_post_clicked)
		self.post_action_mute.triggered.connect(self.mute_post_clicked)
		self.post_action_copy_link.triggered.connect(self.copy_link_clicked)
		self.post_action_browser.triggered.connect(self.browser_clicked)
		self.post_action_reload.triggered.connect(self.reload_post_clicked)

		self.menus: QMenu | None = None

		# this is a post that the user sent themselves, so add a few more functions
		if self.authored_by_me:
			# TODO: edit post
			self.post_options_button.addAction(self.post_action_delete)
			self.post_options_button.addAction(self.post_action_mute)

		# actions allowed for all posts
		self.post_options_button.addAction(self.post_action_copy_link)
		self.post_options_button.addAction(self.post_action_browser)
		self.post_options_button.addAction(self.post_action_reload)

	def __del__(self) -> None:
		# remove from the unread counter if needed
		self.set_unread(False, False)

		# DEBUG: printing this to see if posts are properly deleted when purged
		debug("__del__eting PostView", self.id)

	def destroy_view(self) -> None:
		debug("PostView", self.id, "destroy_view()")

		# remove from the unread counter
		self.set_unread(False)
		# remove/delete anything that might have bigger memory impact, since I can't figure out
		# how to REALLY make sure that a PostView is REALLY deleted from memory. So make it as
		# small as possible in case it never gets freed
		self.web_view.setPage(None)
		del self.web_page
		self.web_page = None
		self.original_post = None
		self.history = None

		# recursively destroy any threaded posts below this one
		if self.threaded_layout.count() > 1:
			debug("PostView.destroy_view(): Deleted PostView had", self.threaded_layout.count(), "threaded posts")
			while self.threaded_layout.count() > 1:
				# DEBUGGING
				gc.collect()
				referrers = gc.get_referrers(self)
				debug("PostView::destroy_view() before: ", referrers)

				post_view_to_delete: QWidget = self.threaded_layout.itemAt(1).widget()

				post_view_to_delete: PostView
				debug("Attempt to delete threaded post", post_view_to_delete.id)

				self.threaded_layout.removeWidget(post_view_to_delete)
				post_view_to_delete.destroy_view()

				# DEBUGGING
				gc.collect()
				referrers = gc.get_referrers(self)
				debug("PostView::destroy_view() after: ", referrers)

		# remove ourselves from any Timeline
		self.hide()
		self.setParent(None)

		self.was_destroyed.emit(self.id)

		# DEBUGGING
		gc.collect()
		rc = sys.getrefcount(self)

		# correct for unthreaded posts? TODO: it was 2 before, what changed?
		if rc == 2 or rc == 3:
			return

		# correct for threaded posts? TODO: it was 3 before, what changed?
		if rc == 4:
			if self.threaded:
				return

		# this should not happen, so break!
		debug("PostView::destroy_view(", self, self.id, ").refcount:", rc, self.threaded)
		referrers = gc.get_referrers(self)
		debug(referrers)
		breakpoint()

	# pass on QWebEngineView events to us, like mouse clicks and ChildAdded events
	def eventFilter(self, o: QObject, e: QEvent) -> bool:
		if e.type() == QEvent.Type.Wheel:
			self.mouse_wheel_event.emit(e)
			# do not pass on this event, we don't want anything scrolling by itself
			return True

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

		# do not react to any of the events past this point when this PostView is reloading
		if not self.isEnabled():
			return False

		if e.type() == QEvent.Type.MouseButtonPress:
			e: QMouseEvent
			self.handle_mouse_click(e)

			# pass on this event for drag-selecting, link clicking, profile picture click etc.
			return False

		if e.type() == QEvent.Type.ContextMenu:
			e: QContextMenuEvent

			self.menus = QMenu()
			self.menus.addActions([self.post_action_reload, self.debug_action_copy_raw, self.debug_action_copy_html])
			self.menus.popup(e.globalPos())

			return True

		# pass on any event we are not interested in
		return False

	# slot
	def post_load_finished(self, _ok_unused: bool) -> None:
		self.run_size_check()

	def run_size_check(self) -> None:
		if not self.web_page:
			return

		# HACK: run a small javascript that tells us where (in pixels) the end of page is
		self.web_page.runJavaScript('if (typeof endofpage !== "undefined") { endofpage.offsetTop; }  else 0;', self.size_callback)

	def size_callback(self, result) -> None:
		if not result:
			return

		# if the size needs to be adjusted, do so right here
		if self.web_view.geometry().height() != (result + 2):
			self.web_view.setFixedHeight(result + 2)

	# slot
	def on_contents_size_changed(self, _size: QSizeF) -> None:
		# debug("size changed:", size)
		self.run_size_check()

	def mousePressEvent(self, e: QMouseEvent) -> None:
		# DEBUG: mostly printing this here to get the post/reply to IDs to chase bugs
		debug("mousePressEvent() in PostView", self.id)
		debug("in reply to", self.original_post["in_reply_to_id"])

		self.handle_mouse_click(e)

		e.ignore()

	def handle_mouse_click(self, _event: QMouseEvent) -> None:
		# currently we do the same for all mouse clicks
		debug("marking post as read", self.id)
		self.set_unread(False)

		# currently nobody listening to this signal
		self.post_clicked.emit(self)

	# we want to keep a copy of the HTML content around, so we can re-set it if needed
	# e.g. for changing post sizes when expanding/collapsing spoilers, and reading it
	# back from the QWebEnginePage is a pain
	def set_html(self, html: str) -> None:
		self.post_html = html
		self.web_page.setHtml(self.post_html)

	def get_html(self) -> str:
		return self.post_html

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

	def set_unread(self, unread: bool, update_unread_marker: bool = True) -> None:
		# send signal only if something changed
		if self.unread != unread:
			self.unread = unread

			if self.count_as_unread:
				if update_unread_marker:
					self.is_unread.emit(self.unread)

		if update_unread_marker:
			# in case the marker needs to be set even when the internal status did not change (e.g. by __init__)
			self.unread_marker.setEnabled(self.unread)

	def minimized(self) -> None:
		self.set_unread(False)

	def update_edit_button(self) -> None:
		edit_button_text = self.original_post["created_at"].astimezone().strftime("%Y-%m-%d %H:%M")

		if self.history:
			if len(self.history) > 1:
				edit_button_text += " - Edit: " + self.history[-1]["created_at"].astimezone().strftime("%Y-%m-%d %H:%M")

		self.edited_button.setText(edit_button_text)

	def set_original_post(self, post: dict) -> None:
		# original post might have been a boost, so we need to pull out the boosted post
		if post["reblog"]:
			self.original_post = post["reblog"]
		else:
			self.original_post = post

		self.set_posted_with(self.original_post.get("application", {}))
		self.update_edit_button()

	def set_posted_with(self, app: dict) -> None:
		if not app:
			self.posted_with_label.setText("unknown")
		elif app["website"]:
			self.posted_with_label.setText('<a href="' + app["website"] + '">' + app["name"] + '</a>')
		else:
			self.posted_with_label.setText(app.get("name", "unknown"))

	def show_history(self) -> None:
		self.show_history_clicked.emit(self)

	def set_history(self, history: list[dict]) -> None:
		self.history = history
		self.update_edit_button()

	def expand_post_context(self, checked: bool) -> None:
		if self.threaded_layout.count() < 2:
			debug("needs to load post context ids for post", self.id)
			self.post_context_requested.emit(self.id)
			return

		# hide all posts under the one that was clicked
		for index in range(1, self.threaded_layout.count()):
			self.threaded_layout.itemAt(index).widget().setVisible(checked)

	def link_clicked(self, qurl: QUrl) -> None:
		scheme = qurl.scheme()
		url = qurl.toString()

		# account image or name clicked
		if url == self.original_post["account"]["url"]:
			user_name = "@" + self.original_post["account"]["acct"]
			debug("user", user_name)
			self.account_clicked.emit(self.original_post["account"]["id"])
			return

		# post was boosted by another account, so check for boosting account clicks
		if "mammudon_boosted_by_url" in self.original_post:
			# account image or name of boosting account clicked
			if url == self.original_post["mammudon_boosted_by_url"]:
				user_name = "@" + self.original_post["mammudon_boosted_by_acct"]
				self.account_clicked.emit(self.original_post["mammudon_boosted_by_id"])
				debug("user", user_name)
				return

		# a link with regard to a poll function was clicked
		if scheme == "poll":
			# poll://subcommand/poll_id
			poll_id = qurl.path()[1:]  # skip leading "/"

			if qurl.host() == "vote":
				# gather all checked options and send them back to a callback function as an array
				self.web_page.runJavaScript('inputs = document.getElementsByTagName("input"); result = ["' + str(poll_id) + '"]; n = 0; for(option of inputs) { if(option.checked) { result.push(n.toString()); } n++; } result;', self.vote_callback)
			elif qurl.host() == "refresh":
				self.poll_refresh.emit(poll_id)
			elif qurl.host() == "results":
				self.poll_show_results.emit(poll_id)
			else:
				debug("unknown poll subcommand:", qurl.host(), qurl)

			return

		# an image was clicked
		if scheme == "media-image":
			if self.image_browser:
				self.image_browser.close()
				return

			media: list[str] = []

			attachment: dict
			for attachment in self.original_post["media_attachments"]:
				media.append(attachment["url"])

			current_image = media.index(url.split(":", 1)[1])
			self.image_browser = ImageBrowser(media, current_image)
			self.image_browser.closed.connect(self.on_image_browser_closed)
			self.image_browser.show()

			return

		# a video or gifv was clicked
		if scheme == "media-video" or scheme == "media-gifv":
			if self.media_playback:
				self.media_playback.close()
				return

			self.web_page.runJavaScript("v = document.getElementsByTagName('video'); for(p of v) { p.pause(); }")
			self.media_playback = MediaPlayback(self.original_post["media_attachments"][0]["url"])
			self.media_playback.closed.connect(self.on_media_playback_closed)
			self.media_playback.show()
			return

		# an audio link was clicked # TODO
		if scheme == "media-audio":
			pass

		# some unknown media link was clicked # TODO
		if scheme == "media-unknown":
			pass

		# check if a @mention link was clicked
		for mention in self.original_post["mentions"]:
			if mention["url"] == url:
				user_name = "@" + mention["acct"]
				self.account_clicked.emit(mention["id"])
				debug("user", user_name)
				return

		# check if a #hashtag was clicked
		for tag in self.original_post["tags"]:
			if tag["url"] == url:
				hashtag_name = "#" + tag["name"]
				debug("hashtag", hashtag_name)
				return

		# remove our custom media-...: scheme if present to allow
		# the web browser to open the url - this can be removed once
		# all media-...: links are handled by us
		if scheme.startswith("media-"):
			debug(scheme, qurl)
			url = url.replace(scheme + ":", "")

		# if all else fails, send this link to the system web browser
		debug(url)
		webbrowser.open(url)

	def vote_callback(self, r: list[int]) -> None:
		# do not send empty votes
		if len(r) < 2:
			return

		self.poll_vote.emit(r[0], r[1:])

	# TODO: boost with visibility
	def boost_clicked(self, checked: bool) -> None:
		self.boost_post.emit(self, checked)
		self.set_unread(False)

	def favorite_clicked(self, checked: bool) -> None:
		self.favorite_post.emit(self, checked)
		self.set_unread(False)

	def bookmark_clicked(self, checked: bool) -> None:
		self.bookmark_post.emit(self, checked)
		self.set_unread(False)

	def delete_post_clicked(self, _checked: bool) -> None:
		self.delete_post.emit(self)
		del self  # TODO: check if this is still needed or even correct at all

	def mute_post_clicked(self, checked: bool) -> None:
		self.mute_post.emit(self, checked)
		self.set_unread(False)

	def copy_link_clicked(self, _checked: bool) -> None:
		# self.copy_post_link.emit(self.original_post)
		self.set_unread(False)
		QApplication.clipboard().setText(self.original_post["url"])

	def browser_clicked(self, _checked: bool) -> None:
		self.in_browser.emit(self.original_post)
		self.set_unread(False)

	def reload_post_clicked(self, _checked: bool) -> None:
		self.reload_post.emit(self)

	def reply_to_post(self, _checked: bool) -> None:
		self.reply_to_post_clicked.emit(self.original_post)
		self.set_unread(False)

	def set_threaded(self, threaded: bool) -> None:
		# weird construct, but "threaded" can be "None", so we need to take care of that
		self.threaded = False
		if threaded:
			self.threaded = True

		self.threading_marker.setVisible(self.threaded)

	# post is threaded but the timeline does not have the parent post
	def set_no_parent_post(self) -> None:
		self.threading_marker.setVisible(False)

	def on_image_browser_closed(self) -> None:
		self.image_browser = None

	def on_media_playback_closed(self) -> None:
		self.media_playback = None

	def set_reply_count(self, count: int) -> None:
		self.reply_count.setText(str(count))
		self.conversation_button.setEnabled(bool(count))

	def set_boost_count(self, count: int) -> None:
		self.boost_count.setText(str(count))

	def set_favorite_count(self, count: int) -> None:
		self.favorite_count.setText(str(count))

	# replied status isn't available in the status reply dict
	# def set_replied(self, checked):
	# 	self.reply_button.setChecked(checked)

	def set_boosted(self, checked: bool) -> None:
		self.boost_button.setChecked(checked)

	def set_favorited(self, checked: bool) -> None:
		self.favorite_button.setChecked(checked)

	def set_bookmarked(self, checked: bool) -> None:
		self.bookmark_button.setChecked(checked)

	def set_muted(self, checked: bool) -> None:
		self.post_action_mute.setChecked(checked)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
