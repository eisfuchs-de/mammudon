import os
import requests

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWebEngineCore import QWebEngineSettings

from PyQt6.QtWebEngineWidgets import QWebEngineView

from PyQt6.uic import loadUi

from PyQt6.QtWidgets import QWidget, QLabel, QPushButton

from mammudon.debugging import debug


class NameListEntry(QWidget):
	def __init__(self, account: dict, following: bool):
		super().__init__()

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "name_list_entry.ui"), self)

		self.account: dict = account

		self.avatar_label: QLabel = self.findChild(QLabel, "avatarLabel")
		self.displayNameView: QWebEngineView = self.findChild(QWebEngineView, "displayNameView")
		self.username_label: QLabel = self.findChild(QLabel, "usernameLabel")
		self.follow_button: QPushButton = self.findChild(QPushButton, "followBtn")

		self.displayNameView.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

		# TODO: image cache
		avatar_image = QImage()
		avatar_image.loadFromData(requests.get(account["avatar"]).content)

		self.avatar_label.setPixmap(QPixmap.fromImage(avatar_image.scaled(QSize(45, 45), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)))
		self.username_label.setText("@" + account["acct"])

		# custom emojis
		display_name_html: str = account["display_name"]
		emoji: dict
		for emoji in account["emojis"]:
			display_name_html = display_name_html.replace(":" + emoji["shortcode"] + ":", "<img class=\"custom-emoji\" title=\"&#58;" + emoji["shortcode"] + "&#58;\" src=\"" + emoji["url"] + "\">")

		# mark external links with an impossible URL extension, so link_clicked() can decide upon those later
		display_name_html = display_name_html.replace('" target="_blank"', ' EXTERNAL LINK"')

		# TODO: use theming
		self.displayNameView.page().setHtml(
			'<html><head><style>' +
			'body { margin: 2px; font-size: 14px; font-family: Arial, sans-serif; } ' +
			'.custom-emoji { width: 18px; height: 18px; } ' +
			'</style></head><body>' +
			display_name_html +
			'</body></html>'
		)

		self.follow_button.setChecked(following)

	def __del__(self):
		debug("__del__eted NameListEntry", "@" + self.account["acct"])

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
