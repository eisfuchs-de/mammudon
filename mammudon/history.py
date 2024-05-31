# TODO: create M icon with "history.png" (or something) on top - can be set in Designer

import os
from difflib import SequenceMatcher
from html import escape

from PyQt6.QtCore import QPoint, QSize, QSettings
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QComboBox, QSplitter, QTextEdit, QWidget
from PyQt6.uic import loadUi

from mammudon.prefs import debug, preferences

from mammudon.html_to_text import HtmlToText


class History(QWidget):
	def __init__(self, parent, history_list: list[dict]):
		super().__init__(parent)

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "post_history_view.ui"), self)

		settings = QSettings()

		settings.beginGroup("HistoryWindow")
		self.resize(QSize(settings.value("size", QSize(362, 560))))
		self.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		self.splitter: QSplitter = self.findChild(QSplitter, "historySplitter")
		self.version1_combo: QComboBox = self.findChild(QComboBox, "version1Combo")
		self.version2_combo: QComboBox = self.findChild(QComboBox, "version2Combo")
		self.version1_display: QTextEdit = self.findChild(QTextEdit, "version1Display")
		self.comparison_display: QTextEdit = self.findChild(QTextEdit, "comparisonDisplay")

		self.splitter.restoreState(preferences.values["history_splitter_pos"])
		self.splitter.splitterMoved.connect(self.splitter_moved)

		if len(history_list) < 2:
			debug("Not enough history to compare:", history_list)

		self.history_list = history_list

		count = 0
		for history in history_list:
			appendix = ""
			if count == 0:
				appendix = " (original)"
			elif count == len(history_list) - 1:
				appendix = " (current)"
			elif count == len(history_list) - 2:
				appendix = " (previous)"

			self.version1_combo.addItem(history["created_at"].astimezone().strftime("%Y-%m-%d %H:%M") + appendix)
			self.version2_combo.addItem(history["created_at"].astimezone().strftime("%Y-%m-%d %H:%M") + appendix)

			count += 1

		history_len = len(history_list)
		if history_len > 2:
			# pick "previous"
			self.version1_combo.setCurrentIndex(history_len - 2)
		else:
			# pick "original"
			self.version1_combo.setCurrentIndex(0)

		# pick "current"
		self.version2_combo.setCurrentIndex(history_len - 1)

		self.version1_combo.currentIndexChanged.connect(self.show_diff)
		self.version2_combo.currentIndexChanged.connect(self.show_diff)

		self.show_diff()

	def closeEvent(self, event: QCloseEvent) -> None:
		settings = QSettings()

		settings.beginGroup("HistoryWindow")
		settings.setValue("size", self.size())
		settings.setValue("pos", self.pos())
		settings.endGroup()

		event.accept()

	def splitter_moved(self, _pos_unused, _index_unused) -> None:
		preferences.history_splitter_pos = self.splitter.saveState()
		preferences.save_settings()

	def show_diff(self) -> None:
		v1_index: int = self.version1_combo.currentIndex()
		v2_index: int = self.version2_combo.currentIndex()

		version1_text: str = self.convert_post_to_plain_text(self.history_list[v1_index])
		version2_text: str = self.convert_post_to_plain_text(self.history_list[v2_index])

		# try to keep scroll position
		slider1_position: int = self.version1_display.verticalScrollBar().sliderPosition()
		slider2_position: int = self.comparison_display.verticalScrollBar().sliderPosition()

		self.version1_display.document().setHtml(
				'<html><head><style>body { margin: 2px; font-size: 14px; font-family: Arial, sans-serif; } </style><body>' +
				version1_text.replace("\n", "<br>") + '</body></html>')

		# found this genius snippet on https://stackoverflow.com/a/62019391
		# by https://stackoverflow.com/users/2318649/balmy
		seqm = SequenceMatcher(None, version1_text, version2_text)

		output: list[str] = []
		for opcode, a0, a1, b0, b1 in seqm.get_opcodes():
			if opcode == 'equal':
				output.append(seqm.a[a0:a1])
			elif opcode == 'insert':
				output.append("<ins>" + seqm.b[b0:b1] + "</ins>")
			elif opcode == 'delete':
				output.append("<s>" + seqm.a[a0:a1] + "</s>")
			elif opcode == 'replace':
				output.append("<s>" + seqm.a[a0:a1] + "</s>" + "<ins>" + seqm.b[b0:b1] + "</ins>")

			else:
				debug("Unexpected unknown opcode:", opcode)
		# </> found this genius snippet

		self.comparison_display.document().setHtml(
			'<html><head><style>' +
			'ins { background-color: #bfb; } ' +
			's { background-color: #fbb; } ' +
			'body { margin: 2px; font-size: 14px; font-family: Arial, sans-serif; } ' +
			'</style><body>' +
			''.join(output).replace('\n', '<br>') +
			'</body></html>'
		)

		self.version1_display.verticalScrollBar().setSliderPosition(slider1_position)
		self.comparison_display.verticalScrollBar().setSliderPosition(slider2_position)

	@staticmethod
	def convert_post_to_plain_text(post: dict) -> str:

		parser = HtmlToText()
		parser.feed(post["content"])
		parser.close()

		converted_text = (
			"Sensitive:" + ("On" if post["sensitive"] else "Off") + "\n" +
			"Spoiler text: " + escape(str(post["spoiler_text"])) + "\n\n" +
			parser.text + "\n\n"
		)

		for media in post["media_attachments"]:
			converted_text += str(media["type"]) + " " + str(media["id"]) + " " + escape(str(media["description"])) + "\n"

		if post.get("poll", {}):
			# Unfortunately, post histories don't give us the full polls, only the options
			poll_text = "Poll options:\n"
			item: dict
			for item in post["poll"]["options"]:
				poll_text += "* " + escape(item["title"]) + "\n"

			converted_text += poll_text

		return converted_text.strip()

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
