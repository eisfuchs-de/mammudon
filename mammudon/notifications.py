import _weakref
import sys
import weakref
import webbrowser

from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtWidgets import QMessageBox, QApplication, QWidget

from mammudon.account import Account
from mammudon.debugging import debug
from mammudon.format_post import format_notification
from mammudon.listener import Listener
from mammudon.notification_view import NotificationView
from mammudon.prefs import preferences
from mammudon.scroller import Scroller


class Notifications(Scroller):
	# debugging signatures for various dicts/lists
	DELETED_NOTIFICATIONS_SIGNATURE = 9001
	NOTIFICATIONS_SIGNATURE = 9003

	# debug housekeeping
	deleted_notifications: dict[int, _weakref.ReferenceType] = {}

	current_account = pyqtSignal(Account)
	unread_changed = pyqtSignal(bool)

	def __init__(self, account: Account, name: str, friendly_name: str):

		super().__init__(name=name, friendly_name=friendly_name, account=account)

		# dictionary to point notification ids of this timeline to their NotificationView
		self.notifications: dict[int, NotificationView] = {}

		# contains notification dicts by id, added e.g. from the account listener to be added to this timeline
		self.notification_queue: dict[int, dict] = {}

		# DEBUG: add some signatures to these lists/dicts to be able to recognize them in gc.ger_references
		#        this is done here separately so the pycharm parser doesn't think these are the types we want
		self.deleted_notifications[self.DELETED_NOTIFICATIONS_SIGNATURE] = weakref.ref(self)  # DEBUG: add debugging signature
		self.notifications[self.NOTIFICATIONS_SIGNATURE] = NotificationView(notification_id=1)  # DEBUG: add debugging signature

		# connect signals
		self.reload_button.clicked.connect(self.on_reload_button_clicked)  # TODO
		self.close_button.clicked.connect(self.on_close_button_clicked)

		# reload all notifications in the timeline instead of just from the newest post on
		self.full_reload = True

		# 1 minute timeline auto update - TODO: make configurable
		self.refresh_time = 60 * 1000

		self.newest_id = 0

		# timeline poll timer
		self.update_timer = QTimer()
		self.update_timer.timeout.connect(self.update_timeline)
		self.update_timer.setSingleShot(True)

		# first timeline update shortly after creating the container, will be adjusted in the reload function
		self.update_timer.start(1000)

		# update the remaining time display on the reload button periodically
		self.remaining_time_updater = QTimer()
		self.remaining_time_updater.timeout.connect(self.remaining_time)
		self.remaining_time_updater.setSingleShot(True)
		# timer gets started in self.on_reload_button_clicked() first, and then in each self.remaining_time() call

	def __del__(self) -> None:
		debug("__del__eting timeline", self.scroller_name, "of account", self.account.account_username)

	def on_close_button_clicked(self) -> None:
		debug("notifications.on_close_button_clicked", self.friendly_name)

		super().on_close_button_clicked()

		# TODO: report unread notifications (currently just sending 0)
		self.close_scroller.emit(self, 0)

		debug("closing scroller", self.friendly_name)

	def open_account_profile(self, account_id: int) -> None:
		self.open_profile.emit(account_id)

	def purge_notification(self, id_to_delete: int) -> None:
		# debug("purging notification", id_to_delete, "from tracking dict")

		if id_to_delete in self.notifications:
			self.deleted_notifications[id_to_delete] = weakref.ref(self.notifications[id_to_delete])
			del self.notifications[id_to_delete]
			debug("popped notification", id_to_delete, "from timeline", self.scroller_name)

	# TODO
	def purge_notifications(self) -> None:
		pass

	# TODO: actions on posts shown in notifications, like boosts, favorites, replies, etc.

	def delete_notification(self, notification_view: NotificationView) -> None:
		# remove the post from the internal list of root posts
		if notification_view.id in self.notifications:
			del self.notifications[notification_view.id]

		self.sender().deleteLater()   # tell qt to delete the NotificationView widget after returning from this signal
		try:
			# TODO: move into ActionThread of the Account class
			self.mastodon.notifications_dismiss(notification_view.id)  # delete actual notification from mastodon
		except Exception as e:
			debug(e)
			breakpoint()

	@staticmethod
	def in_browser(notification: dict) -> None:
		webbrowser.open(notification["url"])

	def add_post(self, notification: dict) -> NotificationView:
		notification_id: int = notification["id"]

		notification_view: NotificationView = self.notifications.get(notification_id, None)
		if not notification_view:
			notification_view = NotificationView(notification_id=notification_id)

			# mastodon.notifications()[0]
			# # Returns the following dictionary:
			# {
			#     'id': # id of the notification
			#     'type': # "mention", "reblog", "favourite", "follow", "poll" or "follow_request"
			#     'created_at': # The time the notification was created
			#     'account': # User dict of the user from whom the notification originates
			#     'status': # In case of "mention", the mentioning status
			#               # In case of reblog / favourite, the reblogged / favourited status
			# }

			notification_html = format_notification(preferences.values, self.my_id, notification)
			notification_view.set_html(notification_html)
			# notification_view.set_html(
			# 	notification["type"] + "\n" +
			# 	notification["account"]["acct"] + "\n" +
			# 	notification.get("status", {}).get("content", "")  # follows don't have "status"
			# )

			self.minimized.connect(notification_view.minimized)
			notification_view.mouse_wheel_event.connect(self.scroll_event)

			insert_index = self.timeline_view.layout().count()
			for index in range(insert_index):
				view: QWidget = self.timeline_view.layout().itemAt(index).widget()
				view: NotificationView
				if view.id < notification_id:
					insert_index = index
					break

			debug("inserting notification", notification_id, "at index", insert_index)
			self.timeline_view.layout().insertWidget(insert_index, notification_view)

			# save notification in the notifications dictionary
			self.notifications[notification_id] = notification_view

		else:
			# TODO: is there something we need to do when we already know this notification?
			#       update its html maybe, in case the referring post changed?
			# DEBUG: for testing notifications styling
			notification_view.set_html(format_notification(preferences.values, self.my_id, notification))
			pass

		notification_view.set_original_post(notification)

		return notification_view

	def on_reload_button_clicked(self) -> None:
		self.full_reload = True
		self.update_timeline()

	def update_timeline(self) -> None:
		try:
			if self.full_reload:
				# first time loading or manual reload will pull in the whole timeline
				timeline: list[dict] = self.mastodon.notifications(
					limit=preferences.values["max_timeline_length"]
				)
			else:
				# get the newest posts
				timeline: list[dict] = self.mastodon.notifications(
					limit=preferences.values["max_timeline_length"], since_id=self.newest_id
				)

			if len(timeline):
				debug("Loaded timeline, length:", len(timeline), "for", self.friendly_name)

			for notification in timeline:
				# record the newest automatically loaded post id
				if notification["id"] > self.newest_id:
					self.newest_id = notification["id"]
				self.queue_notification(notification)

			# DEBUG: test loading specific post IDs
			# requested_notification = self.mastodon.notifications(id=XXXXXXXXXXXXXXX)
			# self.notifications_queue[requested_notification["id"]] = requested_notification

		except Exception as e:
			str_args: list[str] = []
			for x in e.args:
				str_args.append(str(x))
			QMessageBox.information(self, "Mammudon", "Could not reload timeline " + self.friendly_name + ":\n" + " - ".join(str_args))

		self.update_timer.start(self.refresh_time)

		# pull the queued posts into our timeline right after
		self.remaining_time_updater.start(10)

		self.full_reload = False

	def remaining_time(self) -> None:
		remaining_update_time = self.update_timer.remainingTime()
		if remaining_update_time < 0:
			remaining_update_time = 0
		self.reload_button.setText(str(remaining_update_time // 1000))
		self.add_queued_notifications()
		self.remaining_time_updater.start(5000)

		# DEBUG: check if all deleted notifications really get freed from memory
		# if self.deleted_posts:  # this is how it should be later without the debugging signature
		if len(self.deleted_notifications) > 1:  # take debugging signature into account
			debug("Lingering deleted posts: ", len(self.deleted_notifications))

			for deleted_notification_id in list(self.deleted_notifications.keys()):
				# guard against "deleted_notifications" debugging signature
				if deleted_notification_id == self.DELETED_NOTIFICATIONS_SIGNATURE:
					continue

				if self.deleted_notifications[deleted_notification_id]():
					debug(deleted_notification_id, sys.getrefcount(self.deleted_notifications[deleted_notification_id]()))
				else:
					# weakref is None, so remove it from the list
					del self.deleted_notifications[deleted_notification_id]

			debug("------------------")

			# breakpoint()

	def queue_notification(self, notification: dict) -> None:
		debug("Notifications - queue_notification:", notification)
		self.notification_queue[notification["id"]] = notification

	def add_queued_notifications(self) -> None:
		# use a copy of the queue so a possible streaming thread in the background does not
		# mess with it while we are working at inserting the queued notifications
		insert_queue = self.notification_queue.copy()
		if insert_queue:
			# restart the update timer, so we only poll updates when
			# there was no streaming content until the update timeout
			self.update_timer.start(self.refresh_time)
			# update the button, too
			self.reload_button.setText(str(self.update_timer.remainingTime() // 1000))

			for notification in insert_queue.values():
				debug("adding queued notification", notification["id"], "in timeline", self.scroller_name)
				self.add_post(notification)
				self.notification_queue.pop(notification["id"])
				QApplication.instance().processEvents()

		if len(self.notification_queue):
			debug("notification queue not yet empty, probably a thread put something in it while we were adding ... will be in the next round - in timeline", self.scroller_name)
		# else:
		# 	debug("notification queue empty, good! - in timeline", self.scroller_name)

		self.purge_notifications()

	def connect_to_stream_listener(self, stream_name: str, stream_listener: Listener) -> None:
		if stream_name == self.scroller_name:
			stream_listener.incoming_notification.connect(self.queue_notification)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
