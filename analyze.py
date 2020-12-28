#!/bin/env python3
import urllib.parse, re

URL_RE = re.compile("http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")

def truncate_schema(url):
	return url[url.find("://")+3:]

def get_urls(string):
	return URL_RE.findall(string)

def get_urls_from_files(files):
	urls = []
	for fl in files: #Read descriptions
		lines = []
		with open(fl, "r") as fl:
			words = fl.read().replace("\n", " ")
		urls = get_urls(words)
	return urls

if(__name__ == "__main__"):
	import sys

	if(len(sys.argv) < 2):
		print("Usage: ")
		print(" ./{} FILE [FILE]".format(sys.argv[0]))
		exit()

	urls = get_urls_from_files(sys.argv[1:])
	for url in urls:
		print(url)
