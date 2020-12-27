#!/bin/env python3
import re


#Searches for keys and lists of keys; also considers url encoded symbols
mf_key_re = "(?i)(?:media.{0,5}?fire.{0,5}?com|mfi.{0,5}?re).{0,40}?(?:(?:\/|%2F).{0,40}?(?:\/|%2F)|(?:\?|%3F)).{0,40}?([0-9a-z,.]{22,}|[0-9a-z,]{19}|[0-9a-z,]{15}|[0-9a-z,]{13}|[0-9a-z,]{11})"

#Searches for links to files (e.g. https://img19.mediafire.com/22d9d9406ca5a970a04cf542eb7e210241fcd8ca47494a3483729a9b7320afbb5g.jpg)
#and for links to custom folders (e.g. https://www.mediafire.com/MonHun); this regex also considers url encoded symbols
mf_link_re = "(?i)(?:media.{0,5}?fire.{0,5}?com|mfi.{0,5}?re)[^\/?%\r\n]{0,5}?(?:\/|%2F)[^\/?%\r\n]{0,5}?([a-zA-Z0-9_.]+)\s"

def get_mediafire_links(text):
	#Get all of the mediafire keys, links and custom folders from text
	output = {"keys": [], "links": [], "custom_folders": []}

	mf_key_matches = re.findall(mf_key_re, text)
	for match in mf_key_matches:
		for mf_key in match.split(","): #Mediafire allows specifying multiple keys by separating them with ","
			if(len(mf_key) in [11,13,15,19,31]):
				output["keys"].append(mf_key) #It's a valid key

	mf_link_matches = re.findall(mf_link_re, text)
	for match in mf_link_matches:
		if("." in match): #file
			output["links"].append(match)
		else: #custom folder
			output["custom_folders"].append(match)

	return output

def read_mediafire_links(files):
	#Get all of the mediafire keys, links and custom folders from list of files
	output = {"keys": [], "links": [], "custom_folders": []}
	for fname in files:
		with open(fname, "r") as fl:
			data = fl.read()
		mf_links = get_mediafire_links(data)
		output["keys"] += mf_links["keys"]
		output["links"] += mf_links["links"]
		output["custom_folders"] += mf_links["custom_folders"]
	return output

if(__name__ == "__main__"):
	import sys

	if(len(sys.argv) < 2):
		print("Usage: ")
		print(" ./{} FILE [FILE]".format(sys.argv[0]))
		exit()

	urls = read_mediafire_links(sys.argv[1:])

	if(urls["keys"]):
			print("--- KEYS ---")
			for fl in urls["keys"]:
				print("https://mediafire.com/?{}".format(fl))
			print()
	
	if(urls["links"]):
			print("--- LINKS ---")
			for fl in urls["links"]:
				print("https://mediafire.com/{}".format(fl))
			print()
	
	if(urls["custom_folders"]):
			print("--- CUSTOM FOLDERS ---")
			for fl in urls["custom_folders"]:
				print("https://mediafire.com/{}".format(fl))
			print()
