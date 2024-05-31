from PyQt6.QtCore import QObject, pyqtSignal

from mammudon.debugging import debug

from mastodon import StreamListener


# streaming listener
class Listener(StreamListener, QObject):
	incoming_post = pyqtSignal(object)
	incoming_notification = pyqtSignal(object)
	incoming_conversation = pyqtSignal(object)
	stream_aborted = pyqtSignal(str)

	def __init__(self, account_name: str, listener_name: str):
		super().__init__()

		self.listener_name: str = listener_name
		self.full_name = account_name + "/" + listener_name

		debug("streaming listener created for listener", self.full_name)

	def __del__(self):
		debug("__del__eting listener", self.full_name)

	def on_update(self, status: dict) -> None:
		debug("streaming status", status["id"], "received in listener", self.full_name)
		# self.timeline.post_queue[status["id"]] = status
		self.incoming_post.emit(status)

	# TODO: implement the rest of these
	def on_notification(self, notification) -> None:
		debug("notification received in listener", self.full_name, "-", notification)
		self.incoming_notification.emit(notification)

	def on_delete(self, status_id: int) -> None:
		debug("delete", status_id, "received in listener", self.full_name)

	def on_conversation(self, conversation) -> None:
		debug("conversation received in listener", self.full_name, "-", conversation)
		self.incoming_conversation.emit(conversation)

	def on_status_update(self, status_update) -> None:
		debug("status update", status_update["id"], "received in listener", self.full_name)

	def on_unknown_event(self, event_name: str, unknown_event=None) -> None:
		debug("unknown event", event_name, "received in listener", self.full_name, "-", unknown_event)

	def on_abort(self, err) -> None:
		# TODO: find out if we can tell which stream (local, user, ...) actually aborted
		debug("abort received in listener", self.full_name, "-", err)
		self.stream_aborted.emit(self.listener_name)

	def handle_heartbeat(self) -> None:
		debug("streaming listener heartbeat received for listener", self.full_name)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
