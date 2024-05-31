# TODO: image drag should stop at zoomed image edges
# TODO: image cache

import os
import requests

from PyQt6 import QtCore
from PyQt6.QtCore import QSettings, QSize, QPoint, pyqtSignal, QEvent, QRect, QTimerEvent, QThread, QCoreApplication, \
	QObject
from PyQt6.QtGui import QCloseEvent, QWheelEvent, QImage, QPixmap, QMouseEvent, QResizeEvent, QKeyEvent
from PyQt6.uic import loadUi

from PyQt6.QtWidgets import QPushButton, QWidget, QGridLayout, QLayout, QScrollArea, QLabel, QProgressBar

from mammudon.debugging import debug


class ImageLoaderProgressEvent(QEvent):
	def __init__(self, image_url: str, progress: int, image: QImage | None):
		super().__init__(QEvent.Type.User)

		self._image_url = image_url
		self._progress: int = progress
		self._image: QImage = image

	def type(self) -> QEvent.Type:
		return QEvent.Type.User

	def image_url(self) -> str:
		return self._image_url

	def progress(self) -> int:
		return self._progress

	def image(self) -> QImage | None:
		return self._image


class ImageLoader(QThread):
	def __init__(self, parent: QObject, image_url: str):
		super(ImageLoader, self).__init__(parent)
		self.image_url = image_url

	def post_progress_event(self, progress: int, image: QImage = None) -> bool:
		if self.isInterruptionRequested():
			return False

		e: ImageLoaderProgressEvent = ImageLoaderProgressEvent(self.image_url, progress, image)
		QCoreApplication.postEvent(self.parent(), e)

		return True

	def run(self) -> None:
		try:
			if not self.post_progress_event(0):
				return

			image_content: bytearray = bytearray()
			request = requests.get(self.image_url, stream=True)
			total_length = int(request.headers.get('content-length'))

			chunks: bytes
			for chunk in request.iter_content(chunk_size=1024):
				if chunk:
					image_content.extend(chunk)
					# DEBUG: simulate slow connection
					# time.sleep(0.002)

				if not self.post_progress_event(len(image_content) * 100 // total_length):
					return

			image = QImage()
			image.loadFromData(image_content)

			if not self.post_progress_event(100, image):
				return

		# TODO: pass meaningful error message to caller. See:
		#       https://requests.readthedocs.io/en/latest/api/#requests.RequestException
		except Exception as e:
			debug(e)
			if not self.post_progress_event(100, None):
				return


class ImageBrowser(QWidget):
	closed = pyqtSignal(QWidget)

	def __init__(self, image_urls: list[str], current_image: int):
		super().__init__()

		self.drag_origin: QPoint | None = None
		self.zoom_origin: QPoint | None = None
		self.scale_factor = 1.0
		self.image_offset = QPoint(0, 0)

		self.window_title = "Mammudon Image Browser"
		loadUi(os.path.join(os.path.dirname(__file__), "ui", "image_browser.ui"), self)

		self.widget: QWidget | None = None

		settings = QSettings()
		settings.beginGroup("ImageBrowserWindow")
		self.resize(QSize(settings.value("size", QSize(1024, 768))))
		self.move(QPoint(settings.value("pos", QPoint(100, 100))))
		settings.endGroup()

		self.image_scroll_area: QScrollArea = self.findChild(QScrollArea, "imageScrollArea")
		self.image_label: QLabel = self.findChild(QLabel, "imageLabel")
		self.status_bar_label: QLabel = self.findChild(QLabel, "statusBarLabel")

		self.browse_previous: QPushButton = self.findChild(QPushButton, "browsePrevious")
		self.browse_next: QPushButton = self.findChild(QPushButton, "browseNext")

		self.progressBar: QProgressBar = self.findChild(QProgressBar, "progressBar")

		# without this, keyboard events for cursor keys are seen as ShortcutOverride events instead
		self.grabKeyboard()

		if len(image_urls) == 1:
			self.browse_previous.hide()
			self.browse_next.hide()
		else:
			self.browse_previous.show()
			self.browse_next.show()

			self.image_scroll_area.lower()
			self.browse_previous.raise_()
			self.browse_next.raise_()

			self.browse_previous.clicked.connect(self.browse)
			self.browse_next.clicked.connect(self.browse)

		layout: QLayout = self.layout()
		layout: QGridLayout

		# re-layout the image widget to span the whole grid layout, since Designer
		# does not let us do it
		layout.removeWidget(self.image_scroll_area)
		layout.addWidget(self.image_scroll_area, 0, 0, -1, -1)

		layout.removeWidget(self.progressBar)
		layout.addWidget(self.progressBar, 0, 2, 1, 1)

		self.current_image: int = 0
		self.current_image_url: str = ""

		self.status_bar_timer = 0

		# we use a simple list of urls to keep the image ordering intact
		self.image_urls: list[str] = []
		# this dict gets referenced by self.image_urls
		self.images: dict[str, dict[str, int | QImage | ImageLoader | None]] = {}

		url: str
		for url in image_urls:
			image_loader = ImageLoader(self, url)
			image_loader.start()

			self.image_urls.append(url)

			self.images[url] = {
				"progress": 0,
				"image": None,
				"loader": image_loader
			}

		self.set_current_image(self.image_urls[current_image])

	def set_current_image(self, image_url: str) -> None:
		self.current_image_url = image_url

		image_size: QSize
		image: QImage = self.images[image_url]["image"]

		if image:
			self.progressBar.hide()
			self.image_label.setText("")

			self.image_label.setPixmap(QPixmap.fromImage(image))
			self.image_scroll_area.setWidgetResizable(True)
			self.image_scroll_area.widget().adjustSize()

			if self.scale_factor > 3.0:
				self.scale_factor = 3.0
			elif self.scale_factor < 0.2:
				self.scale_factor = 0.2

			image_size = image.size() * self.scale_factor * self.scale_factor

		else:
			progress = self.images[image_url]["progress"]

			self.progressBar.setValue(progress)
			self.progressBar.show()

			if progress == 100:
				self.progressBar.hide()
				self.image_label.setText(
					'<html><head/><body><p><span style=" font-size:24pt; font-weight:700;">Error While Loading</span><br/></p>' +
					'<p><span style=" font-size:11pt;">' + self.current_image_url + '</span></p></body></html>')
			else:
				self.image_label.setText(
					'<html><head/><body><p><span style=" font-size:24pt; font-weight:700;">Loading ...</span><br/></p>' +
					'<p><span style=" font-size:11pt;">' + self.current_image_url + '</span></p></body></html>')

			image_size = self.image_label.geometry().size()

			if self.status_bar_timer:
				self.killTimer(self.status_bar_timer)
				self.status_bar_timer = 0
			self.status_bar_label.hide()

		canvas_size = self.image_scroll_area.contentsRect().size()
		image_size.scale(canvas_size * self.scale_factor * self.scale_factor, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

		image_rect = QRect(
			(canvas_size.width() - image_size.width()) // 2,
			(canvas_size.height() - image_size.height()) // 2,
			image_size.width(), image_size.height())

		if self.image_offset:
			image_rect.translate(self.image_offset)

		self.image_label.setGeometry(image_rect)
		self.setWindowTitle(self.window_title + " - " + self.current_image_url)

		if image:
			if self.status_bar_timer:
				self.killTimer(self.status_bar_timer)
				self.status_bar_timer = 0
			self.status_bar_timer = self.startTimer(3000)

			self.status_bar_label.setText(f"{image_rect.width()}x{image_rect.height()}")
			self.status_bar_label.show()

	def browse(self) -> None:
		self.drag_origin = None
		self.zoom_origin = None

		self.scale_factor = 1.0
		self.image_offset = QPoint(0, 0)

		if self.sender() == self.browse_previous:
			self.current_image -= 1
		elif self.sender() == self.browse_next:
			self.current_image += 1

		self.current_image = (self.current_image + len(self.image_urls)) % len(self.image_urls)
		self.set_current_image(self.image_urls[self.current_image])

	def zoom(self, direction: int) -> None:
		if not self.images[self.current_image_url]["image"]:
			return

		if direction == 0:
			# just return to the current image with zero zoom
			self.browse()
			return

		if direction > 0:
			self.scale_factor += 0.1
		else:
			self.scale_factor -= 0.1

		self.set_current_image(self.current_image_url)

	def resizeEvent(self, e: QResizeEvent) -> None:
		self.set_current_image(self.current_image_url)
		size = self.image_scroll_area.geometry().size()
		# self.status_bar_label.setFixedSize(size.width(), 24)
		self.status_bar_label.move(QPoint(0, size.height() - 24))
		e.accept()

	def event(self, e: QEvent) -> bool:
		event_type: QEvent.Type = e.type()
		match event_type:
			case QEvent.Type.User:
				e: ImageLoaderProgressEvent
				self.images[e.image_url()]["progress"] = e.progress()

				if e.progress() == 100:
					self.images[e.image_url()]["image"] = e.image()
					self.scale_factor = 1.0
					self.image_offset = QPoint(0, 0)

				self.set_current_image(self.current_image_url)
				return True

			case QEvent.Type.Timer:
				e: QTimerEvent
				if e.timerId() == self.status_bar_timer:
					self.status_bar_label.hide()
					self.killTimer(self.status_bar_timer)
					self.status_bar_timer = 0
				return True

			case QEvent.Type.Wheel:
				e: QWheelEvent
				if e.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
					self.zoom(e.pixelDelta().y())
					return True

				if e.pixelDelta().y() < 0:
					self.browse_next.click()
				else:
					self.browse_previous.click()
				return True

			case QEvent.Type.MouseButtonPress:
				e: QMouseEvent
				if e.button() == QtCore.Qt.MouseButton.LeftButton:
					self.drag_origin = e.pos() - self.image_offset
					return True

				if e.button() == QtCore.Qt.MouseButton.MiddleButton:
					self.zoom_origin = e.pos()
					return True

			case QEvent.Type.MouseButtonRelease:
				e: QMouseEvent
				if e.button() == QtCore.Qt.MouseButton.LeftButton and self.drag_origin:
					self.drag_origin = None
					return True

				if e.button() == QtCore.Qt.MouseButton.MiddleButton and self.zoom_origin:
					self.zoom_origin = None
					return True

			case QEvent.Type.MouseMove:
				e: QMouseEvent
				if not self.images[self.current_image_url]["image"]:
					return True

				if self.drag_origin:
					self.image_offset = e.pos() - self.drag_origin
					self.set_current_image(self.current_image_url)

					# debug("drag:", self.image_offset, self.drag_origin)
					return True

				if self.zoom_origin:
					self.scale_factor += float((e.pos().x() - self.zoom_origin.x()) + (e.pos().y() - self.zoom_origin.y())) / 400.0
					self.zoom_origin = e.pos()
					self.set_current_image(self.current_image_url)

					# debug("zoom:", self.scale_factor, self.zoom_origin)
					return True

			case QEvent.Type.MouseButtonDblClick:
				e: QMouseEvent
				if e.button() == QtCore.Qt.MouseButton.LeftButton:
					self.zoom(0)
					return True

			case QEvent.Type.KeyPress:
				e: QKeyEvent
				key = e.key()
				handled = True

				# browsing
				if key == QtCore.Qt.Key.Key_Left or key == QtCore.Qt.Key.Key_Backspace:
					if len(self.images) > 1:
						self.browse_previous.click()
				elif key == QtCore.Qt.Key.Key_Right or key == QtCore.Qt.Key.Key_Space:
					if len(self.images) > 1:
						self.browse_next.click()

				# zooming
				elif key == QtCore.Qt.Key.Key_Plus:
					self.zoom(1)
				elif key == QtCore.Qt.Key.Key_Minus:
					self.zoom(-1)
				elif key == QtCore.Qt.Key.Key_0:
					self.zoom(0)

				# exiting
				elif key == QtCore.Qt.Key.Key_Escape:
					self.close()
				else:
					handled = False

				if handled:
					return True

		# debug(e, event_type)
		return super().event(e)

	def closeEvent(self, e: QCloseEvent) -> None:
		settings = QSettings()
		settings.beginGroup("ImageBrowserWindow")
		settings.setValue("size", self.size())
		settings.setValue("pos", self.pos())
		settings.endGroup()

		# tell all threads to stop running
		image: dict[str, int | QImage | ImageLoader | None]
		for image in list(self.images.values()):
			image["loader"].requestInterruption()

		# make sure all threads stopped running
		# TODO: add .terminate() in case a thread takes too long to stop
		for image in list(self.images.values()):
			while image["loader"].isRunning():
				pass

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
