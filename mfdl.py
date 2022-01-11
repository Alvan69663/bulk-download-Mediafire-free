#!/bin/env python3
import requests, json, os, traceback, time, random, sys, argparse, queue, threading, re
from log import log

TIMEOUT_T = 30
HTTP_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0" #Spoof firefox user agent
}
CUSTOM_FOLDER_RE = re.compile(r'afI= "([a-z0-9]{13}|[a-z0-9]{19})"') #Regex used for locating keys on pages with custom named folders e.g. https://www.mediafire.com/MonHun

def download_url(url, local_filename):
	#Save url as local_filename
	r = requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=TIMEOUT_T)
	#If error
	if(not r.ok):
		return r.status_code
	#Download
	with open(local_filename, 'wb') as f:
		for chunk in r.iter_content(chunk_size=1024): 
			if chunk: # filter out keep-alive new chunks
				f.write(chunk)
	return r.status_code

def get_file_metadata(file_id):
	#Get "response" key from mediafire's file/get_info.php API function
	rq = requests.post("https://www.mediafire.com/api/1.5/file/get_info.php", params={"quick_key": file_id, "response_format": "json"}, headers=HTTP_HEADERS, timeout=TIMEOUT_T)
	return rq.json()["response"]

def find_direct_url(info_url):
	#Find a direct download url on an info page
	rq = requests.get(info_url, headers=HTTP_HEADERS, timeout=TIMEOUT_T)
	web_html = rq.text
	
	download_link_prefix = '<div class="download_link" id="download_link">\n                            <a class="preparing" href="#"><span>Preparing your download...</span></a>\n                                    <a class="input popsok"\n                        aria-label="Download file"\n                        href="'
	uploaded_from_prefix = "<p>This file was uploaded from "

	if((web_html.find(download_link_prefix) == -1)): #If not found
		return {"success": 0}
	
	#Get direct url
	direct_url = web_html[web_html.find(download_link_prefix)+len(download_link_prefix):]
	direct_url = direct_url[:direct_url.find('"')]

	#Get location which only seems to be available on these info pages
	uploaded_from = web_html[web_html.find(uploaded_from_prefix)+len(uploaded_from_prefix):]
	uploaded_from = uploaded_from[:uploaded_from.find("</p>")]
	location = uploaded_from[:uploaded_from.find(" on ")]

	return {"url": direct_url, "location": location, "success": 1}

def download_file(mediafire_id, output_dir, only_meta=0, print_lock=threading.Lock()):
	#Returns 1 on success and 0 otherwise
	metadata = get_file_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		with print_lock:
			log("\033[90m{}:\033[0m \033[31m{}: {}\033[0m".format(mediafire_id, metadata["result"], metadata["message"]))
		return 0 #Skip file
	
	#Display info
	with print_lock:
		log("\033[90m{}: {}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m".format(mediafire_id,
		                                                                       metadata["file_info"]["created"],
		                                                                       metadata["file_info"]["owner_name"],
		                                                                       metadata["file_info"]["filename"]))

	#Individually shared files point to an info page, but files shared in a folder point directly to the file
	dwnld_head = requests.head(metadata["file_info"]["links"]["normal_download"], headers=HTTP_HEADERS, timeout=TIMEOUT_T).headers
	if(str(dwnld_head.get("Location")).startswith("https://download")): #Direct
		direct_url = metadata["file_info"]["links"]["normal_download"]
	else: #Info page
		direct_url = find_direct_url(metadata["file_info"]["links"]["normal_download"])
		#If couldn't find a download link; There needs to be an additional check because mediafire's API still returns info about files which were taken down
		if(direct_url["success"] == 0):
			with print_lock:
				log("\033[90m{}: \033[0m\033[31mCouldn't find download url\033[0m".format(mediafire_id))
			return 0
		metadata["location"] = direct_url["location"]
		direct_url = direct_url["url"]

	#Download file
	if(only_meta == 0):
		os.makedirs(output_dir + "/" + mediafire_id, exist_ok=True)
		output_fname = output_dir + "/" + mediafire_id + "/" + metadata["file_info"]["filename"]
		download_url(direct_url, output_fname)
	#Write metadata
	with open(output_dir + "/" + mediafire_id + ".info.json", "w") as fl:
		fl.write(json.dumps(metadata))
	return 1

def get_folder_content(folder_key, content_type, chunk):
	#Get "response" key from mediafire's folder/get_info.php API function
	rq = requests.get("https://www.mediafire.com/api/1.4/folder/get_content.php",
	                  params={"content_type": content_type, "chunk": chunk, "folder_key": folder_key, "response_format": "json"},
					  headers=HTTP_HEADERS,
					  timeout=TIMEOUT_T)
	return rq.json()["response"]

