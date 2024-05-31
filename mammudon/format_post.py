# TODO: Qt UI needs to follow the theme, icons need inverted colors in dark mode, etc.

import os
from html import escape

from mammudon.debugging import debug


def format_poll(values: dict, poll: dict) -> tuple[str, str]:
	# TODO: this part is duplicated in format_*() below, we need to find
	#       a way to get preferences["values"] here without importing preferences, because
	#       that creates a cyclic dependency
	theme: str = values["theme"]
	layout: str = values["layout"]
	file_path: str = os.path.dirname(__file__)
	theme_path: str = os.path.join(file_path, "themes", theme)
	layout_path: str = os.path.join(file_path, "layouts", layout)

	def theme_open(file_name: str):
		return open(os.path.join(theme_path, file_name), 'r')

	def layout_open(file_name: str):
		return open(os.path.join(layout_path, file_name), 'r')
	# TODO: /duplicated

	poll_css = ""
	poll_html = ""

	if poll:
		with theme_open("poll.css") as poll_css_file:
			poll_css = poll_css_file.read()

		with layout_open("poll.html") as poll_html_file:
			poll_html = poll_html_file.read()

			poll_id = poll["id"]
			# count voters, not votes, so multiple choice percentages work correctly
			total_votes = poll["voters_count"]
			poll_expired = poll["expired"]
			poll_voted = poll.get("voted", False)

			poll_item: dict
			poll_items_html = ""

			winning_votes = 0
			losing_votes = 101
			for poll_item in poll["options"]:
				count = poll_item["votes_count"]
				if count > winning_votes:
					winning_votes = count
				elif count < losing_votes:
					losing_votes = count

			item_number = 0
			for poll_item in poll["options"]:
				# TODO: use "poll_item_closed.html" when "See Results" was clicked on a still open and unvoted post
				poll_item_filename = "poll_item_radio.html"
				if poll_expired or poll_voted:
					poll_item_filename = "poll_item_closed.html"
				elif poll["multiple"]:
					poll_item_filename = "poll_item_checkbox.html"

				item_html: str
				with layout_open(poll_item_filename) as item_html_file:
					item_html = item_html_file.read()

					percent = 0
					percent_bar = 0
					if total_votes:
						percent = poll_item["votes_count"] * 100 // total_votes
						# TODO: scale bar length to maximum vote?
						percent_bar = poll_item["votes_count"] * 100 // total_votes

					winning_losing = ""
					count = poll_item["votes_count"]
					if count == winning_votes:
						winning_losing = " poll-winning"
					elif count == losing_votes:
						winning_losing = " poll-losing"

					item_html = item_html.replace("%poll_item_title%", escape(poll_item["title"]))
					item_html = item_html.replace("%poll_item_percent%", str(percent))
					item_html = item_html.replace("%poll_item_percent_bar%", str(percent_bar))
					item_html = item_html.replace("%poll_winning_losing%", winning_losing)

					poll_voted_html = ""
					if item_number in poll.get("own_votes", []):
						with layout_open("poll_item_voted.html") as poll_voted_html_file:
							poll_voted_html = poll_voted_html_file.read()

					item_html = item_html.replace("%poll_voted%", poll_voted_html)

				poll_items_html += item_html
				item_number += 1

			# TODO: use "poll_footer_open_results-html" when "See Results" was clicked
			poll_footer_filename = "poll_footer_open.html"
			if poll_expired:
				poll_footer_filename = "poll_footer_closed.html"
			elif poll_voted:
				poll_footer_filename = "poll_footer_voted.html"

			poll_footer_html: str
			with layout_open(poll_footer_filename) as poll_footer_html_file:
				poll_footer_html = poll_footer_html_file.read()

			poll_html = poll_html.replace("%poll_items%", poll_items_html)
			poll_html = poll_html.replace("%poll_footer%", poll_footer_html)
			poll_html = poll_html.replace("%poll_votes%", str(total_votes))
			poll_html = poll_html.replace("%poll_users%", str(poll["voters_count"]))
			poll_html = poll_html.replace("%remaining%", str(poll["expires_at"]))  # TODO - remaining time / "Closed"
			poll_html = poll_html.replace("%poll_vote_url%", "poll://vote/" + str(poll_id))  # TODO - refresh url
			poll_html = poll_html.replace("%poll_results_url%", "poll://results/" + str(poll_id))  # TODO - refresh url
			poll_html = poll_html.replace("%poll_refresh_url%", "poll://refresh/" + str(poll_id))

	return poll_css, poll_html


