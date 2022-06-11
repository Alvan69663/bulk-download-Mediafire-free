#!/bin/env python3
import requests, json, os, traceback, time, random, sys, argparse, queue, threading, multiprocessing, re, analyze_mediafire
from log import log

TIMEOUT_T = 30
HTTP_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0" #Spoof firefox user agent
}
CUSTOM_FOLDER_RE = re.compile(r'afI= "([a-z0-9]{13}|[a-z0-9]{19})"') #Regex used for locating keys on pages with custom named folders e.g. https://www.mediafire.com/MonHun

ARCHIVE_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()

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
	
	download_link_prefix = '\nPreparing your download…\n<a class="input popsok" aria-label="Download file" href="'
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

def download_file(mediafire_id, output, only_meta=0, archive_mode=False):
	#Returns 1 on success and 0 otherwise
	metadata = get_file_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		with PRINT_LOCK:
			log("\033[90m{}:\033[0m \033[31m{}: {}\033[0m".format(mediafire_id, metadata["result"], metadata["message"]))
		return 0 #Skip file

	#Display info
	with PRINT_LOCK:
		log("\033[90m{}: {}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m".format(mediafire_id,
		                                                                       metadata["file_info"]["created"],
		                                                                       metadata["file_info"]["owner_name"],
		                                                                       metadata["file_info"]["filename"]))

	if not archive_mode and not only_meta:
		filename = metadata["file_info"]["filename"]
		if "/" in filename or ".." == filename:
			with PRINT_LOCK:
				log("Dangerous name {} for file with id {}".format(filename, mediafire_id))
			filename = mediafire_id
		output = output + "/" + filename
		if(os.path.exists(output)): #Duplicate
			log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
			return (1, None)

	#Individually shared files point to an info page, but files shared in a folder point directly to the file
	dwnld_head = requests.head(metadata["file_info"]["links"]["normal_download"], headers=HTTP_HEADERS, timeout=TIMEOUT_T).headers
	if(str(dwnld_head.get("Location")).startswith("https://download")): #Direct
		direct_url = metadata["file_info"]["links"]["normal_download"]
	else: #Info page
		direct_url = find_direct_url(metadata["file_info"]["links"]["normal_download"])
		#If couldn't find a download link; There needs to be an additional check because mediafire's API still returns info about files which were taken down
		if(direct_url["success"] == 0):
			with PRINT_LOCK:
				log("\033[90m{}: \033[0m\033[31mCouldn't find download url\033[0m".format(mediafire_id))
			return 0
		metadata["location"] = direct_url["location"]
		direct_url = direct_url["url"]

	#Download file
	if not only_meta:
		if archive_mode:
			output_dir = output + "/keys/" + mediafire_id
			output_fname = output_dir + "/" + metadata["file_info"]["filename"]
		else:
			output_dir = output[0:output.rfind('/')]
			output_fname = output
		os.makedirs(output_dir, exist_ok=True)
		download_url(direct_url, output_fname)
	#Write metadata
	if archive_mode or only_meta:
		with open(output + "/keys/" + mediafire_id + ".info.json", "w") as fl:
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

def download_folder(mediafire_id, output_dir, only_meta=0, archive=[], archive_mode=False):
	#Recursively downloads a folder
	#Returns 1 on success and 0 otherwise
	metadata = get_folder_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		with PRINT_LOCK:
			log("\033[90m{}: \033[0m\033[31m{}: {}\033[0m".format(mediafire_id, metadata["result"], metadata["message"]))
		return (0, None) #Skip folder

	with PRINT_LOCK:
		log("\033[90m{}: {}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m".format(mediafire_id,
		                                                                       metadata["folder_info"]["created"],
		                                                                       metadata["folder_info"]["owner_name"],
		                                                                       metadata["folder_info"]["name"]))

	metadata["children"] = {"folders": [], "files": []}
	folder_contents = ((metadata["folder_info"]["name"], mediafire_id), [])

	#Download folders inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"):
		children_folders_chunk = get_folder_content(mediafire_id, "folders", chunk)
		metadata["children"]["folders"] += children_folders_chunk["folder_content"]["folders"]
		more_chunks = children_folders_chunk["folder_content"]["more_chunks"]
		chunk+=1
	for folder in metadata["children"]["folders"]:
		folder_contents[1].append(folder["folderkey"])

	#Download files inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"):
		children_files_chunk = get_folder_content(mediafire_id, "files", chunk)
		metadata["children"]["files"] += children_files_chunk["folder_content"]["files"]
		more_chunks = children_files_chunk["folder_content"]["more_chunks"]
		chunk+=1
	for fl in metadata["children"]["files"]:
		folder_contents[1].append(fl["quickkey"])

	#Download avatar
	avatar_keys = analyze_mediafire.get_mediafire_links(metadata["folder_info"]["avatar"])["keys"]
	for avatar in avatar_keys: #There should be only 1 key in an avatar link, but loop through it just to be sure
		folder_contents[1].append(avatar)

	#Write metadata
	if archive_mode or only_meta:
		if(os.path.exists(output_dir + "/keys/" + mediafire_id + ".info.json")): #Don't overwrite the .info.json file
			log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
			return (1, folder_contents)
		with open(output_dir + "/keys/" + mediafire_id + ".info.json", "w") as fl:
			fl.write(json.dumps(metadata))

	return (1, folder_contents)