def get_folder_metadata(folder_key):
	#Get "response" key from mediafire's folder/get_info.php API function
	rq = requests.post("https://www.mediafire.com/api/1.5/folder/get_info.php", params={"folder_key": folder_key, "response_format": "json"}, headers=HTTP_HEADERS, timeout=TIMEOUT_T)
	return rq.json()["response"]

def download_folder(mediafire_id, output_dir, only_meta=0, print_lock=threading.Lock(), archive=[], archive_lock=threading.Lock()):
	#Recursively downloads a folder
	#Returns 1 on success and 0 otherwise
	metadata = get_folder_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		with print_lock:
			log("\033[90m{}: \033[0m\033[31m{}: {}\033[0m".format(mediafire_id, metadata["result"], metadata["message"]))
		return 0 #Skip folder
	
	with print_lock:
		log("\033[90m{}: {}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m".format(mediafire_id,
		                                                                       metadata["folder_info"]["created"],
		                                                                       metadata["folder_info"]["owner_name"],
		                                                                       metadata["folder_info"]["name"]))

	metadata["children"] = {"folders": [], "files": []}

	#Download folders inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"):
		children_folders_chunk = get_folder_content(mediafire_id, "folders", chunk)
		metadata["children"]["folders"] += children_folders_chunk["folder_content"]["folders"]
		more_chunks = children_folders_chunk["folder_content"]["more_chunks"]
		chunk+=1
	for folder in metadata["children"]["folders"]:
		download(folder["folderkey"], output_dir, only_meta=only_meta, archive=archive, archive_lock=archive_lock)

	#Download files inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"):
		children_files_chunk = get_folder_content(mediafire_id, "files", chunk)
		metadata["children"]["files"] += children_files_chunk["folder_content"]["files"]
		more_chunks = children_files_chunk["folder_content"]["more_chunks"]
		chunk+=1
	for fl in metadata["children"]["files"]:
		download(fl["quickkey"], output_dir, only_meta=only_meta, archive=archive, archive_lock=archive_lock)
	
	#Download avatar
	avatar_keys = analyze_mediafire.get_mediafire_links(metadata["folder_info"]["avatar"])["keys"]
	for avatar in avatar_keys: #There should be only 1 key in an avatar link, but loop through it just to be sure
		download(avatar, output_dir, only_meta=only_meta, archive=archive, archive_lock=archive_lock)

	#Write metadata
	if(os.path.exists(output_dir+"/"+mediafire_id+".info.json")): #Don't overwrite the .info.json file
		log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
		return 1
	with open(output_dir + "/" + mediafire_id + ".info.json", "w") as fl:
		fl.write(json.dumps(metadata))
	return 1

def download(mediafire_id, output_dir, only_meta=0, print_lock=threading.Lock(), archive=[], archive_lock=threading.Lock()):
	#Download mediafire key and save it in output_dir
	#In case of a mediafire error return 0
	#In case of an exception - retry after 10 seconds
	#Otherwise return 1
	while(1): #Retry until download returns
			with print_lock:
				log("\033[90m{}: Downloading...\033[0m".format(mediafire_id))
			try:
				if(mediafire_id.startswith("/conv/")): #Conv link
					with archive_lock:
						if(os.path.exists(output_dir+".."+mediafire_id) or (mediafire_id in archive)): #Duplicate
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return 1
						archive.append(mediafire_id)
					if(download_url("https://mediafire.com" + mediafire_id, output_dir+".."+mediafire_id) == 200): #Success
						log("\033[90m{}: \033[0m\033[96mDownloaded\033[0m".format(mediafire_id))
						return 1
					else:
						log("\033[90m{}: \033[0m\033[31mNot found!\033[0m".format(mediafire_id))
						return 0
				elif(len(mediafire_id) in [11, 15, 31]): #Single file
					with archive_lock:
						if(os.path.exists(output_dir+mediafire_id+".info.json") or (mediafire_id in archive)): #Duplicate
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return 1
						archive.append(mediafire_id)
					return download_file(mediafire_id, output_dir, only_meta=only_meta)
				elif(len(mediafire_id) in [13, 19]): #Folder
					with archive_lock:
						#Redownload contents even if .info.json file exists (without overwriting it) but skip if another thread already started downloading it
						if(mediafire_id in archive):
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return 1
						archive.append(mediafire_id)
					return download_folder(mediafire_id, output_dir, only_meta=only_meta, archive=archive, archive_lock=archive_lock)
			except Exception:
				with print_lock:
					traceback.print_exc()
					log("\033[90m{}: \033[0m\033[31mError while downloading! Retrying in 10s...\033[0m".format(mediafire_id))
				time.sleep(10)

