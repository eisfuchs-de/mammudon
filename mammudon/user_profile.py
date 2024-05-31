import os
import re
import requests
import webbrowser

from PyQt6.QtCore import Qt, QSizeF, QEvent, pyqtSignal, QUrl, QObject, QChildEvent
from PyQt6.QtGui import QImage, QPixmap, QPalette, QColor, QWheelEvent
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QPushButton, QLabel, QGridLayout, QSizePolicy, QPlainTextEdit, QFrame, QScrollArea, \
	QTabWidget, QVBoxLayout, QMessageBox
from PyQt6.uic import loadUi

from mastodon import Mastodon

from mammudon.debugging import debug
from mammudon.name_list_entry import NameListEntry


class BioPage(QWebEnginePage):

	# signals
	link_clicked = pyqtSignal(QUrl)

	def __init__(self, parent: QWidget):
		super(QWebEnginePage, self).__init__(parent)

		self.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

	# DEBUG: catch all events and print info on them
# 	def event(self, e: QEvent):
# 		debug(e.type())
# 		return super().event(e)

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

		# don't pass on any other events by default
		return False


# TODO: convert to Scroller base class
class UserProfile(QWidget):
	follow_account = pyqtSignal(object)     # really an int() but that gets trashed by Qt because too big
	notify_account = pyqtSignal(object, bool)     # really an int() but that gets trashed by Qt because too big
	unfollow_account = pyqtSignal(object)     # really an int() but that gets trashed by Qt because too big

	# TODO: might want to pass the Account object rather than just the id and get the mastodon instance from there
	def __init__(self, mastodon: Mastodon, account_id: int, my_id: int):
		super().__init__()

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "user_profile.ui"), self)

		self.scroll_area: QScrollArea = self.findChild(QScrollArea, "profileScrollArea")
		self.banner_grid: QGridLayout = self.findChild(QGridLayout, "bannerGrid")
		self.close_button: QPushButton = self.findChild(QPushButton, "closeBtn")
		self.follows_you_label: QLabel = self.findChild(QLabel, "followsYouLabel")
		self.avatar_label: QLabel = self.findChild(QLabel, "avatarLabel")
		self.notes_edit: QPlainTextEdit = self.findChild(QPlainTextEdit, "notesEdit")
		self.fields_frame: QFrame = self.findChild(QFrame, "fieldsFrame")
		self.fields_grid: QGridLayout = self.findChild(QGridLayout, "fieldsGrid")
		self.follow_button: QPushButton = self.findChild(QPushButton, "followBtn")
		self.follow_req_button: QPushButton = self.findChild(QPushButton, "followRequestBtn")
		self.requested_button: QPushButton = self.findChild(QPushButton, "requestedBtn")
		self.unfollow_button: QPushButton = self.findChild(QPushButton, "unfollowBtn")
		self.notify_button: QPushButton = self.findChild(QPushButton, "notifyBtn")
		self.edit_profile_button: QPushButton = self.findChild(QPushButton, "editProfileBtn")
		self.display_name_label: QLabel = self.findChild(QLabel, "displayNameLabel")
		self.username_label: QLabel = self.findChild(QLabel, "usernameLabel")
		self.automated_label: QLabel = self.findChild(QLabel, "automatedLabel")
		self.bio_web_view: QWebEngineView = self.findChild(QWebEngineView, "bioWebView")
		self.joined_date_label: QLabel = self.findChild(QLabel, "joinedDateLabel")
		self.posts_button: QPushButton = self.findChild(QPushButton, "postsBtn")
		self.follows_button: QPushButton = self.findChild(QPushButton, "followsBtn")
		self.followers_button: QPushButton = self.findChild(QPushButton, "followersBtn")
		self.posts_count_label: QLabel = self.findChild(QLabel, "postsCountLabel")
		self.follows_count_label: QLabel = self.findChild(QLabel, "followsCountLabel")
		self.followers_count_label: QLabel = self.findChild(QLabel, "followersCountLabel")
		self.posts_tab_widget: QTabWidget = self.findChild(QTabWidget, "postsTabContainer")
		self.follows_container: QWidget = self.findChild(QWidget, "followsContainer")
		self.followers_scroller: QScrollArea = self.findChild(QScrollArea, "followersScroller")

		self.mastodon = mastodon
		try:
			self.account = self.mastodon.account(account_id)
			debug(self.account)
		except Exception as e:
			QMessageBox.information(self, f"Mammudon - User profile {account_id} lookup error:", str(e))
			return

		self.my_id = my_id

		self.followers_name_list_layout: QVBoxLayout | None = None

		self.display_name_label.setText(self.account["display_name"])
		self.username_label.setText("@" + self.account["acct"])

		self.joined_date_label.setText(self.account["created_at"].astimezone().strftime("%x"))

		# TODO: image cache
		avatar_image = QImage()
		avatar_image.loadFromData(requests.get(self.account["avatar"]).content)
		self.avatar_label.setPixmap(QPixmap.fromImage(avatar_image))

		# TODO: image cache
		banner_image = QImage()
		banner_image.loadFromData(requests.get(self.account["header"]).content)

		# since Qt does not give us a way to do this with a native widget, we must
		# get creative and calculate everything ourselves
		image_width = banner_image.width()
		image_height = banner_image.height()

		# TODO: find a good way to make these resize properly
		new_height = 145
		new_width = new_height * image_width // image_height

		# not sure if we need to do this speed-saving thing, but it's not hard to keep it in
		if image_width * image_height > (800 * 600):
			preview = banner_image.scaled(800, 600).scaled(new_width, new_height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
		else:
			preview = banner_image.scaled(new_width, new_height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

		# "getting creative" here means "use a sledge hammer"
		self.banner_label = QLabel()
		self.banner_label.setPixmap(QPixmap.fromImage(preview))
		self.banner_label.setScaledContents(False)
		palette = QPalette()
		palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
		self.banner_label.setPalette(palette)
		self.banner_label.setAutoFillBackground(True)
		self.banner_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
		self.banner_grid.addWidget(self.banner_label, 0, 0, -1, 1)

		# TODO: try to get rid of absolute values
		self.banner_label.setFixedWidth(320)
		self.banner_label.setFixedHeight(210)

		self.banner_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
		self.banner_label.stackUnder(self.follows_you_label)

		self.follow_button.clicked.connect(self.follow_button_clicked)
		self.unfollow_button.clicked.connect(self.unfollow_button_clicked)
		self.requested_button.clicked.connect(self.unfollow_button_clicked)
		self.notify_button.clicked.connect(self.notify_button_clicked)

		self.automated_label.setVisible(self.account["bot"])

		# make web view small, so it can resize properly
		# a lot of this is based on what was done in PostView()
		# TODO: PostView uses a different method now, we probably can adapt this to here, too
		self.bio_web_page = BioPage(self)
		self.bio_web_view.setPage(self.bio_web_page)

		self.bio_web_page.contentsSizeChanged.connect(self.on_contents_size_changed)
		self.bio_web_page.link_clicked.connect(self.link_clicked)

		self.bio_web_view.setVisible(bool(self.account["note"]))

		self.bio_web_view.installEventFilter(self)   # pass on scroll wheel events from the QWebEngineView to us

		# custom emoji
		note_html = self.account["note"]
		emoji: dict
		for emoji in self.account["emojis"]:
			note_html = note_html.replace(
				":" + emoji["shortcode"] + ":",
				'<img class="custom-emoji" title="&#58;' + emoji["shortcode"] + '&#58;" src="' + emoji["url"] + '">'
			)

		# mark external links with an impossible URL extension, so link_clicked() can decide upon those later
		note_html = note_html.replace('" target="_blank"', ' EXTERNAL LINK"')

		# TODO: convert to theme system
		self.bio_web_view.page().setHtml(
			'<html><head><style>' +
			'body { margin: 2px; font-size: 14px; font-family: Arial, sans-serif; } ' +
			'.custom-emoji { width: 18px; height: 18px; } ' +
			'</style></head><body>' +
			note_html +
			'</body></html>'
		)

		self.fields_frame.setVisible(bool(self.account["fields"]))

		# the mastodon specs say "by default 4 fields", and apparently not all instances
		# and/or user accounts follow this default, so we need to create each field manually
		f = 0
		field: dict
		for field in self.account["fields"]:
			field_label = QLabel(self.fields_frame)
			field_content = QLabel(self.fields_frame)

			self.fields_grid.addWidget(field_label, f, 0)
			self.fields_grid.addWidget(field_content, f, 1)

			verified_at = ""
			if field["verified_at"]:
				# TODO: show date
				verified_at = "✔ "
			field_label.setText(str(field["name"]))

			# str(value) because it gets returned as int if there is just a number in there ...
			field_content.setText(verified_at + str(field["value"]))
			f += 1

		self.posts_count_label.setText(str(self.account["statuses_count"]))
		self.follows_count_label.setText(str(self.account["following_count"]))
		self.followers_count_label.setText(str(self.account["followers_count"]))

		relationship: dict = self.mastodon.account_relationships(self.account["id"])[0]
		self.update_relationship(relationship)

		self.posts_button.clicked.connect(self.switch_tabs)
		self.follows_button.clicked.connect(self.switch_tabs)
		self.followers_button.clicked.connect(self.switch_tabs)

		self.update_pages("postsBtn")

	def eventFilter(self, o: QObject, e: QEvent) -> bool:  # pass on scroll wheel events from the QWebEnginePage to us
		# debug("UserProfile eventFilter", o, o.objectName(), e.type())

		if e.type() == QEvent.Type.Wheel:
			e: QWheelEvent
			self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - e.pixelDelta().y())
			# do not pass on this event, we don't want anything scrolling by itself
			return True

		# install the event filter also on child views that get added to the object
		if e.type() == QEvent.Type.ChildAdded:
			e: QChildEvent
			e.child().installEventFilter(self)

			# pass on this event, maybe some other part needs it
			return False

		# pass on any event we are not interested in
		return False

	def enable_close_button(self, enabled: bool) -> None:
		self.close_button.setEnabled(enabled)

	def on_contents_size_changed(self, size: QSizeF) -> None:
		# TODO: try to get rid of absolute values
		self.bio_web_view.setFixedSize(320, int(size.height()))

	@staticmethod
	def link_clicked(qurl: QUrl) -> None:
		debug(qurl)

		# assuming that "internal" links (without "EXTERNAL LINK" marker) are hashtags or usernames
		if not qurl.url().endswith(" EXTERNAL LINK"):
			match = re.match("(http|https)://([^/]+)/(@[^/]+$)", qurl.url())
			if match:
				debug("User: " + match.group(3) + "@" + match.group(2))

			match = re.match("(http|https)://([^/]+)/tags/([^/]+$)", qurl.url())
			if match:
				debug("Hashtag: #" + match.group(3))

			return

		url = qurl.url().replace(" EXTERNAL LINK", "")
		webbrowser.open(url)

	def switch_tabs(self) -> None:
		button: QObject = self.sender()
		self.update_pages(button.objectName())

	def update_pages(self, button_name: str) -> None:
		self.posts_tab_widget.setVisible(button_name == "postsBtn")
		self.follows_container.setVisible(button_name == "followsBtn")
		self.followers_scroller.setVisible(button_name == "followersBtn")

		self.posts_button.setChecked(button_name == "postsBtn")
		self.follows_button.setChecked(button_name == "followsBtn")
		self.followers_button.setChecked(button_name == "followersBtn")

		# mastodon.account_familiar_followers(1)[0]
		# # Returns the following dictionary:
		# {
		#     'id': # ID of the account for which the familiar followers are being returned
		#     'accounts': # List of account dicts of the familiar followers
		# }

		familiar_ids: list[int] = []
		account: dict
		familiar_followers = self.mastodon.account_familiar_followers(self.account["id"])
		if familiar_followers:
			for account in familiar_followers[0]["accounts"]:
				familiar_ids.append(account["id"])

		if button_name == "followsBtn":
			if not self.followers_name_list_layout:
				self.followers_name_list_layout = QVBoxLayout(self.follows_container)
				self.followers_name_list_layout.setContentsMargins(0, 0, 0, 0)
				self.followers_name_list_layout.setSpacing(2)
				self.follows_container.setLayout(self.followers_name_list_layout)

				# TODO: paginated loading when scroller hits the bottom
				page = self.mastodon.account_following(self.account["id"], limit=10)
				for account in page:
					name_list_entry = NameListEntry(account, account["id"] in familiar_ids)
					self.followers_name_list_layout.addWidget(name_list_entry)
					name_list_entry.displayNameView.installEventFilter(self)
					name_list_entry.displayNameView.page().installEventFilter(self)

	def follow_button_clicked(self) -> None:
		self.follow_account.emit(self.account["id"])

	def unfollow_button_clicked(self) -> None:
		self.unfollow_account.emit(self.account["id"])

	def notify_button_clicked(self, checked: bool) -> None:
		self.notify_account.emit(self.account["id"], checked)

	def update_relationship(self, relationship: dict) -> None:
		self.notes_edit.setPlainText(relationship["note"])
		self.notes_edit.setVisible(relationship["id"] != self.my_id)

		self.follows_you_label.setVisible(relationship["followed_by"])

		if relationship["id"] == self.my_id:
			self.follow_button.setVisible(False)
			self.follow_req_button.setVisible(False)
			self.requested_button.setVisible(False)
			self.unfollow_button.setVisible(False)
			self.notify_button.setVisible(False)
			self.edit_profile_button.setVisible(True)
		else:
			self.follow_button.setVisible(not relationship["following"] and not self.account["locked"] and not relationship["requested"])
			self.follow_req_button.setVisible(not relationship["following"] and self.account["locked"] and not relationship["requested"])
			self.requested_button.setVisible(relationship["requested"])
			self.unfollow_button.setVisible(relationship["following"])
			self.notify_button.setVisible(relationship["following"])
			self.notify_button.setChecked(relationship["notifying"])
			self.edit_profile_button.setVisible(False)

		# TODO: relationship flags
		# 'showing_reblogs': False,
		# 'languages': None,
		# 'blocking': False,
		# 'blocked_by': False,
		# 'muting': False,
		# 'muting_notifications': False,
		# 'requested': False,
		# 'requested_by': False,
		# 'domain_blocking': False,
		# 'endorsed': False,

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
