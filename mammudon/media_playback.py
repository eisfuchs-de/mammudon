from PyQt6.QtCore import QSettings, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

from PyQt6.QtWidgets import QWidget


class MediaPlayback(QWebEngineView):
	closed = pyqtSignal(QWidget)

	def __init__(self, media_url: str):
		super().__init__()

		self.setWindowTitle("Mammudon Media Playback - " + media_url)

		settings = QSettings()

		settings.beginGroup("MediaPlaybackWindow")
		self.resize(QSize(settings.value("size", QSize(1024, 768))))
		self.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		self.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
		self.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

		self.setHtml(
			'<html><style>.media-preview { object-fit: contain; width: 100%; height: 100%; }</style>' +
			'<body style="background: black;"><video class="media-preview" onload="this.play()" src="' + media_url + '" controls autoplay loop></video></body></html>'
		)

	def closeEvent(self, e: QCloseEvent) -> None:    # pyCharm tells me the signature is wrong, but it works
		# make sure to stop any media playing when this window closes
		self.setHtml("")

		settings = QSettings()

		settings.beginGroup("MediaPlaybackWindow")
		settings.setValue("size", self.size())
		settings.setValue("pos", self.pos())
		settings.endGroup()

		e.accept()

		# tell anyone who wants to know that this window closed
		self.closed.emit(self)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