def format_post(values: dict, post: dict, boosted_by: dict, custom_emojis: list[dict]) -> str:
	# TODO: this part is duplicated in format_*() above and below, we need to find
	#       a way to get preferences["values"] here without importing preferences, because
	#       that creates a cyclic dependency
	theme: str = values["theme"]
	layout: str = values["layout"]
	file_path: str = os.path.dirname(__file__)
	theme_path: str = os.path.join(file_path, "themes", theme)
	layout_path: str = os.path.join(file_path, "layouts", layout)

	def theme_open(file_name: str):
		return open(os.path.join(theme_path, file_name), 'r')

	def layout_open(file_name: str):
		return open(os.path.join(layout_path, file_name), 'r')
	# TODO: /duplicated

	boost = ""
	if boosted_by:
		with layout_open("boosted_by.html") as boosted_by_file:
			boost = boosted_by_file.read()
			boost = boost.replace("%boosted_by_url%", boosted_by["url"])
			boost = boost.replace("%boosted_by_avatar%", boosted_by["avatar"])
			boost = boost.replace("%boosted_by_acct%", boosted_by["acct"])
			boost = boost.replace("%boosted_by_display_name%", boosted_by["display_name"])

	in_reply_to_css = ""
	in_reply_to_html = ""
	in_reply_to_id = post.get("in_reply_to_account_id", 0)
	if in_reply_to_id:
		mentions: list[dict] = post.get("mentions", [])
		for mention in mentions:
			if mention["id"] == in_reply_to_id:
				with theme_open("in_reply_to.css") as in_reply_to_css_file:
					in_reply_to_css = in_reply_to_css_file.read()
				with layout_open("in_reply_to.html") as in_reply_to_file:
					in_reply_to_html = in_reply_to_file.read()
					in_reply_to_html = in_reply_to_html.replace("%in_reply_to_url%", mention["url"])
					in_reply_to_html = in_reply_to_html.replace("%in_reply_to_acct%", "@" + mention["acct"])

	poll: dict = post.get("poll", {})
	poll_css, poll_html = format_poll(values, poll)

	media_descs = ""
	media_css = ""
	media_hover_css = ""
	audio_player_css = ""
	media_attachments = post.get("media_attachments", [])

	num_media = len(media_attachments)

	# default to single cells, this will be always the case for 4 images
	media_tall_wide = ""

	media_index = 0
	media: dict
	for media in media_attachments:
		# only one image/media, fill the whole grid
		if num_media == 1:
			media_tall_wide = " media-item-tall media-item-wide"

		# prefer tall image layout for 2 images, unless both images are really wide
		elif num_media == 2:
			# get these first, so we can test if they exist before calling .get on them
			meta0 = media_attachments[0]["meta"]
			meta1 = media_attachments[1]["meta"]
			# "small" might not be there, so safeguard it
			if (
				meta0 and meta1 and
				meta0.get("small", {}).get("aspect", 1.0) > 1.66 and
				meta1.get("small", {}).get("aspect", 1.0) > 1.66
			):
				media_tall_wide = " media-item-wide"
			else:
				media_tall_wide = " media-item-tall"

		# seems like the mastodon website always shows the first image in a set of 3 as
		# tall, the others in single cells, so we do the same
		elif num_media == 3:
			if media_index == 0:
				media_tall_wide = " media-item-tall"
			else:
				media_tall_wide = ""

		# TODO: HTML encode of all externally inserted strings

		media_description = media.get("description", "")
		# could still return "None"
		if not media_description:
			media_description = ""

		media_preview_url = media.get("preview_url", "")
		# could still return "None"
		if not media_preview_url:
			media_preview_url = ""

		media_url = media.get("url", "")
		# could still return "None"
		if not media_url:
			media_url = ""

		media_item_html = ""

		# different media types need different previews
		if media["type"] == "image":
			if media_url:

				media_markers_html = ""

				if media_description:
					with layout_open("media_marker_alt.html") as media_marker_alt_file:
						media_markers = media_marker_alt_file.read()

						with layout_open("media_markers.html") as media_markers_file:
							media_markers_html = media_markers_file.read()
							media_markers_html = media_markers_html.replace("%media_markers%", media_markers)

				if media_preview_url:
					with layout_open("image_with_preview.html") as image_with_preview:
						media_item_html += image_with_preview.read()
						media_item_html = media_item_html.replace("%media_markers_container%", media_markers_html)
						media_item_html = media_item_html.replace("%media_index%", str(media_index))
				else:
					with layout_open("image_without_preview.html") as image_without_preview:
						media_item_html += image_without_preview.read()
			else:
				debug("Missing Image URL for", post["id"], "-", media_description)

			meta: dict = media.get("meta", {})
			focus: dict = meta.get("focus", {})
			focus_x: float = focus.get("x", 0.0) * (-50.0)
			focus_y: float = focus.get("y", 0.0) * 50.0

			# add the media hover focus css with the current index number
			with theme_open("media_hover.css") as media_hover_file:
				media_hover_css += media_hover_file.read()
				media_hover_css = media_hover_css.replace("%media_index%", str(media_index))
				media_hover_css = media_hover_css.replace("%focus_x%", str(focus_x))
				media_hover_css = media_hover_css.replace("%focus_y%", str(focus_y))

		elif media["type"] == "video":
			if media_url:
				with layout_open("video_player.html") as video_player_file:
					media_item_html += video_player_file.read()
			else:
				debug("Missing Video URL for", post["id"], "-", media_description)

		elif media["type"] == "gifv":
			if media_url:
				with layout_open("media_marker_gifv.html") as media_marker_gifv_file:
					media_markers = media_marker_gifv_file.read()

					if media_description:
						with layout_open("media_marker_alt.html") as media_marker_alt_file:
							media_markers += media_marker_alt_file.read()

					with layout_open("media_markers.html") as media_markers_file:
						media_markers_html = media_markers_file.read()
						media_markers_html = media_markers_html.replace("%media_markers%", media_markers)

				with layout_open("gifv_player.html") as gifv_player_file:
					media_item_html += gifv_player_file.read()
					media_item_html = media_item_html.replace("%media_markers_container%", media_markers_html)
			else:
				debug("Missing GIFV URL for", post["id"], "-", media_description)

		elif media["type"] == "audio":
			if media_url:
				with theme_open("audio_player.css") as audio_player_file:
					audio_player_css = audio_player_file.read()

				audio_player_content_file_name = "audio_without_preview"
				if media_preview_url:
					audio_player_content_file_name = "audio_with_preview"
				else:
					if not media_description:
						media_description = "Download Here"

				with layout_open(audio_player_content_file_name + ".html") as audio_player_content_file:
					audio_player_content_html = audio_player_content_file.read()

				with layout_open("audio_player.html") as audio_player_file:
					audio_player_html = audio_player_file.read()
					audio_player_html = audio_player_html.replace("%audio_player%", audio_player_content_html)

				media_item_html += audio_player_html

			else:
				debug("Missing Audio URL for", post["id"], "-", media_description)

		else:
			if media_url:
				if media_preview_url:
					media_item_html += (
						f'<div class="media-item{media_tall_wide}"><a href="media-unknown:{media_url}">' +
						f'<img class="media-preview" src="{media_preview_url}" title="{media_description}"></a></div>'
					)
				else:
					media_item_html += f'<div class="media-item"><a href="media-unknown:{media_url}">Unknown media: {media_description}</a></div>'
			else:
				debug("Missing Unknown Media URL for", post["id"], "-", media_description)

		media_index += 1

		# replace all common placeholders for this media item
		media_item_html = media_item_html.replace("%media_tall_wide%", media_tall_wide)
		media_item_html = media_item_html.replace("%media_url%", media_url)
		media_item_html = media_item_html.replace("%media_preview_url%", media_preview_url)
		media_item_html = media_item_html.replace("%media_description%", escape(media_description))

		media_descs += media_item_html

	card_html = ""
	card_css = ""

	media_html = ""
	if media_descs:
		with layout_open("media_grid.html") as file:
			media_html = file.read()
			media_html = media_html.replace("%media_grid%", media_descs)

		with theme_open("media.css") as file:
			media_css = file.read()
			media_css = media_css.replace("%media_hover_css%", media_hover_css)
	else:
		# only check for cards if there is no media attached
		card: dict = post["card"]
		if card:
			debug("Card:", card)

			card_url: str = card["url"]

			card_image: str = card.get("image", "")
			if not card_image:
				card_image = ""

			card_language: str = card.get("language", "")
			if not card_language:
				card_language = ""

			card_provider_name = card.get("provider_name", "")
			if not card_provider_name:
				card_provider_name = card_url.split("/")[2]

			card_type = card["type"]
			card_body_file_name = "card_body_link_no_image"

			if card_type == "link":
				if card_image:
					card_body_file_name = "card_body_link_image"

			elif card_type == "rich":
				# TODO: make a rich card - never saw one in the wild
				card_body_file_name = "card_body_rich_text"

			elif card_type == "video":
				card_body_file_name = "card_body_video"

			elif card_type == "photo":
				card_body_file_name = "card_body_photo"

			card_marker_alt_html = ""
			if card["title"]:
				with layout_open("card_marker_alt.html") as file:
					card_marker_alt_html = file.read()

			with layout_open(card_body_file_name + ".html") as file:
				card_html = file.read()
				card_html = card_html.replace("%card_url%", card_url)
				card_html = card_html.replace("%card_image%", card_image)
				card_html = card_html.replace("%card_description%", escape(card["description"]))
				card_html = card_html.replace("%card_language%", card_language)
				card_html = card_html.replace("%card_marker_alt%", card_marker_alt_html)
				card_html = card_html.replace("%card_title%", escape(card["title"]))
				card_html = card_html.replace("%card_provider_name%", escape(card_provider_name))

			with theme_open("card.css") as file:
				card_css = file.read()

	spoiler_css = ""
	spoiler_start = ""
	spoiler_end = ""
	if post["spoiler_text"]:

		with theme_open("spoiler.css") as file:
			spoiler_css = file.read()

		expand_spoilers = bool(int(values["expand_spoilers"]))
		with layout_open("spoiler_start.html") as file:
			spoiler_start = file.read()
			spoiler_start = spoiler_start.replace("%spoiler_text%", escape(post["spoiler_text"]))
			spoiler_start = spoiler_start.replace("%spoiler_open%", ' open' if expand_spoilers else '')

		with layout_open("spoiler_end.html") as file:
			spoiler_end = file.read()

	post_css: str
	with theme_open("post.css") as file:
		post_css = file.read()

	body_css: str
	with theme_open("body.css") as file:
		body_css = file.read()

	post_html: str
	with layout_open("post.html") as file:
		post_html = file.read()
		post_html = post_html.replace("%body_css%", body_css)
		post_html = post_html.replace("%post_css%", post_css)
		post_html = post_html.replace("%media_css%", media_css)
		post_html = post_html.replace("%audio_player_css%", audio_player_css)
		post_html = post_html.replace("%poll_css%", poll_css)
		post_html = post_html.replace("%card_css%", card_css)
		post_html = post_html.replace("%spoiler_css%", spoiler_css)
		post_html = post_html.replace("%boost%", boost)
		post_html = post_html.replace("%in_reply_to_css%", in_reply_to_css)
		post_html = post_html.replace("%in_reply_to%", in_reply_to_html)
		post_html = post_html.replace("%post_account_url%", post["account"]["url"])
		post_html = post_html.replace("%post_account_avatar%", post["account"]["avatar"])
		post_html = post_html.replace("%post_id%", str(post["id"]))
		post_html = post_html.replace("%post_account_display_name%", post["account"]["display_name"])
		post_html = post_html.replace("%post_account_acct%", post["account"]["acct"])
		post_html = post_html.replace("%spoiler_start%", spoiler_start)
		post_html = post_html.replace("%post_content%", post["content"])
		post_html = post_html.replace("%poll_content%", poll_html)
		post_html = post_html.replace("%media_html%", media_html)
		post_html = post_html.replace("%card_html%", card_html)
		post_html = post_html.replace("%spoiler_end%", spoiler_end)

	# collect custom emojis from all sorts of places
	emojis: list = post["account"]["emojis"]
	emojis.extend(post["emojis"])
	emojis.extend(custom_emojis)

	if poll:
		emojis.extend(poll["emojis"])
	if boosted_by:
		emojis.extend(boosted_by["emojis"])

	for emoji in emojis:
		post_html = post_html.replace(
			':' + emoji["shortcode"] + ':',
			'<img class="custom-emoji" title="&#58;' + emoji["shortcode"] + '&#58;" src="' + emoji["url"] + '">'
		)

	# return content with all "open in new tab" tags removed, so we can intercept the navigation requests
	return post_html.replace(' target="_blank"', '')


