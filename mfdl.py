#!/bin/env python3
import requests, json, os, traceback, time, random, sys, argparse, queue, threading

timeout_t = 30
http_headers = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0" #Spoof firefox user agent
}

def download_url(url, local_filename):
	#Don't overwrite
	if(os.path.exists(local_filename)):
		return
	#Save url as local_filename
	r = requests.get(url, headers=http_headers, stream=True, timeout=timeout_t)
	with open(local_filename, 'wb') as f:
		for chunk in r.iter_content(chunk_size=1024): 
			if chunk: # filter out keep-alive new chunks
				f.write(chunk)

def get_file_metadata(file_id):
	#Get "response" key from mediafire's file/get_info.php API function
	rq = requests.post("https://www.mediafire.com/api/1.5/file/get_info.php", params={"quick_key": file_id, "response_format": "json"}, headers=http_headers, timeout=timeout_t)
	return rq.json()["response"]

def find_direct_url(info_url):
	#Find a direct download url on an info page
	rq = requests.get(info_url, headers=http_headers, timeout=timeout_t)
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

def download_file(mediafire_id, output_dir, only_meta=0, download_info=""):
	#Returns 1 on success and 0 otherwise
	metadata = get_file_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		download_info += "\033[31m{}: {}\033[0m\n".format(metadata["result"], metadata["message"])
		return {"success": 0, "download_info": download_info} #Skip file
	
	#Display info
	download_info += "\033[90m{}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m".format(metadata["file_info"]["created"],
	                                                                                metadata["file_info"]["owner_name"],
	                                                                                metadata["file_info"]["filename"])

	#Individually shared files point to an info page, but files shared in a folder point directly to the file
	dwnld_head = requests.head(metadata["file_info"]["links"]["normal_download"], headers=http_headers, timeout=timeout_t).headers
	if(str(dwnld_head.get("Location")).startswith("https://download")): #Direct
		direct_url = metadata["file_info"]["links"]["normal_download"]
	else: #Info page
		direct_url = find_direct_url(metadata["file_info"]["links"]["normal_download"])
		#If couldn't find a download link; There needs to be an additional check because mediafire's API still returns info about files which were taken down
		if(direct_url["success"] == 0):
			download_info += "\033[31m{}\033[0m\n".format("Couldn't find download url")
			return {"success": 0, "download_info": download_info}
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
	download_info += "\n"
	return {"success": 1, "download_info": download_info}

def get_folder_content(folder_key, content_type, chunk):
	#Get "response" key from mediafire's folder/get_info.php API function
	rq = requests.get("https://www.mediafire.com/api/1.4/folder/get_content.php",
	                  params={"content_type": content_type, "chunk": chunk, "folder_key": folder_key, "response_format": "json"},
					  headers=http_headers,
					  timeout=timeout_t)
	return rq.json()["response"]

def get_folder_metadata(folder_key):
	#Get "response" key from mediafire's folder/get_info.php API function
	rq = requests.post("https://www.mediafire.com/api/1.5/folder/get_info.php", params={"folder_key": folder_key, "response_format": "json"}, headers=http_headers, timeout=timeout_t)
	return rq.json()["response"]

def download_folder(mediafire_id, output_dir, level=0, only_meta=0, download_info=""):
	#Recursively downloads a folder
	#Returns 1 on success and 0 otherwise
	metadata = get_folder_metadata(mediafire_id)
	if(metadata["result"] != "Success"): #Error from mediafire
		download_info += "\033[31m{}: {}\033[0m\n".format(metadata["result"], metadata["message"])
		return {"success": 0, "download_info": download_info} #Skip folder

	download_info += "\033[90m{}\033[0m \033[96m{}\033[0m \033[95m{}\033[0m\n".format(metadata["folder_info"]["created"],
	                                                                                  metadata["folder_info"]["owner_name"],
	                                                                                  metadata["folder_info"]["name"])

	metadata["children"] = {"folders": [], "files": []}

	#Download folders inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"): #TODO: find a folder with >100 elements to check if chunking works ; setting chunk_size only works for sizes 100-1000
		children_folders_chunk = get_folder_content(mediafire_id, "folders", chunk)
		metadata["children"]["folders"] += children_folders_chunk["folder_content"]["folders"]
		more_chunks = children_folders_chunk["folder_content"]["more_chunks"]
	for folder in metadata["children"]["folders"]:
		download_info += download(folder["folderkey"], output_dir, level=level+1, only_meta=only_meta)["download_info"]

	#Download files inside
	chunk = 1
	more_chunks = True
	while(more_chunks != "no"):
		children_files_chunk = get_folder_content(mediafire_id, "files", chunk)
		metadata["children"]["files"] += children_files_chunk["folder_content"]["files"]
		more_chunks = children_folders_chunk["folder_content"]["more_chunks"]
	for fl in metadata["children"]["files"]:
		download_info += download(fl["quickkey"], output_dir, level=level+1, only_meta=only_meta)["download_info"]
	
	#Write metadata
	with open(output_dir + "/" + mediafire_id + ".info.json", "w") as fl:
		fl.write(json.dumps(metadata))
	#Download avatar
	avatar_fname = metadata["folder_info"]["avatar"][::-1] #Get the filename
	avatar_fname = avatar_fname[:avatar_fname.find("/")][::-1]
	os.makedirs(output_dir + "/avatars", exist_ok=True)
	download_url(metadata["folder_info"]["avatar"], output_dir + "/avatars/" + avatar_fname)
	return {"success": 1, "download_info": download_info}

