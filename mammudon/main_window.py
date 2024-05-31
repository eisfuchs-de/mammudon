import os
import time

from PyQt6.QtCore import QPoint, QSize, QObject, pyqtSignal, QSettings, QRect

from PyQt6.QtGui import QColor, QFont, QPainter, QIcon, QPixmap, QAction, QCloseEvent

from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QMenu, QMessageBox, QScrollArea, QSystemTrayIcon, \
	QWidget, QAbstractSlider, QToolBar, QToolButton, QApplication
from PyQt6.uic import loadUi

from mammudon.account import Account
from mammudon.account_manager import AccountManager
from mammudon.conversations import Conversations
from mammudon.debugging import debug
from mammudon.media_attachment import MediaAttachment
from mammudon.new_post import NewPost
from mammudon.notifications import Notifications
from mammudon.prefs import preferences
from mammudon.scroller import Scroller
from mammudon.timeline import Timeline
from mammudon.user_profile import UserProfile


# TODO: for Help / About - make sure we only have one place in the project that defines
#       the version number and grab it from there
VERSION = "0.1.dev1"


class MainWindow(QMainWindow):

	# signals
	media_upload_result = pyqtSignal(object, bool, object)
	application_minimized = pyqtSignal()

	def __init__(self, parent=None):
		super().__init__(parent)

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "mammudon_main_window.ui"), self)

		self.action_publish: QAction = self.findChild(QAction, "actionPublish")
		self.action_publish.setEnabled(False)
		self.action_publish.triggered.connect(self.new_post)

		self.action_login: QAction = self.findChild(QAction, "actionLogin")
		self.action_login.setEnabled(True)
		self.action_login.triggered.connect(self.login_clicked)

		self.action_logout: QAction = self.findChild(QAction, "actionLogout")
		self.action_logout.setEnabled(False)
		self.action_logout.triggered.connect(self.logout_clicked)

		self.action_preferences: QAction = self.findChild(QAction, "actionPreferences")
		self.action_preferences.setEnabled(True)
		self.action_preferences.triggered.connect(preferences.show_dialog)

		self.action_quit: QAction = self.findChild(QAction, "actionQuit")
		self.action_quit.triggered.connect(self.save_and_quit)

		self.action_about: QAction = self.findChild(QAction, "actionAbout")
		self.action_about.triggered.connect(self.about_mammudon)

		self.toolbar: QToolBar = self.findChild(QToolBar, "toolBar")
		self.timelines_button: QToolButton = QToolButton()
		self.timelines_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		self.timelines_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "timeline.png")))
		self.timelines_button.setToolTip("Open Timeline")

		# doing this in code because Qt Designer does not have a way to add QToolButtons to QToolBars ...
		# TODO: currently duplicated in Scroller()
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
		for preset, friendly_name in self.preset_timelines.items():
			action: QAction = QAction(friendly_name, self)
			action.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "timeline_" + preset + ".png")))
			action.setData(preset)
			action.triggered.connect(self.timeline_requested)
			self.timelines_button.addAction(action)

		self.toolbar.addWidget(self.timelines_button)
		self.timelines_button.setEnabled(False)

		if preferences.values["minimize_to_tray"]:
			# Adding item on the menu bar
			self.tray_icon = QSystemTrayIcon(self)

			self.tray_icon.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "mammudon_icon.png")))
			self.tray_icon.setVisible(True)

			# apparently, changing the name of a systray menu action does not work (on KDE5)
			# so we just name it like this
			self.action_show_hide = QAction("Show/Hide", self)
			self.action_show_hide.triggered.connect(self.toggle_visibility)

			# creating the systray icon menu
			tray_menu = QMenu()

			tray_menu.addAction(self.action_show_hide)
			tray_menu.addAction(self.action_quit)

			self.tray_icon.activated.connect(self.systray_clicked)

			self.tray_icon.setContextMenu(tray_menu)
			self.tray_icon.show()

		# set up main timelines scroll area
		self.timelines_central: QWidget = self.findChild(QWidget, "centralwidget")
		self.timelines_container: QScrollArea = self.findChild(QScrollArea, "timelineContainer")

		self.timeline_scroller = self.timelines_container.widget()
		self.timeline_scroller_layout: QHBoxLayout = QHBoxLayout(self.timeline_scroller)
		self.timeline_scroller.setLayout(self.timeline_scroller_layout)
		self.timeline_scroller_layout.setSpacing(0)
		self.timeline_scroller_layout.setContentsMargins(0, 0, 0, 0)

		self.timelines_container.horizontalScrollBar().valueChanged.connect(self.container_slider_moved)

		# holds successfully uploaded media ids for each file name in the currently created post
		# TODO: might be better suited for the Account class?
		self.media_ids_per_file_name = {}

		self.last_used_account: Account | None = None
		self.show_minimize_hint = True
		self.quit_application = False

		self.unread = 0

		settings = QSettings()
		settings.beginGroup("MainWindow")
		self.resize(QSize(settings.value("size", QSize(362, 560))))
		self.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		# list of currently active accounts
		self.logins: list[Account] = []

		# create AccountManager scroller but don't show it yet
		self.account_manager: AccountManager = AccountManager()
		self.add_scroller(0, self.account_manager)
		self.account_manager.enable_close_button(False)

		self.account_manager.add_login.connect(self.add_login)
		self.account_manager.close_button.clicked.connect(self.close_account_manager)

		self.timeline_scroller_layout.insertWidget(0, self.account_manager)

		settings = QSettings()
		settings.beginGroup("Accounts")

		autologin = False
		for account_username in settings.allKeys():
			account_data = dict(settings.value(account_username))
			if account_data.get("autologin", False):
				debug("Autologin to:", account_username)
				account = Account(account_data)
				self.add_login(account)
				autologin = True

		settings.endGroup()

		# we have no accounts that wanted to log in automatically, so display the AccountManager scroller
		if not autologin:
			self.open_account_manager()

		# this widget is only here to put the whole main window into OpenGL accelerated mode
		# right from the start; otherwise it will flicker badly the first time a post is inserted
		# into a timeline
		anti_flicker_web_view: QWidget | None = self.findChild(QWidget, "antiFlickerWebView")
		if anti_flicker_web_view:
			anti_flicker_web_view.hide()

	def __del__(self):
		debug("__del__eting main window")

	# TODO: enable/disable timeline choices, so you can't select one that is already there
	#       for that specific account, or auto-scroll to the existing one
	def timeline_requested(self) -> None:
		timeline: QObject = self.sender()
		timeline_name = timeline.data()

		if timeline_name in self.preset_timelines:
			self.add_timeline(
				self.last_used_account,
				timeline_name,
				self.preset_timelines[timeline_name])

	def container_slider_moved(self) -> None:
		slider: QObject = self.sender()

		slider: QAbstractSlider
		slider_value: int = slider.value()
		new_value: int = slider_value

		# snap slider to nearest timeline
		for num in range(self.timeline_scroller_layout.count()):
			geometry: QRect = self.timeline_scroller_layout.itemAt(num).widget().geometry()

			if slider_value > geometry.x() - geometry.width() // 2:
				new_value = geometry.x()

		slider.setValue(new_value)

	def open_account_manager(self) -> None:
		if not self.account_manager.isVisible():
			debug("opening account manager")
			self.account_manager.setVisible(True)
			self.timelines_container.horizontalScrollBar().setValue(0)

			self.action_login.setEnabled(False)
			self.action_logout.setEnabled(False)
		else:
			debug("account manager was already open")

	def close_account_manager(self) -> None:
		self.account_manager.setVisible(False)

		self.action_login.setEnabled(True)
		self.action_logout.setEnabled(True)

	def add_login(self, account: Account) -> None:
		debug("Received add_login signal:", account)
		self.logins.append(account)
		account.login_status.connect(self.account_login_status)
		account.login()

	def account_login_status(self, status: str) -> None:
		account: QObject = self.sender()
		account: Account

		debug("Received account_login_status signal:", status)
		if status == "success":
			timeline_name: str

			# add home timeline by default ...
			self.add_timeline(account, "home", "Home")

			# TODO: ... other timelines will be up to the user here
			for timeline_name, params in account.timelines.items():
				if not account.account_autologin:
					self.account_manager.autosave_login(account)

				# do not add "home" twice - this is clunky and needs a better solution
				if timeline_name != "home":
					self.add_timeline(account, timeline_name, params["friendly_name"])

			# TODO: disable again when we logged out of all accounts
			self.account_manager.enable_close_button(True)

			self.close_account_manager()

		elif status == "revoked":
			account.login(drop_access_tokens=True)

	def login_clicked(self, _checked) -> None:
		self.open_account_manager()

	# TODO
	def logout_clicked(self, clicked) -> None:
		pass

	def toggle_visibility(self) -> None:
		if self.isVisible():
			self.hide()
			self.application_minimized.emit()
		else:
			self.show()

			# raise window on Windows/Linux
			self.activateWindow()

	# apparently, changing the name of a systray menu action does not work (on KDE5)
	# so we don't bother
	# def event(self, e):
	# 	if e.type() == QShowEvent:
	# 		self.action_show_hide.setText("Hide")
	# 		return True
	#
	# 	if e.type() == QHideEvent:
	# 		self.action_show_hide.setText("Show")
	# 		return True
	#
	# 	return False

	def check_unread(self) -> None:
		if self.unread == 0:
			if preferences.values["minimize_to_tray"]:
				self.tray_icon.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "mammudon_icon.png")))
		elif self.unread == -1:
			debug("Unread posts went into negative!")
			breakpoint()
		else:
			pix = QPixmap(os.path.join(os.path.dirname(__file__), "icons", "mammudon_icon_counter.png"))
			painter = QPainter(pix)
			painter.setPen(QColor(255, 255, 255))
			# doesn't look like it really uses Noto, at least not as QFont.Black
			painter.setFont(QFont("Noto Sans", 14, QFont.Weight.Black))
			number = self.unread
			offset = 0
			if number < 10:
				offset = 6
			painter.drawText(QPoint(20 + offset, 40), str(number))

			if preferences.values["minimize_to_tray"]:
				self.tray_icon.setIcon(QIcon(pix))

			del painter

	def adjust_unreads(self, num_unread: int) -> None:
		self.unread += num_unread
		self.check_unread()

	def adjust_unread(self, unread: bool) -> None:
		self.adjust_unreads(1 if unread else -1)

	# TODO: probably a good idea to move this into the NewPost or Account class
	def publish_post(self, new_post_popup: NewPost) -> None:
		# TODO: posting options: poll
		new_post_popup.enable_publish(False)

		post = new_post_popup.get_post()
		debug("new post: ", post)

		media_fail = False
		media_ids = []

		# TODO: show upload media progress (1/4 ... 2/4 ...)
		media_file: MediaAttachment
		for media_file in post["media_files"]:
			debug(media_file.file_name())

			# don't upload media that was already uploaded successfully
			if media_file.file_name() in self.media_ids_per_file_name:
				debug("media", media_file.file_name(), "already uploaded, passing id", self.media_ids_per_file_name[media_file.file_name()])
				media_ids.append(self.media_ids_per_file_name[media_file.file_name()])
			else:
				try:
					# TODO: thumbnail=..., thumbnail_mime_type=...
					media_dict = new_post_popup.account.mastodon.media_post(
						media_file.file_name(),
						description=media_file.description(),
						# focus_point() returns a tuple[float, float] in the range of 0.0..1.0 - remember that
						# mastodon media uses -1.0..1.0, so it needs to be recalculated on upload
						focus=(media_file.focus_point()[0] * 2.0 - 1.0, 1.0 - media_file.focus_point()[1] * 2.0)
					)
					media_ids.append(media_dict["id"])

					self.media_ids_per_file_name[media_file.file_name()] = media_dict["id"]
					self.media_upload_result.emit(media_file.file_name(), True, "Success")

					debug(media_file.file_name(), media_dict)

				except Exception as e:
					self.media_upload_result.emit(media_file.file_name(), False, str(e))
					QMessageBox.information(self, "Mammudon", "Could not upload media:\n" + media_file.file_name() + "\n" + str(e))
					media_fail = True

		if media_fail:
			new_post_popup.enable_publish(True)
			return

		try:
			# TODO: if we try publish media too quickly, we get an "unprocessed media" error,
			#       but we can just publish again. maybe check the media IDs for URLs until all
			#       are finalized
			if media_ids:
				time.sleep(5.0)

			debug("publishing post!", new_post_popup.account.mastodon.status_post(
				status=post["content"],
				in_reply_to_id=post["in_reply_to_id"],
				media_ids=media_ids,
				sensitive=post["sensitive"],
				visibility=post["visibility"],
				spoiler_text=post["spoiler_text"],
				language=post["language"],
				idempotency_key=post["idempotency_key"],
				content_type=post["content_type"] if new_post_popup.account.account_feature_set == "pleroma" else None,
				scheduled_at=post["scheduled_at"],
				poll=post["poll"],
				quote_id=post["quote_id"]))

			new_post_popup.close()

			self.action_publish.setEnabled(True)

		except Exception as e:
			QMessageBox.information(self, "Mammudon", "Could not publish post:\n" + str(e))
			new_post_popup.enable_publish(True)
			new_post_popup.activateWindow()

	# TODO: probably a good idea to move this into the NewPost or Account class
	def cancel_post(self, new_post_popup: QWidget) -> None:
		new_post_popup.close()

		# update publish icon
		self.set_last_used_account(self.last_used_account)

	def new_post(self, reply_to_post: dict = None) -> None:
		# TODO: posting options

		# holds successfully uploaded media ids for each file name in this post
		self.media_ids_per_file_name.clear()

		if not self.last_used_account.is_composing_post:
			self.action_publish.setEnabled(False)
			new_post_popup = NewPost(self, self.last_used_account, reply_to_post)

			new_post_popup.publish.connect(self.publish_post)
			new_post_popup.cancel.connect(self.cancel_post)

			self.media_upload_result.connect(new_post_popup.media_uploaded)

			new_post_popup.show()
		else:
			self.last_used_account.is_composing_post.activateWindow()

	# TODO: test CallbackStreamListener
	@staticmethod
	def handler_update() -> None:
		debug("handler_update")

	# TODO: test CallbackStreamListener
	@staticmethod
	def handler_local_update() -> None:
		debug("handler_local_update")

	def add_scroller(self, index: int, scroller: QWidget) -> QWidget:
		# TODO: set up timeline/scroller width somehow, currently fixed to 350
		scroller.setMaximumWidth(350)
		scroller.setMinimumWidth(350)

		self.timeline_scroller_layout.insertWidget(index, scroller)

		# explicitly show the scroller so the layout will start to do its work
		scroller.show()

		# give the layout a chance to settle so the scroller position is valid
		QApplication.processEvents()
		debug(scroller.geometry(), scroller.pos(), scroller.frameGeometry())

		x_offset = scroller.mapTo(self.timeline_scroller, scroller.pos()).x()
		debug(x_offset, scroller.geometry())

		self.timelines_container.horizontalScrollBar().setValue(x_offset)

		return scroller

	def remove_scroller(self, scroller: QWidget) -> None:
		debug("remove scroller")
		self.timeline_scroller_layout.removeWidget(scroller)
		scroller.deleteLater()

	def add_timeline(self, account: Account, name: str, friendly_name: str) -> None:
		if name == "notifications":
			# WIP
			timeline = Notifications(account, name, friendly_name)
		elif name == "conversations":
			# WIP
			timeline = Conversations(account, name, friendly_name)
		else:
			timeline = Timeline(account, name, friendly_name)

		account.stream_listener_ready.connect(timeline.connect_to_stream_listener)
		account.add_timeline(name, friendly_name, timeline)

		# -1 = add at the end
		self.add_scroller(-1, timeline)

		timeline.current_account.connect(self.set_last_used_account)
		timeline.close_scroller.connect(self.close_scroller)
		timeline.open_profile.connect(self.open_profile)
		timeline.reply_to_post.connect(self.new_post)
		timeline.unread_changed.connect(self.adjust_unread)
		self.application_minimized.connect(timeline.application_minimized)

		self.set_last_used_account(account)

	def close_scroller(self, scroller: Scroller, num_unreads: int = 0) -> None:
		debug("close_scroller received from scroller", scroller.friendly_name, scroller.account.account_username)
		self.remove_scroller(scroller)
		self.adjust_unreads(-num_unreads)
		scroller.account.remove_timeline(scroller.scroller_name)

	def set_last_used_account(self, account: Account) -> None:
		# debug("Last used account:", account)
		self.last_used_account = account
		if not account:
			self.timelines_button.setEnabled(False)
			self.setWindowTitle("Mammudon")
			self.action_publish.setEnabled(False)
			return

		self.setWindowTitle(account.account_username + " - Mammudon")
		self.action_publish.setEnabled(not bool(account.is_composing_post))
		self.timelines_button.setEnabled(True)

	# slot
	def open_profile(self, account_id: int) -> None:
		profile: UserProfile = UserProfile(
			self.last_used_account.mastodon, account_id,
			self.last_used_account.account["id"]
		)

		self.add_scroller(self.timeline_scroller_layout.indexOf(self.sender()), profile)

		profile.close_button.clicked.connect(profile.close)
		profile.follow_account.connect(self.last_used_account.follow_account)
		profile.notify_account.connect(self.last_used_account.notify_account)
		profile.unfollow_account.connect(self.last_used_account.unfollow_account)

		self.last_used_account.relationship_update.connect(profile.update_relationship)

	def systray_clicked(self, reason) -> None:
		if reason == QSystemTrayIcon.ActivationReason.Trigger:
			# TODO: if the window is already visible but obscured, just raise it instead
			self.toggle_visibility()

	# only close the application when preferences.minimize_to_tray is False, otherwise hide
	# in the systray and show new message markers
	def closeEvent(self, event: QCloseEvent) -> None:
		if not preferences.values["minimize_to_tray"] or self.quit_application:

			if preferences.preferences_dialog:
				preferences.close_dialog(preferences.preferences_dialog)

			event.accept()
			return

		event.ignore()

		self.toggle_visibility()
		if self.show_minimize_hint:
			self.tray_icon.showMessage(
				"Mammudon",
				"Mammudon was minimized to the system tray. If you want to quit the application, choose the Quit item from the File menu or the System Tray icon's context menu.",
				QSystemTrayIcon.MessageIcon.Information, 2000)

			self.show_minimize_hint = False

		self.application_minimized.emit()

	def about_mammudon(self) -> None:
		# TODO: translations instead of fixed _en version
		with open(os.path.join(os.path.dirname(__file__), "res", "about_mammudon_en.html"), 'r') as about_file:
			about_html = about_file.read()
			about_html = about_html.replace("%version%", VERSION)
			QMessageBox.about(self, "About Mammudon", about_html)

	def save_and_quit(self) -> None:
		settings = QSettings()
		settings.beginGroup("MainWindow")
		settings.setValue("size", self.size())
		settings.setValue("pos", self.pos())
		settings.endGroup()

		self.quit_application = True

		QApplication.instance().quit()

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
