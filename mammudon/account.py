# TODO: Proper GUI error messages
# TODO: move more server calls here into non blocking operation thread
import time

from PyQt6.QtCore import pyqtSignal, QTimer, QObject, QThread
from PyQt6.QtWidgets import QWidget, QMessageBox

from mastodon import Mastodon, CallbackStreamListener

from mammudon.debugging import debug
from mammudon.listener import Listener
from mammudon.prefs import preferences


class ActionThread(QThread):
	def __init__(self, mastodon: Mastodon, action_queue: list[dict]):
		super().__init__()
		self.mastodon = mastodon
		self.action_queue = action_queue

	def run(self) -> None:
		debug("ActionThread running ...")

		while self.action_queue:
			# DEBUG: simulate slow server, so we can see that threading won't block the UI
			# time.sleep(6.0)

			action_item = self.action_queue.pop()
			try:
				action: str = action_item["action"]
				status_id: int = action_item["status_id"]
				callback = action_item["callback"]

				status: dict

				if action == "favourite":
					if action_item["favourited"]:
						status = self.mastodon.status_favourite(status_id)
					else:
						status = self.mastodon.status_unfavourite(status_id)

					callback(status_id, {"action": "favourite", "result": status})

				elif action == "bookmark":
					if action_item["bookmarked"]:
						status = self.mastodon.status_bookmark(status_id)
					else:
						status = self.mastodon.status_unbookmark(status_id)

					callback(status_id, {"action": "delete", "result": status})

				elif action == "delete":
					status = self.mastodon.status_delete(status_id)
					callback(status_id, {"action": "delete", "result": status})

				elif action == "mute":
					if action_item["muted"]:
						status = self.mastodon.status_mute(status_id)
					else:
						status = self.mastodon.status_unmute(status_id)
					callback(status_id, {"action": "mute", "result": status})

				elif action == "boost":
					if action_item["boosted"]:
						status = self.mastodon.status_reblog(status_id)
					else:
						status = self.mastodon.status_unreblog(status_id)
					callback(status_id, {"action": "boost", "result": status})

				elif action == "reload":
					status: dict = self.mastodon.status(status_id)
					callback(status_id, {"action": "reload", "result": status})

				elif action == "reload_notification":
					notification: dict = self.mastodon.notifications(id=status_id)
					debug(notification)
					callback(status_id, {"action": "reload_notification", "result": notification})

				# TODO: conversations work differently (see https://mastodonpy.readthedocs.io/en/stable/02_return_values.html#conversation-dicts)
				#       so this here probably just doesn't work yet
				elif action == "reload_conversation":
					conversation: list = self.mastodon.conversations(min_id=status_id, max_id=status_id)
					callback(status_id, {"action": "reload_conversation", "result": conversation})
				else:
					debug("unknown action item", action_item)
					breakpoint()

			except Exception as e:
				str_args: list[str] = []
				for x in e.args:
					str_args.append(str(x))
				QMessageBox.information(None, "Mammudon", "Could not boost post:\n" + str_args[0] + "\n" + " - ".join(str_args[1:]))
				breakpoint()

		debug("ActionThread finished!")


