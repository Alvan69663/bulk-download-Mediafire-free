#!/bin/env python3
import analyze

def get_mediafire_id(url):
	charset = "qwertyuiopasdfghjklzxcvbnm1234567890"
	candidates = []

	current = ""
	for char in url:
		if(char in charset):
			current+=char
		else:
			candidates.append(current)
			current=""
	candidates.append(current)

	for cand in candidates:
		#Determine type of object by key length
		#I've never seen 19 and 31 characters long keys,
		#but according to mediafire's API they are valid
		if(len(cand) in [11, 15, 31]):
			return {"type": "file", "id": cand}
		elif(len(cand) in [13, 19]):
			return {"type": "directory", "id": cand}
	return {"type": "unknown", "id": url}

def get_mediafire_urls(files):
		urls = analyze.get_urls_from_files(list(files))
		mediafire_urls = []
		for url in urls:
			if(("mediafire" in url) or ("mfi.re" in url)):
				mediafire_urls.append(url)

		files = []
		dirs = []
		for url in mediafire_urls:
			m_id = get_mediafire_id(url)
			if(m_id["type"] == "file"):
				if(m_id["id"] not in files): files.append(m_id["id"])
			elif(m_id["type"] == "directory"):
				if(m_id["id"] not in dirs): dirs.append(m_id["id"])

		return {"files": files, "dirs": dirs}

if(__name__ == "__main__"):
	import sys

	if(len(sys.argv) < 2):
		print("Usage: ")
		print(" ./{} FILE [FILE]".format(sys.argv[0]))
		exit()

	urls = get_mediafire_urls(sys.argv[1:])

	print("--- FILES ---")
	for fl in urls["files"]:
		print("https://mediafire.com/?{}".format(fl))

	print()

	print("--- DIRECTORIES ---")
	for dr in urls["dirs"]:
		print("https://mediafire.com/?{}".format(dr))