def format_notification(values: dict, my_id: int, notification: dict) -> str:
	# TODO: this part is duplicated in format_post() above, we need to find
	#       a way to get preferences["values"] here without importing preferences, because
	#       that creates a cyclic dependency
	theme: str = values["theme"]
	layout: str = values["layout"]
	file_path: str = os.path.dirname(__file__)
	theme_path: str = os.path.join(file_path, "themes", theme)
	layout_path: str = os.path.join(file_path, "layouts", layout)

	def theme_open(file_name: str):
		return open(os.path.join(theme_path, file_name), 'r')

	def layout_open(file_name: str):
		return open(os.path.join(layout_path, file_name), 'r')
	# TODO: /duplicated

	# 'id': # id of the notification
	# 'type': # "mention", "reblog", "favourite", "follow", "poll" or "follow_request"
	# 'created_at': # The time the notification was created
	# 'account': # User dict of the user from whom the notification originates
	# 'status': # In case of "mention", the mentioning status
	#           # In case of reblog / favourite, the reblogged / favourited status

	own = ""
	if notification["type"] == "poll" and notification["account"]["id"] == my_id:
		own = "_own"

	notification_content_html: str
	with layout_open("notification_" + notification["type"] + own + ".html") as file:
		notification_content_html = file.read()

	notification_post_avatar = ""
	if notification["type"] != "poll":
		if notification["type"] == "favourite":
			with layout_open("notification_favourite_avatar.html") as file:
				notification_post_avatar = file.read()
		else:
			with layout_open("notification_post_avatar.html") as file:
				notification_post_avatar = file.read()

	poll_css = ""
	poll_html = ""
	notification_post_html = ""
	notification_status = notification.get("status", {})
	if notification_status:
		notification_post_html = notification_status.get("content", "")

		poll: dict = notification_status.get("poll", {})
		poll_css, poll_html = format_poll(values, poll)

	notification_post_css: str
	with theme_open("notification_post.css") as file:
		notification_post_css = file.read()

	notification_body_css: str
	with theme_open("notification_body.css") as file:
		notification_body_css = file.read()

	notification_css: str
	with theme_open("notification.css") as file:
		notification_css = file.read()

	notification_html: str
	with layout_open("notification.html") as file:
		notification_html = file.read()
		notification_html = notification_html.replace("%body_css%", notification_body_css)
		notification_html = notification_html.replace("%post_css%", notification_post_css)
		notification_html = notification_html.replace("%poll_css%", poll_css)
		notification_html = notification_html.replace("%notification_css%", notification_css)
		notification_html = notification_html.replace("%notification_content%", notification_content_html)
		notification_html = notification_html.replace("%post_avatar%", notification_post_avatar)
		notification_html = notification_html.replace("%post_content%", notification_post_html)
		notification_html = notification_html.replace("%poll_content%", poll_html)
		notification_html = notification_html.replace("%notification_id%", str(notification["id"]))
		notification_html = notification_html.replace("%other_account_url%", notification["account"]["url"])
		notification_html = notification_html.replace("%other_account_acct%", notification["account"]["acct"])
		notification_html = notification_html.replace("%other_account_display_name%", notification["account"]["display_name"])
		notification_html = notification_html.replace("%other_account_avatar%", notification["account"]["avatar"])
		if notification_status:
			notification_html = notification_html.replace("%account_url%", notification["status"]["account"]["url"])
			notification_html = notification_html.replace("%account_avatar%", notification["status"]["account"]["avatar"])

	# return content with all "open in new tab" tags removed, so we can intercept the navigation requests
	return notification_html.replace(' target="_blank"', '')