class Account(QObject):
	# signals
	login_status = pyqtSignal(str)
	relationship_update = pyqtSignal(object)  # dict()
	stream_listener_ready = pyqtSignal(str, Listener)  # (timeline_name, Listener)

	# errors
	errors = {
		"success": "Success",
		"create_app": "Error while creating client ID and secret",
		"create_endpoint": "Error while creating API endpoint with client ID and secret",
		"login": "Error while logging in with user name and password"
	}

	def __init__(self, account_data: dict):
		super().__init__()

		self.mastodon: Mastodon | None = None
		self.health_timer: QTimer | None = None
		self.account = {}
		self.instance = {}
		self.timelines: dict[str, dict[str, str | bool | QWidget | Listener]] = {}
		self.custom_emojis: list[dict] = []
		self.is_composing_post: QWidget | None = None

		self.account_login = account_data.get("login", "")
		self.account_autologin = account_data.get("autologin", False)
		self.account_password = account_data.get("password", "")
		self.account_instance = account_data.get("instance", "")
		self.account_feature_set = account_data.get("feature_set", preferences.values["feature_set"])

		self.account_username = "<unknown>"

		self.account_access_token = account_data.get("access_token", "")
		self.account_client_id = account_data.get("client_id", "")
		self.account_client_secret = account_data.get("client_secret")

		self.callback_stream: CallbackStreamListener | None = None

		# TODO: test streaming modes, uncomment one of these at a time, so far "callback" did not work at all
		self.stream_mode = "stream"
		# self.stream_mode = "callback"

		self.action_queue: list[dict] = []
		self.action_thread: ActionThread | None = None

	def __del__(self):
		debug("__del__eting account", self.account_username)

	def login(self, drop_access_tokens=False):
		debug("Trying to log in to", self.account_instance, "using", self.account_login, ": ***********")

		# if we don't have a client_id or a client_secret, (re-)create our app on the instance
		if drop_access_tokens or (not self.account_client_id) or (not self.account_client_secret):
			try:
				debug("Trying to register new client credentials ...")
				(self.account_client_id, self.account_client_secret) = Mastodon.create_app(
					"Mammudon",
					website=self.account_instance + "@" + self.account_login,
					api_base_url=self.account_instance)
			except Exception as e:
				debug("Error registering new app credentials on", self.account_instance, e)
				self.login_status.emit("create_app")
				return

			debug("New client credentials obtained successfully.")

		# if we already have an access token for this account, try logging in immediately
		if self.account_access_token and not drop_access_tokens:
			try:
				debug("Trying to log in with saved access token ...")
				self.mastodon = Mastodon(
					access_token=self.account_access_token,
					client_id=self.account_client_id,
					client_secret=self.account_client_secret,
					user_agent="Mammudon",
					feature_set=self.account_feature_set,
					api_base_url=self.account_instance)

			except Exception as e:
				debug("Login with saved access token failed:", e)

		# not logged in yet, try harder
		if drop_access_tokens or (not self.mastodon):
			# create endpoint API with client ID and client secret to allow a login
			try:
				debug("Trying to create endpoint with saved client credentials ...")
				self.mastodon = Mastodon(
					client_id=self.account_client_id,
					client_secret=self.account_client_secret,
					user_agent="Mammudon",
					feature_set=self.account_feature_set,
					api_base_url=self.account_instance)

			except Exception as e:
				debug("Endpoint creation with saved client credentials failed:", e)
				self.login_status.emit("create_endpoint")
				return

			# log in regularly with username and password to obtain an access token
			try:
				debug("Trying to log in with new user credentials ...")
				self.account_access_token = self.mastodon.log_in(
					self.account_login,
					self.account_password)
			except Exception as e:
				debug("Login with new user credentials failed:", e)
				debug("Error logging in user", self.account_login, "on", self.account_instance)
				self.login_status.emit("user_login")
				return

			debug("Logged in", self.account_login, "on", self.account_instance)

		# TODO: pretty display
		try:
			self.account = self.mastodon.me()
			debug("account dict", self.account)
		except Exception as e:
			debug(e)
			# TODO: find out how to get the exact error code
			self.login_status.emit("revoked")
			return

		self.instance = self.mastodon.instance()
		debug("instance dict", self.instance)

		self.account_username = "@" + self.account["username"] + "@" + self.instance["uri"]
		self.custom_emojis = self.mastodon.custom_emojis()

		self.health_timer = QTimer()
		self.health_timer.timeout.connect(self.health)
		self.health_timer.start(10 * 60 * 1000)

		debug(self.mastodon.app_verify_credentials())

		self.login_status.emit("success")

		self.action_thread: ActionThread = ActionThread(self.mastodon, self.action_queue)

	def add_timeline(self, name: str, friendly_name: str, scroller: QWidget) -> None:
		if name in self.timelines:
			debug("account.add_timeline(): Account", self.account_username, "already has a timeline named", name)
			breakpoint()
			return

		self.timelines[name] = {
			"friendly_name": friendly_name,
			"scroller": scroller,
			"stream": None,
			"listener": None
		}

		self.restart_stream(name)

		debug("account.add_timeline(): added timeline stream named", name, "to account", self.account_username)

	def remove_timeline(self, name: str):
		if name not in self.timelines:
			debug("account.remove_timeline(): Account", self.account_username, "does not have a timeline named", name)
			breakpoint()
			return

		stream_handle = self.timelines[name]["stream"]
		if stream_handle:
			debug("stream handler", self.account_username + "/" + name, "alive?", stream_handle.is_alive())
			debug("stream handler", self.account_username + "/" + name, "running?", stream_handle.is_receiving())
			debug("closing stream handler",  self.account_username + "/" + name, stream_handle.close())
			debug("stream handler", self.account_username + "/" + name, "alive?", stream_handle.is_alive())

			for _ in range(10):
				if stream_handle.is_alive():
					debug("stream handler", self.account_username + "/" + name, "alive?", stream_handle.is_alive())
					debug("stream handler", self.account_username + "/" + name, "running?", stream_handle.is_receiving())
					time.sleep(0.25)
				else:
					break

		del self.timelines[name]["listener"]
		del self.timelines[name]["stream"]
		del self.timelines[name]

		debug("account.remove_timeline(): removed timeline named", name, "from account", self.account_username)

		# TODO: log out when no timeline is left(?) or when home timeline is closed(?)

	def access_token(self) -> str:
		return self.account_access_token

	def health(self) -> None:
		try:
			if self.mastodon.stream_healthy():
				return

			debug("streaming api not healthy!")

		except Exception as e:
			debug("Error while checking streaming health status:", e)

	def restart_stream(self, stream_name: str) -> None:
		if self.stream_mode == "stream":
			# TODO: make "Stream" its own class(?)
			stream_listener = self.timelines[stream_name]["listener"]

			if not stream_listener:
				stream_listener = Listener(self.account_username, stream_name)
				stream_listener.stream_aborted.connect(self.restart_stream)
				self.timelines[stream_name]["listener"] = stream_listener

				debug("Added streaming", stream_name, "listener to account", self.account_username)

			try:
				stream_handle = None

				if stream_name == "home" or stream_name == "notifications":
					stream_handle = self.mastodon.stream_user(
						stream_listener, run_async=True, reconnect_async=True
					)
				elif stream_name == "local":
					# From the 1.8.1 documentation: Please use :ref:`stream_public() <stream_public()>` with parameter
					# `local` set to True instead.
					# self.mastodon.stream_local(listener=self.listener, run_async=True)
					stream_handle = self.mastodon.stream_public(
						stream_listener, run_async=True, local=True, reconnect_async=True, timeout=300
					)
				elif stream_name == "public":
					stream_handle = self.mastodon.stream_public(
						stream_listener, run_async=True, reconnect_async=True, timeout=300
					)

				self.timelines[stream_name]["stream"] = stream_handle

				self.stream_listener_ready.emit(stream_name, stream_listener)

			except Exception as e:
				debug("Error while setting up stream_user for account", self.account_username, " - ", e)
			return

		# TODO: so far I have not been able to get this one to do anything at all
		elif self.stream_mode == "callback":
			if self.callback_stream:
				return

			debug("Adding callback listener to account", self.account_username)

			try:
				self.callback_stream = CallbackStreamListener(
					update_handler=self.multihandler,
					local_update_handler=self.multihandler,
					delete_handler=self.multihandler,
					notification_handler=self.multihandler,
					conversation_handler=self.multihandler,
					unknown_event_handler=self.multihandler,
					status_update_handler=self.multihandler,
					filters_changed_handler=self.multihandler,
					announcement_handler=self.multihandler,
					announcement_reaction_handler=self.multihandler,
					announcement_delete_handler=self.multihandler,
					encryted_message_handler=self.multihandler)
			except Exception as e:
				debug(e)
			return

	# TODO: so far I have not been able to get this one to do anything at all
	def multihandler(self, unknown_1, unknown_2=None) -> None:
		debug("Callback Listener multihandler for account", self.account_username, unknown_1, unknown_2)

	# TODO
	def log_out(self) -> None:
		for timeline_name in self.timelines:
			self.remove_timeline(timeline_name)

	def status_action(self, action: dict) -> None:
		self.action_queue.append(action)
		self.action_thread.start()

	# TODO: move to ActionThread
	def follow_account(self, account_id: object) -> None:
		try:
			relationship = self.mastodon.account_follow(account_id)
			debug(relationship)
			self.relationship_update.emit(relationship)
		except Exception as e:
			debug(e)

	# TODO: move to ActionThread
	def notify_account(self, account_id: object, notify: bool) -> None:
		try:
			relationship = self.mastodon.account_follow(account_id, notify=notify)
			debug(relationship)
			self.relationship_update.emit(relationship)
		except Exception as e:
			debug(e)

	# TODO: move to ActionThread
	def unfollow_account(self, account_id: object) -> None:
		try:
			relationship = self.mastodon.account_unfollow(account_id)
			debug(relationship)
			self.relationship_update.emit(relationship)
		except Exception as e:
			debug(e)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
