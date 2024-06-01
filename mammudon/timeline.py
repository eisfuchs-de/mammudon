import _weakref
import sys
import weakref
import webbrowser

from PyQt6 import QtCore
from PyQt6.QtCore import QTimer, QObject, QEvent
from PyQt6.QtWidgets import QWidget, QApplication, QLayout, QMessageBox

from mammudon.account import Account
from mammudon.debugging import debug
from mammudon.listener import Listener
from mammudon.prefs import preferences, format_post

from mammudon.history import History
from mammudon.scroller import Scroller
from mammudon.status_post import PostView


class Timeline(Scroller):
	# debugging signatures for various dicts/lists
	DELETED_POSTS_SIGNATURE = 8001
	THREADED_POSTS_SIGNATURE = 8002
	POSTS_SIGNATURE = 8003
	WANTED_PARENTS_SIGNATURE = "999999"
	# debug housekeeping
	deleted_posts: dict[int, _weakref.ReferenceType] = {}

	def __init__(
			self,
			account: Account,
			name: str,
			friendly_name: str):

		super().__init__(name=name, friendly_name=friendly_name, account=account)

		self.history_view: History | None = None

		# dictionary to point unthreaded post ids of this timeline to their PostView
		self.posts: dict[int, PostView] = {}

		# dictionary to point threaded post ids of this timeline to their PostView, separate to be able to
		# limit the timeline to X unthreaded posts
		self.threaded_posts: dict[int, PostView] = {}

		# keep track of parent IDs that are not (yet) added to the timeline but are wanted by threaded posts
		self.wanted_parents: dict[int, list] = {}

		# contains status dicts by id, added e.g. from the account listener to be added to this timeline
		self.post_queue: dict[int, dict] = {}

		# DEBUG: add some signatures to these lists/dicts to be able to recognize them in gc.ger_references
		#        this is done here separately so the pycharm parser doesn't think these are the types we want
		self.deleted_posts[self.DELETED_POSTS_SIGNATURE] = weakref.ref(self)  # DEBUG: add debugging signature
		self.threaded_posts[self.THREADED_POSTS_SIGNATURE] = PostView(authored_by_me=True, post_id=0)  # DEBUG: add debugging signature
		self.posts[self.POSTS_SIGNATURE] = PostView(authored_by_me=True, post_id=1)  # DEBUG: add debugging signature

		# connect signals
		self.reload_button.clicked.connect(self.on_reload_button_clicked)
		self.close_button.clicked.connect(self.on_close_button_clicked)

		# catch mouse clicks on the timeline icon to jump to next unread post
		self.timeline_icon_widget.installEventFilter(self)

		# reload all posts in the timeline instead of just from the newest post on
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

	def eventFilter(self, o: QObject, e: QEvent) -> bool:
		if o is not self.timeline_icon_widget:
			return False

		# catch mouse clicks on the timeline icon to jump to next unread post
		if e.type() == QtCore.QEvent.Type.MouseButtonRelease:
			self.scroll_to_next_unread()
			return False

		return False

	def find_unread_offsets(self, layout: QLayout, current_y: int) -> int:
		if not layout:
			return 0

		num_posts = layout.count()
		for current_post in range(num_posts):
			post_view: QWidget = layout.itemAt(current_post).widget()
			if not post_view:
				continue

			# first check if the post itself is unread and already past current_y
			post_view: PostView
			if post_view.unread:
				# TODO: find out why I have to subtract the post_view.pos().y() value to make it work ...
				y_offset = post_view.mapTo(self.timeline_view, post_view.pos()).y() - post_view.pos().y()
				if y_offset > current_y:
					# this is our next unread post
					return y_offset

			# now check the posts nested underneath this post recursively
			y_offset = self.find_unread_offsets(post_view.threaded_layout, current_y)

			# if they come back as being past current_y ...
			if y_offset > current_y:
				# ... this is our next unread post
				return y_offset

		return 0

	def scroll_to_next_unread(self) -> None:
		scrollbar = self.scroll_area.verticalScrollBar()
		y_offset = self.find_unread_offsets(self.timeline_view.layout(), scrollbar.value())

		if y_offset:
			scrollbar.setValue(y_offset)

	def open_account_profile(self, account_id: int) -> None:
		self.open_profile.emit(account_id)

	# purge a single post, recursively purging all its threaded posts
	def purge_post(self, id_to_delete: int) -> None:
		# same post can be in multiple tracking dicts (posts + unparented at least) so just try
		# to clean the post out of all of them
		popped = False
		if id_to_delete in self.posts:
			self.deleted_posts[id_to_delete] = weakref.ref(self.posts[id_to_delete])
			del self.posts[id_to_delete]
			debug("popped post", id_to_delete, "from root posts in timeline", self.scroller_name)
			popped = True

		if id_to_delete in self.threaded_posts:
			self.deleted_posts[id_to_delete] = weakref.ref(self.threaded_posts[id_to_delete])
			del self.threaded_posts[id_to_delete]
			debug("popped post", id_to_delete, "from threaded posts in timeline", self.scroller_name)
			popped = True

		# delete post_view reference from wanted_parents[parents][post_view_id] sub list, too
		for post_id in list(self.wanted_parents.keys()):
			post_view_list = self.wanted_parents[post_id]
			for post_view in post_view_list:
				# guard against WANTED_PARENTS_SIGNATURE debugging signature in sub list
				if isinstance(post_view, str):
					continue

				if post_view.id == id_to_delete:
					self.deleted_posts[id_to_delete] = weakref.ref(post_view)
					post_view_list.remove(post_view)
					debug("popped post", id_to_delete, "from wanted_parents id sublist in timeline", self.scroller_name)
					break

		if id_to_delete in self.wanted_parents:
			self.deleted_posts[id_to_delete] = weakref.ref(self.wanted_parents[id_to_delete])
			del self.wanted_parents[id_to_delete]
			debug("popped post", id_to_delete, "from unthreaded posts in timeline", self.scroller_name)
			popped = True

		if not popped:
			debug("post", id_to_delete, "was not found in any tracking dict")

	def purge_posts(self) -> None:
		# TODO: purge old posts (customizable timeline length)
		# TODO: take boosts into account, the boost date or id is the sorting factor, not the original post
		# sorted_post_ids = list(self.posts.keys())
		sorted_post_ids: list[int] = []
		for post_item in self.posts.items():
			sorted_post_ids.append(post_item[1].original_post.get("mammudon_sort_id", 0))
		sorted_post_ids.sort()

		# public/local are excluded from the above rule for the amount of data coming in

		# TODO: only purge posts from the last one backwards until we hit one that is not marked as read,
		#       needs better logic here
		if self.window().isActiveWindow() or self.scroller_name in ["public", "local"]:
			while len(self.posts) > preferences.values["max_timeline_length"]:
				id_to_delete = sorted_post_ids.pop(0)

				# NOTE: protect dict signature
				if not id_to_delete:
					continue

				# DEBUG: do not delete our signature post
				if id_to_delete == self.POSTS_SIGNATURE:
					continue

				debug("timeline exceeds", preferences.values["max_timeline_length"], "... removing post view", id_to_delete)

				self.deleted_posts[id_to_delete] = weakref.ref(self.posts[id_to_delete])

				self.timeline_view.layout().removeWidget(self.posts[id_to_delete])
				self.posts[id_to_delete].destroy_view()

	def application_minimized(self) -> None:
		self.purge_posts()
		super().application_minimized()

	def load_post_context(self, post_id: int) -> None:
		try:
			context = self.mastodon.status_context(post_id)
			for post in context["ancestors"]:
				self.post_queue[post["id"]] = post
			for post in context["descendants"]:
				self.post_queue[post["id"]] = post
		except Exception as e:
			debug("could not fetch context for post", post_id, str(e))

	# probably not needed, was used for case-insensitive replace of emoji shortcodes
	# def replace_all(self, pattern, repl, string) -> str:
	# 	occurrences = re.findall(pattern, string, re.IGNORECASE)
	# 	for occurrence in occurrences:
	# 		debug("replacing", occurrence, "with", repl)
	# 		string = string.replace(occurrence, repl)
	# 	return string

	# TODO: boost with visibility
	def boost_post(self, post_view: PostView, checked: bool) -> None:
		post_view.boost_button.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "boost", "boosted": checked, "callback": self.status_update_callback})

	def favorite_post(self, post_view: PostView, checked: bool) -> None:
		post_view.favorite_button.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "favourite", "favourited": checked, "callback": self.status_update_callback})

	def bookmark_post(self, post_view: PostView, checked: bool) -> None:
		post_view.bookmark_button.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "bookmark", "bookmarked": checked, "callback": self.status_update_callback})

	# TODO: ask for confirmation
	def delete_post(self, post_view: PostView) -> None:
		post_view.post_action_delete.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "delete", "callback": self.status_update_callback})

	def mute_post(self, post_view: PostView, checked: bool) -> None:
		post_view.post_action_mute.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "mute", "muted": checked, "callback": self.status_update_callback})

	def reload_post(self, post_view: PostView) -> None:
		post_view.setEnabled(False)
		self.account.status_action({"status_id": post_view.id, "action": "reload", "callback": self.status_update_callback})

	def status_update_callback(self, post_id, update: dict) -> None:
		post_view: PostView
		if post_id not in self.posts:
			if post_id not in self.threaded_posts:
				return
			else:
				post_view = self.threaded_posts[post_id]
		else:
			post_view = self.posts[post_id]

		reload_post = True

		action: str = update["action"]
		if action == "boost":
			post_view.boost_button.setEnabled(update["result"]["reblogged"])
		elif action == "favourite":
			post_view.favorite_button.setChecked(update["result"]["favourited"])
			post_view.favorite_button.setEnabled(True)
		elif action == "bookmark":
			post_view.bookmark_button.setChecked(update["result"]["bookmarked"])
			post_view.bookmark_button.setEnabled(True)
		elif action == "delete":
			# this is probably redundant as the post view gets deleted right after
			post_view.post_action_delete.setEnabled(True)

			# remove the post from the internal list of root posts
			if post_view.id in self.posts:
				del self.posts[post_view.id]

			# remove the post from the internal list of threaded posts
			if post_view.id in self.threaded_posts:
				del self.threaded_posts[post_view.id]

			post_view.deleteLater()   # tell qt to delete the PostView widget after returning from this function
			reload_post = False
		elif action == "mute":
			post_view.post_action_mute.setEnabled(update["result"]["muted"])
			post_view.post_action_mute.setEnabled(True)
			reload_post = False
		elif action == "reload":
			post_view.setEnabled(True)
			self.queue_post(update["result"])
			# obviously we are already reloading this post, so don't reload it again
			reload_post = False
		else:
			debug("unknown status update", update)
			breakpoint()

		if reload_post:
			self.reload_post(post_view)

	@staticmethod
	def in_browser(post: dict) -> None:
		webbrowser.open(post["url"])

	def show_post_history(self, post_view: PostView) -> None:
		if not post_view.history:
			post_view.set_history(self.mastodon.status_history(post_view.id))

		self.history_view = History(None, post_view.history)
		self.history_view.show()

	def load_post_history(self, post_view: PostView) -> None:
		history = self.mastodon.status_history(post_view.id)
		post_view.set_history(history)

	def add_post(self, post: dict) -> PostView:
		# add our own parts to the post dict, prefixed by "mammudon", see below
		post_id = post["id"]

		boosted_by = {}
		if post["reblog"]:
			# keep this info around so PostView can check the URL on clicks
			boosted_by = post["account"]

			# TODO: does this mess up the sort order? It seems like it does
			# we want the boosted post inside the post
			post = post["reblog"]

			# store the boosted-by info inside the post, so we can read it later in PostView
			post["mammudon_boosted_by_id"] = boosted_by["id"]
			post["mammudon_boosted_by_acct"] = boosted_by["acct"]
			post["mammudon_boosted_by_url"] = boosted_by["url"]

		# add our own parts to the post dict, prefixed by "mammudon"
		post["mammudon_sort_id"] = post_id

		# check if this post is already in the timeline UI as un-parented or parented post
		post_view: PostView = self.posts.get(post["id"], None)
		if not post_view:
			post_view = self.threaded_posts.get(post["id"], None)

		post_has_new_content = True

		if not post_view:
			count_as_unread = (self.scroller_name not in ["public", "local"])

			# new post, create new PostView
			post_view: PostView = PostView(
				authored_by_me=(self.my_id == post["account"]["id"]),
				post_id=post["id"],
				threaded=post["in_reply_to_id"],
				count_as_unread=count_as_unread)

			self.minimized.connect(post_view.minimized)

			# TODO: not sure this is the best way to hook this up, this will just pop up the
			#       current NewPost() dialog if one is already open, and no reply stuff will
			#       be added to it. Should we just open multiple post dialogs?
			post_view.reply_to_post_clicked.connect(self.on_reply_to_post)

			# purge post from all tracking dicts when deleted
			post_view.was_destroyed.connect(self.purge_post)

			# "on_post_unread_changed" forwards unread change to whoever wants to know, mainly MainWindow
			post_view.is_unread.connect(self.on_post_unread_changed)

			# save original post to be able to compare the text with updates from the server
			post_view.set_original_post(post)
			post_view.set_unread(True)

			post_view.post_context_requested.connect(self.load_post_context)
			post_view.show_history_clicked.connect(self.show_post_history)
			post_view.boost_post.connect(self.boost_post)
			post_view.favorite_post.connect(self.favorite_post)
			post_view.bookmark_post.connect(self.bookmark_post)
			post_view.delete_post.connect(self.delete_post)
			post_view.mute_post.connect(self.mute_post)
			post_view.in_browser.connect(self.in_browser)
			post_view.reload_post.connect(self.reload_post)
			post_view.account_clicked.connect(self.open_account_profile)
			post_view.mouse_wheel_event.connect(self.scroll_event)

			# this logic looks like it could be simplified, but it turns out
			# it needs to take the parent_post_view into account twice
			# TODO: sort threaded posts by id
			in_reply_to_id = post["in_reply_to_id"]

			parent_post_view: PostView = self.posts.get(in_reply_to_id, None)
			if not parent_post_view:
				parent_post_view = self.threaded_posts.get(in_reply_to_id, None)

			# parent threaded post underneath parent post
			if in_reply_to_id and parent_post_view:
				# debug("threading post", post["id"], "under", in_reply_to_id)
				parent_post_view.threaded_layout.addWidget(post_view)
				parent_post_view.conversation_button.setChecked(True)
				parent_post_view.conversation_button.setEnabled(True)

				# save post in the threaded posts dictionary
				self.threaded_posts[post["id"]] = post_view
			else:
				# remember this post_view still needs a parent post
				if in_reply_to_id not in self.wanted_parents:
					# create a new list in wanted_parents posts for this parent post id, so replies
					# to it can be appended in the next step
					self.wanted_parents[in_reply_to_id] = []
					# DEBUG: add debugging signature to make it easier to recognize this list in gc.get_references
					self.wanted_parents[in_reply_to_id].append(self.WANTED_PARENTS_SIGNATURE)

				self.wanted_parents[in_reply_to_id].append(post_view)

				# remove threaded marker
				debug("threaded post", post["id"], "has no parent yet")
				post_view.set_no_parent_post()

				# disabled for the moment
				# if post["in_reply_to_id"] not in self.post_queue:
				# 	# try to load the parent post and add it to the queue to be inserted
				# 	try:
				# 		requested_post = self.mastodon.status(in_reply_to_id)
				# 		self.post_queue[requested_post["id"]] = requested_post
				# 	except Exception as e:
				# 		debug("could not fetch parent post", post["in_reply_to_id"], "for post", post["id"], e)
				# else:
				# 	debug("parent for threaded post", post["id"], "already queued, don't request to load it again")

			if not parent_post_view:
				# this is a root post or a thread that is waiting for a parent,
				# so insert it into the timeline by id
				sorted_post_ids: list[int] = []
				for post_item in self.posts.items():
					sorted_post_ids.append(post_item[1].original_post.get("mammudon_sort_id", 0))
				sorted_post_ids.sort(reverse=True)

				insert_index = 0
				for current_post_id in sorted_post_ids:
					if current_post_id < post["mammudon_sort_id"]:
						break
					insert_index += 1

				# debug("inserting post", post["id"], "at index", insert_index)
				self.timeline_view.layout().insertWidget(insert_index, post_view)

				# save post in the posts dictionary
				self.posts[post["id"]] = post_view

			# re-parent un-parented posts if this one was a wanted parent for them
			if post["id"] in self.wanted_parents:

				# it should always be in here
				if post["id"] in self.posts:

					seeking_parent: PostView
					for seeking_parent in self.wanted_parents[post["id"]]:
						# guard against WANTED_PARENTS_SIGNATURE debugging signature in sub list
						if isinstance(seeking_parent, str):
							continue

						found_parent: PostView = self.posts[post["id"]]

						debug("Re-parenting post", seeking_parent.id, "under", found_parent.id)
						self.timeline_view.layout().removeWidget(seeking_parent)
						found_parent.threaded_layout.addWidget(seeking_parent)
						found_parent.conversation_button.setChecked(True)
						found_parent.conversation_button.setEnabled(True)

						seeking_parent.set_threaded(True)

						# take newly parented post out of the post list
						if seeking_parent.id in self.posts:
							self.posts.pop(seeking_parent.id)
						else:
							debug("former un-parented post", seeking_parent.id, "was not found in self.posts for removal")

						# add newly parented post to the threaded posts list
						self.threaded_posts[seeking_parent.id] = seeking_parent

					# remove post id from list of wanted parents
					self.wanted_parents.pop(post["id"])

				else:
					debug("post id", post["id"], "was found in self.wanted_parents but is not in self.posts")

		else:
			# TODO: handle this with signals so we don't need to know where the post is threaded?

			# we already know this post, so check if the content has changed
			poll_is_same = True
			if post["poll"]:
				# Unfortunately, polls are not fully preserved in history, only the options are
				# TODO: need to compare only [options][titles] otherwise every vote sets this off
				poll_is_same = (
					# post["poll"]["expires_at"] == post_view.original_post["poll"]["expires_at"] and
					# post["poll"]["multiple"] == post_view.original_post["poll"]["multiple"] and
					post["poll"].get("voted", False) == post_view.original_post["poll"].get("voted", False) and
					post["poll"]["options"] == post_view.original_post["poll"]["options"] and
					post_view.original_post["poll"]["mammudon_refresh"] is False
				)

			if (
				post["content"] == post_view.original_post["content"] and
				post["spoiler_text"] == post_view.original_post["spoiler_text"] and
				post["sensitive"] == post_view.original_post["sensitive"] and
				post["emojis"] == post_view.original_post["emojis"] and
				post["media_attachments"] == post_view.original_post["media_attachments"] and
				poll_is_same
			):
				post_has_new_content = False
			else:
				# this is an edited post, so set it to unread and fetch its history
				self.load_post_history(post_view)
				post_view.set_unread(True)

		post_view.set_reply_count(post["replies_count"])
		post_view.set_boost_count(post["reblogs_count"])
		post_view.set_favorite_count(post["favourites_count"])

		# streaming posts don't provide these, so guard against NoneType
		post_view.set_boosted(post.get("reblogged", False))
		post_view.set_favorited(post.get("favourited", False))
		post_view.set_bookmarked(post.get("bookmarked", False))
		post_view.set_muted(post.get("muted", False))

		if post_has_new_content:
			post_html = format_post(preferences.values, post, boosted_by, self.account.custom_emojis)
			post_view.set_html(post_html)

			# remember the last known post content
			post_view.set_original_post(post)

		if post["poll"]:
			post["poll"]["mammudon_refresh"] = False  # internal flag for refreshing polls
			post_view.poll_vote.connect(self.on_poll_vote)
			post_view.poll_refresh.connect(self.on_poll_refresh)
			post_view.poll_show_results.connect(self.on_poll_show_results)

		return post_view

	def on_poll_vote(self, poll_id: int, voted_options: list[int]) -> None:
		post_view: QObject = self.sender()
		post_view: PostView

		try:
			# TODO: in an upcoming mastodon API version this will return the resulting votes in the poll, so
			#       switch to that when it becomes available
			# TODO: move this into the Account's ActionThread
			self.mastodon.poll_vote(int(poll_id), voted_options)
			requested_post = self.mastodon.status(post_view.id)
			self.post_queue[post_view.id] = requested_post

		except Exception as e:
			str_args: list[str] = []
			for x in e.args:
				str_args.append(str(x))
			QMessageBox.information(self, "Mammudon", "Could not vote in the poll:\n" + str_args[0] + "\n" + " - ".join(str_args[1:]))

	def on_poll_refresh(self, _poll_id: int) -> None:
		post_view: QObject = self.sender()
		post_view: PostView

		# we could use mastodon.poll(poll_id) to update the poll but that won't read changes in the text
		# or spoilers etc. so we just reload the whole post
		post_view.original_post["poll"]["mammudon_refresh"] = True
		try:
			requested_post = self.mastodon.status(post_view.id)
			self.post_queue[post_view.id] = requested_post

		except Exception as e:
			str_args: list[str] = []
			for x in e.args:
				str_args.append(str(x))
			QMessageBox.information(self, "Mammudon", "Could not refresh poll:\n" + str_args[0] + "\n" + " - ".join(str_args[1:]))

	# TODO: allow showing poll results and switching back to voting
	def on_poll_show_results(self, poll_id: int) -> None:
		post_view: QObject = self.sender()
		post_view: PostView
		debug(poll_id, post_view.original_post["id"])

	# slot
	def on_reply_to_post(self, post: dict) -> None:
		self.reply_to_post.emit(post, True)

	def on_reload_button_clicked(self) -> None:
		self.full_reload = True
		self.update_timeline()

	def update_timeline(self) -> None:
		try:
			if self.full_reload:
				# first time loading or manual reload will pull in the whole timeline
				timeline: list[dict] = self.mastodon.timeline(self.scroller_name, limit=preferences.values["max_timeline_length"], only_media=False)
			else:
				# get the newest posts
				timeline: list[dict] = self.mastodon.timeline(self.scroller_name, limit=preferences.values["max_timeline_length"], only_media=False, since_id=self.newest_id)

			if len(timeline):
				debug("Loaded timeline, length:", len(timeline), "for", self.friendly_name)

			for post in timeline:
				# record the newest automatically loaded post id
				if post["id"] > self.newest_id:
					self.newest_id = post["id"]
				self.queue_post(post)

			# DEBUG: test loading specific post IDs
			# requested_post = self.mastodon.status(XXXXXXXXXXXXXXX)
			# self.post_queue[requested_post["id"]] = requested_post

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
		self.add_queued_posts()
		self.remaining_time_updater.start(5000)

		# DEBUG: check if all deleted posts really get freed from memory
		# if self.deleted_posts:  # this is how it should be later without the debugging signature
		if len(self.deleted_posts) > 1:  # take debugging signature into account
			debug("Lingering deleted posts: ", len(self.deleted_posts))

			for deleted_post_id in list(self.deleted_posts.keys()):
				# guard against "deleted_posts" debugging signature
				if deleted_post_id == self.DELETED_POSTS_SIGNATURE:
					continue

				if self.deleted_posts[deleted_post_id]():
					debug(deleted_post_id, sys.getrefcount(self.deleted_posts[deleted_post_id]()))
				else:
					# weakref is None, so remove it from the list
					del self.deleted_posts[deleted_post_id]

			debug("------------------")

			# breakpoint()

	def queue_post(self, post: dict) -> None:
		self.post_queue[post["id"]] = post

	def add_queued_posts(self) -> None:
		# use a copy of the queue so a possible streaming thread in the background does not
		# mess with it while we are working at inserting the queued posts
		insert_queue = self.post_queue.copy()
		if insert_queue:
			# restart the update timer, so we only poll updates when
			# there was no streaming content until the update timeout
			self.update_timer.start(self.refresh_time)
			# update the button, too
			self.reload_button.setText(str(self.update_timer.remainingTime() // 1000))

			for post in insert_queue.values():
				# debug("adding queued post", post["id"], "in timeline", self.timeline_name)
				self.add_post(post)
				self.post_queue.pop(post["id"])
				QApplication.instance().processEvents()

		if len(self.post_queue):
			debug("post queue not yet empty, probably a thread put something in it while we were adding ... will be in the next round - in timeline", self.scroller_name)
		# else:
		# 	debug("post queue empty, good! - in timeline", self.timeline_name)

	def connect_to_stream_listener(self, stream_name: str, stream_listener: Listener) -> None:
		if stream_name == self.scroller_name:
			stream_listener.incoming_post.connect(self.queue_post)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