def download(mediafire_id, output, only_meta=0, archive=[], archive_mode=False):
	#Download mediafire key and save it in output
	#In case of a mediafire error return 0
	#In case of an exception - retry after 10 seconds
	#Otherwise return 1
	while(1): #Retry until download returns
			with PRINT_LOCK:
				log("\033[90m{}: Downloading...\033[0m".format(mediafire_id))
			try:
				if(mediafire_id.startswith("/conv/")): #Conv link
					with ARCHIVE_LOCK:
						if archive_mode:
							output_file = output + mediafire_id
						else:
							output_file = output
						if(os.path.exists(output_file) or (mediafire_id in archive)): #Duplicate
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return (1, None)
						archive.append(mediafire_id)
					if(download_url("https://mediafire.com" + mediafire_id, output_file) == 200): #Success
						log("\033[90m{}: \033[0m\033[96mDownloaded\033[0m".format(mediafire_id))
						return (1, None)
					else:
						log("\033[90m{}: \033[0m\033[31mNot found!\033[0m".format(mediafire_id))
						return (0, None)
				elif(len(mediafire_id) in [11, 15, 31]): #Single file
					with ARCHIVE_LOCK:
						known_path_exists = False
						if only_meta or archive_mode:
							known_path_exists = os.path.exists(output + "/keys/" + mediafire_id + ".info.json")
						if(known_path_exists or (mediafire_id in archive)): #Duplicate
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return (1, None)
						archive.append(mediafire_id)
					return (download_file(mediafire_id, output, only_meta=only_meta, archive_mode=archive_mode), None)
				elif(len(mediafire_id) in [13, 19]): #Folder
					with ARCHIVE_LOCK:
						#Redownload contents even if .info.json file exists (without overwriting it) but skip if another thread already started downloading it
						if(mediafire_id in archive):
							log("\033[90m{}:\033[0m \033[33mFile already exists. Skipping...\033[0m".format(mediafire_id))
							return (1, None)
						archive.append(mediafire_id)
					return download_folder(mediafire_id, output, only_meta=only_meta, archive=archive, archive_mode=archive_mode)
			except Exception:
				with PRINT_LOCK:
					archive.remove(mediafire_id)
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

def worker(args, output, mediafire_id, archive):
	(download_successful, folder_contents) = download(mediafire_id, output, only_meta=args.only_meta, archive=archive, archive_mode=args.archive_mode)
	return (output, folder_contents)

if(__name__ == "__main__"):
	#CLI front end

	parser = argparse.ArgumentParser(description="Mediafire downloader")
	parser.add_argument("--only-meta", action="store_true", help="Only download *.info.json files")
	parser.add_argument("--threads", type=int, default=6, help="How many threads to use; in case mediafire starts showing captchas or smth the amount of threads should be reduced; default is 6")
	parser.add_argument("--archive-mode", "-a", dest="archive_mode", action="store_true", help="Use a flat directory layout and save all file metadata in *.info.json files")
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
	if args.archive_mode or args.only_meta:
		os.makedirs(args.output + "/keys", exist_ok=True)
		os.makedirs(args.output + "/conv", exist_ok=True)

	#Download
	archive = []
	task_queue = queue.Queue()

	with multiprocessing.Pool(6) as pool:
		def callback(child_info):
			output_base = child_info[0]
			folder_contents = child_info[1]
			if folder_contents is None:
				return
			if args.archive_mode or args.only_meta:
				# Flat directory structure
				output = args.output
			else:
				# Nest children in this folder
				folder_name = folder_contents[0][0]
				if "/" in folder_name or ".." == folder_name:
					with PRINT_LOCK:
						log("Dangerous name {} for folder with id {}".format(folder_name, folder_contents[0][1]))
					folder_name = folder_contents[0][1]
				output = output_base + "/" + folder_name
			for id in folder_contents[1]:
				task_queue.put(pool.apply_async(worker, args=(args, output, id, archive,), callback=callback))

		for conv_link in mediafire_urls["conv"]: #Download conv links
			task_queue.put(pool.apply_async(worker, args=(args, args.output, conv_link, archive,), callback=callback))

		for mediafire_id in mediafire_urls["keys"]: #Download keys
			task_queue.put(pool.apply_async(worker, args=(args, args.output, mediafire_id, archive,), callback=callback))

		while not task_queue.empty():
			task = task_queue.get()
			task.wait()
			try:
				task.get()
			except Exception as e:
				log(e)