def download(mediafire_id, output_dir, level=0, only_meta=0, download_info=""):
	#Download mediafire key and save it in output_dir
	#Returns {"success": int, "download_info": str}
	#msg is a short description of a downloaded file/files
	#In case of a mediafire error - success=0
	#In case of an exception - retry after 10 seconds
	#Otherwise success=1
	download_info += "  "*level + "\033[90m{}\033[0m ".format(mediafire_id)
	sys.stdout.flush()
	while(1): #Retry until download returns
			try:
				if(len(mediafire_id) == len("tsw4yx1ns4c87cf")): #Single file
					return download_file(mediafire_id, output_dir, only_meta=only_meta, download_info=download_info)
				elif(len(mediafire_id) == len("eis9b1dahdcw3")): #Folder
					return download_folder(mediafire_id, output_dir, level=level, only_meta=only_meta, download_info=download_info)
			except Exception:
				traceback.print_exc()
				print("Error while downloading! Retrying in 10s...")
				time.sleep(10)

def worker(args, download_queue, archive_lock, print_lock, thread_id):
	while(mediafire_id := download_queue.get(block=0)):
			download_info = download(mediafire_id, args.output, only_meta=args.only_meta)
			print_lock.acquire()
			print("\033[90mThread #{}\033[0m ".format(thread_id) + download_info["download_info"], end="")
			print_lock.release()
			if(download_info["success"]):
				archive.append(mediafire_id)
				if(args.archive):
					archive_lock.acquire()
					with open(args.archive, "a") as fl:
						fl.write(mediafire_id)
						fl.write("\n")
					archive_lock.release()
			time.sleep(random.random())

if(__name__ == "__main__"):
	#CLI front end
	import analyze_mediafire
	
	parser = argparse.ArgumentParser(description="Mediafire downloader")
	parser.add_argument("--only-meta", action="store_true", help="Only download *.info.json files and avatars")
	parser.add_argument("--archive", help="File used to determine which files were already downloaded")
	parser.add_argument("--threads", type=int, default=6, help="How many threads to use; in case mediafire starts showing captchas or smth the amount of threads should be reduced; default is 6")
	parser.add_argument("output", help="Output directory")
	parser.add_argument("input", nargs="+", help="Input file/files which will be searched for links")
	args = parser.parse_args()

	#Open archive
	archive = []
	if(args.archive):
		if(not os.path.exists(args.archive)):
			with open(args.archive, 'w'): pass
		with open(args.archive, "r") as fl:
			archive += fl.read().splitlines()

	#Get ids
	id_lists = analyze_mediafire.get_mediafire_urls(args.input)
	id_list = []
	id_list += id_lists["files"]
	id_list += id_lists["dirs"]

	#Download
	archive_lock = threading.Lock()
	print_lock = threading.Lock()
	worker_list = []
	download_queue = queue.Queue()

	for mediafire_id in id_list:
		if(mediafire_id in archive):
			continue #Skip if already downloaded
		download_queue.put(mediafire_id)

	for i in range(args.threads): #Launch threads
		thread = threading.Thread(target=worker, args=(args, download_queue, archive_lock, print_lock, i,))
		thread.start()
		worker_list.append(thread)