def resolve_custom_folder(name):
	while(1): #Retry if an exception is caught
		log("\033[90mResolving custom folder name:\033[0m \033[96m{}\033[0m".format(name))
		try:
			rq = requests.get("https://mediafire.com/{}".format(name), headers=HTTP_HEADERS, timeout=TIMEOUT_T)
			resolved = CUSTOM_FOLDER_RE.findall(rq.text)
			if(resolved):
				resolved = resolved[0] #First result
				log("\033[96m{}\033[0m \033[90m->\033[0m \033[95m{}\033[0m".format(name, resolved))
				return resolved
			else:
				log("\033[31mUnable to resolve {}\033[0m".format(name))
				return None
		except Exception:
			continue

def worker(args, download_queue, archive, archive_lock, print_lock):
	while(1):
			try:
				mediafire_id = download_queue.get(block=0)
			except queue.Empty:
				with print_lock:
					log("\033[32mQueue is empty\033[0m")
				return
			download_successful = download(mediafire_id, args.output + "/keys/", only_meta=args.only_meta, print_lock=print_lock, archive=archive, archive_lock=archive_lock)
			time.sleep(random.random())

if(__name__ == "__main__"):
	#CLI front end
	import analyze_mediafire
	
	parser = argparse.ArgumentParser(description="Mediafire downloader")
	parser.add_argument("--only-meta", action="store_true", help="Only download *.info.json files")
	parser.add_argument("--threads", type=int, default=6, help="How many threads to use; in case mediafire starts showing captchas or smth the amount of threads should be reduced; default is 6")
	parser.add_argument("output", help="Output directory")
	parser.add_argument("input", nargs="+", help="Input file/files which will be searched for links")
	args = parser.parse_args()

	#Message to encourage people to submit links to the archive team.
	log("\033[33mIf you have mediafire links you want to archive you can submit them to the Archive Team (https://archiveteam.org/index.php?title=MediaFire). If you don't have any fancy raidz configurations this will be the best way to preserve them.\033[0m")

	#Archive list is a list of files that started downloading. It's used to
	#stop threads from starting to download the same file multiple times.
	#For example if a file is downloading as a single file in one thread and
	#another thread starts downloading it as part of a directory before the first
	#thread finishes
	archive = []

	#Get ids
	mediafire_urls = analyze_mediafire.read_mediafire_links(args.input)

	#Resolve custom names to keys and save names and their keys to custom_folders.txt
	#custom_folders.txt format:
	#"KEY FOLDER_NAME\n"
	custom_folders_fname = args.output + "/custom_folders.txt"
	if(not os.path.exists(custom_folders_fname)): #If doesn't exist create
		with open(custom_folders_fname, 'w'): pass
	custom_folder_lookup = {}
	#Read custom folder lookup table
	with open(custom_folders_fname, "r") as fl:
		for line in fl.read().splitlines():
			lookup_entry = line.split(" ")
			custom_folder_lookup[lookup_entry[1]] = lookup_entry[0]
	#Resolve names
	for custom_folder in mediafire_urls["custom_folders"]:
		if(custom_folder in custom_folder_lookup): #Already in the table
			mediafire_urls["keys"].append(custom_folder_lookup[custom_folder]) #Add resolved key
		else: #Not yet resolved
			resolved = resolve_custom_folder(custom_folder)
			if(resolved):
				with open(custom_folders_fname, "a") as fl:
					fl.write("{} {}\n".format(resolved, custom_folder))
				mediafire_urls["keys"].append(resolved) #Add resolved key
				custom_folder_lookup[custom_folder] = resolved

	#Create download dirs
	os.makedirs(args.output + "/keys", exist_ok=True)
	os.makedirs(args.output + "/conv", exist_ok=True)

	#Download
	archive_lock = threading.Lock()
	print_lock = threading.Lock()
	worker_list = []
	download_queue = queue.Queue()

	for conv_link in mediafire_urls["conv"]: #Download conv links
		download_queue.put(conv_link)

	for mediafire_id in mediafire_urls["keys"]: #Download keys
		download_queue.put(mediafire_id)

	for i in range(args.threads): #Launch threads
		thread = threading.Thread(target=worker, args=(args, download_queue, archive, archive_lock, print_lock,))
		thread.name = i
		thread.start()
		worker_list.append(thread)
