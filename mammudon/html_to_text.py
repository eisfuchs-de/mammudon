from html.parser import HTMLParser


class HtmlToText(HTMLParser):
	text = ""

	# <br>
	def handle_starttag(self, tag: str, _attrs) -> None:
		if tag == "br":
			self.text += "\n"

	# <br /> <p />
	def handle_startendtag(self, tag: str, _attrs) -> None:
		if tag == "br" or tag == "p":
			self.text += "\n"

	# </p>
	def handle_endtag(self, tag: str) -> None:
		if tag == "p":
			self.text += "\n"

	def handle_data(self, data: str) -> None:
		self.text += data

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