def format_conversation(values: dict, _my_id: int, conversation: dict) -> str:
	# TODO: this part is duplicated in format_*() above, we need to find
	#       a way to get preferences["values"] here without importing preferences, because
	#       that creates a cyclic dependency
	theme: str = values["theme"]
	layout: str = values["layout"]
	file_path: str = os.path.dirname(__file__)
	theme_path: str = os.path.join(file_path, "themes", theme)
	layout_path: str = os.path.join(file_path, "layouts", layout)

	def theme_open(file_name: str):
		return open(os.path.join(theme_path, file_name), 'r')

	def layout_open(file_name: str):
		return open(os.path.join(layout_path, file_name), 'r')
	# TODO: /duplicated

	# 'id': # The ID of this conversation object
	# 'unread': # Boolean indicating whether this conversation has yet to be
	#           # read by the user
	# 'accounts': # List of accounts (other than the logged-in account) that
	#             # are part of this conversation
	# 'last_status': # The newest status in this conversation

	debug("Conversation: ", conversation)

	conversation_post_html = "No status."

	last_status = conversation.get("last_status")
	if last_status:
		conversation_post_html = last_status['content']

	body_css: str
	with theme_open("body.css") as file:
		body_css = file.read()

	conversation_css: str
	with theme_open("conversation.css") as file:
		conversation_css = file.read()

	with layout_open("display_name.html") as file:
		display_name_html = file.read().rstrip()

		account: dict
		dns: list[str] = []
		for account in conversation["accounts"]:
			dns.append(display_name_html.replace("%display_name%", account["display_name"]))
		display_names = ", ".join(dns)

	conversation_html: str
	with layout_open("conversation.html") as file:
		conversation_html = file.read()
		conversation_html = conversation_html.replace("%body_css%", body_css)
		conversation_html = conversation_html.replace("%conversation_css%", conversation_css)
		conversation_html = conversation_html.replace("%post_content%", conversation_post_html)
		conversation_html = conversation_html.replace("%conversation_id%", str(conversation["id"]))
		conversation_html = conversation_html.replace("%other_account_url%", conversation["accounts"][0]["url"])
		conversation_html = conversation_html.replace("%other_account_acct%", conversation["accounts"][0]["acct"])
		conversation_html = conversation_html.replace("%display_names%", display_names)
		conversation_html = conversation_html.replace("%other_account_avatar%", conversation["accounts"][0]["avatar"])

	# return content with all "open in new tab" tags removed, so we can intercept the navigation requests
	return conversation_html.replace(' target="_blank"', '')
