#!/bin/env python3
import urllib.parse

def get_urls(string):
	words = string.split(" ")
	urls = []
	protocols = ["http://", "https://"]
	for word in words: #Get URLs
		for prot in protocols:
			if(prot in word):
				urls.append(word[word.find(prot):])
				break
	return urls

def get_urls_from_files(files):
	words = []
	for fl in files: #Read descriptions
		lines = []
		with open(fl, "r") as fl:
			lines = fl.read().splitlines()
		for line in lines:
			words+=line.split(" ")
	combined = " ".join(words)
	urls = get_urls(combined)
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
