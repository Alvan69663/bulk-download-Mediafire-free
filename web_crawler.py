#!/bin/env python3
import argparse, threading, queue, ipaddress, os, analyze, analyze_mediafire, requests, time, traceback

timeout_t = 30
http_headers = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0" #Spoof firefox user agent
}
scrape_content_type = ["text/plain", "text/html"]
#Don't verify certificates so sites with expired certificates will also work
#This will allow MITM attacks on https sites, but if that's the case then the
#scraper getting incorrect links is the least of your problems
verify_certificates=False
requests.packages.urllib3.disable_warnings()

STATUS_NOT_WORKING = 0
STATUS_WORKING = 1
STATUS_ERROR = 2

MAX_RETRIES = 5

def worker(download_queue, output, output_list, archive, print_lock, output_lock, archive_lock, url_filter, thread_id, threads_working, threads_working_lock):
	while(1):
		#Get element from the queue
		threads_working_lock.acquire()
		threads_working[thread_id] = STATUS_NOT_WORKING
		threads_working_lock.release()
		url = download_queue.get(block=1)
		threads_working_lock.acquire()
		threads_working[thread_id] = STATUS_WORKING
		threads_working_lock.release()

		#Download page
		retries = MAX_RETRIES
		skip_get = 1 #If a suitable is determined later
		while((retries > 0)):
			try:
				#Determine if content type is suitable
				web_rq = requests.head(url, headers=http_headers, timeout=timeout_t, allow_redirects=True, verify=verify_certificates)
				web_headers = web_rq.headers
				for content_type in scrape_content_type:
					if(content_type in web_headers.get("Content-Type")):
						skip_get = 0
						break
				if(skip_get): #Skip based on content type
					print_lock.acquire()
					print("\033[90mThread #{}\033[0m \033[93mSkipping\033[0m {}".format(thread_id, url))
					print_lock.release()
				else:
					print_lock.acquire()
					print("\033[90mThread #{}\033[0m \033[95mScraping\033[0m \033[96mstatus={}\033[0m {}".format(thread_id, web_rq.status_code, url))
					print_lock.release()
					web_html = requests.get(url, headers=http_headers, timeout=timeout_t, verify=verify_certificates).text
				break
			except Exception:
				print_lock.acquire()
				traceback.print_exc()
				print("\033[90mThread #{}\033[0m \033[31mError while downloading \033[0m{}\033[31m! Retrying in 2 minutes ({} retries remaining)\033[0m".format(thread_id, url, retries))
				print_lock.release()
				threads_working_lock.acquire()
				threads_working[thread_id] = STATUS_ERROR
				threads_working_lock.release()
				time.sleep(60*2)
				retries-=1
		if(retries == 0):
			print_lock.acquire()
			print("\033[90mThread #{}\033[0m \033[31mMax number of retries exceeded on\033[0m {}\033[31m!\033[0m".format(thread_id, url))
			print_lock.release()
			continue
		elif(retries<MAX_RETRIES):
			threads_working_lock.acquire()
			threads_working[thread_id] = STATUS_WORKING #Working again
			threads_working_lock.release()
		if(skip_get):
			continue

		#Get urls
		html_urls = analyze.get_urls(web_html)
		for html_url in html_urls:
			html_url_no_schema = analyze.truncate_schema(html_url)
			try: #Skip private ip addresses
				if(ipaddress.ip_address(html_url_no_schema).is_private):
					print_lock.acquire()
					print("\033[31mSkipping local address\033[0m {}".format(html_url_no_schema))
					print_lock.release()
					continue
			except ValueError:
				pass

			if(("mediafire.com" in html_url) or ("mfi.re" in html_url)): #If mediafire
				output_lock.acquire()
				already_downloaded = 0
				if(html_url_no_schema in output_list):
					already_downloaded = 1
				if(not already_downloaded):
					with open(output, "a") as fl:
						fl.write(html_url)
						fl.write("\n")
					output_list.append(html_url_no_schema)
					print_lock.acquire()
					print("\033[90mThread #{}\033[0m \033[92mFound\033[0m {}".format(thread_id, html_url))
					print_lock.release()
				output_lock.release()
			else: #Recurse into every site which isn't mediafire
				if(not url_filter in html_url): #Filter url
					continue
				archive_lock.acquire()
				already_downloaded = 0
				if(html_url_no_schema in archive):
					already_downloaded = 1
				if(not already_downloaded):
					download_queue.put(html_url)
					archive.append(html_url_no_schema)
				archive_lock.release()

if(__name__ == "__main__"):
	#CLI front end
	parser = argparse.ArgumentParser(description="Mediafire link web scraper")
	parser.add_argument("--threads", type=int, default=6, help="How many threads to use; if the site you're trying to crawl will start displaying captchas or smth the amount of threads should be reduced; default is 6")
	parser.add_argument("--filter", default="", help="Only scrape websites where filter is found in the url")
	parser.add_argument("start", help="Start URL from which the scraper will begin to recursively scrape pages")
	parser.add_argument("output", help="File where a list of scraped pages will be saved")

	args = parser.parse_args()

	#If archive or output file doesn't exist create it
	if(not os.path.exists(args.output)):
		with open(args.output, 'w'): pass

	#Start workers
	output_list = []
	archive = []
	worker_list = []
	print_lock = threading.Lock()
	output_lock = threading.Lock()
	archive_lock = threading.Lock() #Should also be locked while reading to avoid race conditions
	threads_working_lock = threading.Lock()
	download_queue = queue.Queue()
	download_queue.put(args.start)
	threads_working = [0]*args.threads #Keep track of which threads are working
	for i in range(args.threads):
		current_worker = threading.Thread(target=worker,
		                                  daemon=True,
		                                  args=(download_queue, args.output, output_list, archive, print_lock, output_lock, archive_lock, args.filter, i, threads_working, threads_working_lock,))
		current_worker.start()
		worker_list.append(current_worker)
	#Monitor threads
	any_thread_alive = 1
	while(any_thread_alive):
		time.sleep(15)

		threads_working_lock.acquire()
		threads_working_copy = threads_working.copy() #Copy thread status
		threads_working_lock.release()
		#Check if any thread is alive
		any_thread_alive = 0
		for i in range(args.threads):
			if(threads_working_copy[i]):
				any_thread_alive = 1
				break

		#Show thread status
		for i in range(args.threads):
			thread_color = ""
			if(threads_working_copy[i] == 0): thread_color = "\033[31m"
			elif(threads_working_copy[i] == 1): thread_color = "\033[32m"
			elif(threads_working_copy[i] == 2): thread_color = "\033[33m"
			threads_working_copy[i] = thread_color + str(i) + "\033[0m"
		print_lock.acquire()
		print("\033[90mThread status:\033[0m " + "".join(threads_working_copy))
		print_lock.release()
