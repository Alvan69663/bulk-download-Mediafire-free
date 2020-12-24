#!/bin/env python3
import urllib.parse

URL_CHARS = "^0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ,.-!/=?`*;:_{}\|~%"

def get_urls(string):
	urls = []
	protocols = ["http://", "https://"]
	for word in string.split(" "): #Get URLs
		for prot in protocols:
			if(prot in word):
				url_to_append = ""
				for symbol in word[word.find(prot):]: #Add symbols to url_to_append as long as they can be used in URLs
					if(symbol in URL_CHARS):
						url_to_append += symbol
					else:
						break
				urls.append(url_to_append)
				break
	return urls

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
