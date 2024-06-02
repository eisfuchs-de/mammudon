import _weakref
import sys
import weakref
import webbrowser

from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtWidgets import QMessageBox, QApplication, QWidget

from mammudon.account import Account
from mammudon.conversation_view import ConversationView
from mammudon.debugging import debug
from mammudon.format_post import format_conversation
from mammudon.listener import Listener
from mammudon.prefs import preferences
from mammudon.scroller import Scroller


class Conversations(Scroller):
	# debugging signatures for various dicts/lists
	DELETED_CONVERSATIONS_SIGNATURE = 7001
	CONVERSATIONS_SIGNATURE = 7003

	# debug housekeeping
	deleted_conversations: dict[int, _weakref.ReferenceType] = {}

	current_account = pyqtSignal(Account)
	unread_changed = pyqtSignal(bool)

	def __init__(self, account: Account, name: str, friendly_name: str):

		super().__init__(name=name, friendly_name=friendly_name, account=account)

		# dictionary to point conversation ids of this timeline to their ConversationView
		self.conversations: dict[int, ConversationView] = {}

		# contains conversation dicts by id, added e.g. from the account listener to be added to this timeline
		self.conversation_queue: dict[int, dict] = {}

		# DEBUG: add some signatures to these lists/dicts to be able to recognize them in gc.ger_references
		#        this is done here separately so the pycharm parser doesn't think these are the types we want
		self.deleted_conversations[self.DELETED_CONVERSATIONS_SIGNATURE] = weakref.ref(self)  # DEBUG: add debugging signature
		self.conversations[self.CONVERSATIONS_SIGNATURE] = ConversationView(conversation_id=1)  # DEBUG: add debugging signature

		self.reload_button.clicked.connect(self.on_reload_button_clicked)
		self.close_button.clicked.connect(self.on_close_button_clicked)

		# reload all conversations in the timeline instead of just from the newest post on
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
		debug("conversations.on_close_button_clicked", self.friendly_name)

		super().on_close_button_clicked()

		# TODO: report unread conversations (currently just sending 0)
		self.close_scroller.emit(self, 0)

		debug("closing scroller", self.friendly_name)

	def open_account_profile(self, account_id: int) -> None:
		self.open_profile.emit(account_id)

	def purge_conversation(self, id_to_delete: int) -> None:
		# debug("purging conversation", id_to_delete, "from tracking dict")

		if id_to_delete in self.conversations:
			self.deleted_conversations[id_to_delete] = weakref.ref(self.conversations[id_to_delete])
			del self.conversations[id_to_delete]
			debug("popped conversation", id_to_delete, "from timeline", self.scroller_name)

	# TODO
	def purge_conversations(self) -> None:
		pass

	# TODO: actions on posts shown in conversations, like boosts(?), favorites(?), replies, etc.

	# TODO: move into account ActionThread
	def delete_conversation(self, conversation_view: ConversationView) -> None:
		# remove the post from the internal list of root posts
		if conversation_view.id in self.conversations:
			del self.conversations[conversation_view.id]

		self.sender().deleteLater()   # tell qt to delete the ConversationView widget after returning from this signal
		try:
			self.mastodon.status_delete(conversation_view.id)  # delete actual conversation from mastodon
		except Exception as e:
			debug(e)
			breakpoint()

	@staticmethod
	def in_browser(conversation: dict) -> None:
		webbrowser.open(conversation["url"])

	def add_post(self, conversation: dict) -> ConversationView:
		conversation_id: int = conversation["id"]

		conversation_view: ConversationView = self.conversations.get(conversation_id, None)
		if not conversation_view:
			conversation_view = ConversationView(conversation_id=conversation_id)

			conversation_html = format_conversation(preferences.values, self.my_id, conversation)
			conversation_view.set_html(conversation_html)

			self.minimized.connect(conversation_view.minimized)
			conversation_view.mouse_wheel_event.connect(self.scroll_event)

			insert_index = self.timeline_view.layout().count()
			for index in range(insert_index):
				view: QWidget = self.timeline_view.layout().itemAt(index).widget()
				view: ConversationView
				if view.id < conversation_id:
					insert_index = index
					break

			debug("inserting conversation", conversation_id, "at index", insert_index)
			self.timeline_view.layout().insertWidget(insert_index, conversation_view)

			# save conversation in the conversations dictionary
			self.conversations[conversation_id] = conversation_view

		else:
			# TODO: is there something we need to do when we already know this conversation?
			#       update its html maybe, in case the referring post changed?
			# DEBUG: for testing conversations styling
			conversation_view.set_html(format_conversation(preferences.values, self.my_id, conversation))
			pass

		conversation_view.original_post = conversation

		return conversation_view

	def on_reload_button_clicked(self) -> None:
		self.full_reload = True
		self.update_timeline()

	def update_timeline(self) -> None:
		try:
			if self.full_reload:
				# first time loading or manual reload will pull in the whole timeline
				# TODO: unsure if the same timeline length should be applied to conversations
				timeline: list[dict] = self.mastodon.conversations(
					limit=preferences.values["max_timeline_length"]
				)
			else:
				# get the newest posts
				# TODO: unsure if the same timeline length should be applied to conversations
				timeline: list[dict] = self.mastodon.conversations(
					limit=preferences.values["max_timeline_length"], since_id=self.newest_id
				)

			if len(timeline):
				debug("Loaded timeline, length:", len(timeline), "for", self.friendly_name)

			for conversation in timeline:
				# record the newest automatically loaded post id
				if conversation["id"] > self.newest_id:
					self.newest_id = conversation["id"]
				self.queue_conversation(conversation)

			# DEBUG: test loading specific post IDs
			# requested_conversation = self.mastodon.conversations(max_id=XXXXXXXXXXXXXXX, min_id=XXXXXXXXXXXXXXX)
			# self.conversations_queue[requested_conversation["id"]] = requested_conversation

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
		self.add_queued_conversations()
		self.remaining_time_updater.start(5000)

		# DEBUG: check if all deleted conversations really get freed from memory
		# if self.deleted_posts:  # this is how it should be later without the debugging signature
		if len(self.deleted_conversations) > 1:  # take debugging signature into account
			debug("Lingering deleted posts: ", len(self.deleted_conversations))

			for deleted_conversation_id in list(self.deleted_conversations.keys()):
				# guard against DELETED_CONVERSATIONS_SIGNATURE debugging signature
				if deleted_conversation_id == self.DELETED_CONVERSATIONS_SIGNATURE:
					continue

				if self.deleted_conversations[deleted_conversation_id]():
					debug(deleted_conversation_id, sys.getrefcount(self.deleted_conversations[deleted_conversation_id]()))
				else:
					# weakref is None, so remove it from the list
					del self.deleted_conversations[deleted_conversation_id]

			debug("------------------")

			# breakpoint()

	def queue_conversation(self, conversation: dict) -> None:
		debug("Conversations - queue_conversation:", conversation)
		self.conversation_queue[conversation["id"]] = conversation

	# TODO: probably needs grouping by distinct conversations instead of having a flat list
	def add_queued_conversations(self) -> None:
		# use a copy of the queue so a possible streaming thread in the background does not
		# mess with it while we are working at inserting the queued conversations
		insert_queue = self.conversation_queue.copy()
		if insert_queue:
			# restart the update timer, so we only poll updates when
			# there was no streaming content until the update timeout
			self.update_timer.start(self.refresh_time)
			# update the button, too
			self.reload_button.setText(str(self.update_timer.remainingTime() // 1000))

			for conversation in insert_queue.values():
				debug("adding queued conversation", conversation["id"], "in timeline", self.scroller_name)
				self.add_post(conversation)
				self.conversation_queue.pop(conversation["id"])
				QApplication.instance().processEvents()

		if len(self.conversation_queue):
			debug("conversation queue not yet empty, probably a thread put something in it while we were adding ... will be in the next round - in timeline", self.scroller_name)
		# else:
		# 	debug("conversation queue empty, good! - in timeline", self.scroller_name)

		self.purge_conversations()

	def connect_to_stream_listener(self, stream_name: str, stream_listener: Listener) -> None:
		if stream_name == self.scroller_name:
			stream_listener.incoming_conversation.connect(self.queue_conversation)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
