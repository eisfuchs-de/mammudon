import os
import sys
import time


def debug(*text):

	local_time = time.localtime(time.time())

	final: list[str] = []

	for piece in text:
		final.append(str(piece))

	filename = os.path.basename(sys._getframe().f_back.f_code.co_filename)
	line = str(sys._getframe().f_back.f_lineno)

	print(time.strftime("[%Y-%m-%d %H:%M:%S]", local_time), "DEBUG:", filename + ":" + line + " - " + " ".join(final))
