# Description
mf-dl is a command line program for downloading mediafire links in bulk. It also contains a web crawler which can be used for searching for mediafire links.

# Running on Windows:
1. Download and install python3 from their [website](https://www.python.org/)
2. Clone this repo
3. Open the command line
4. Go to the directory with mf-dl using `cd DIRECTORY`
5. Install all of the dependencies using `python3 -m pip install -r requirements.txt`

# Running on GNU/Linux:
1. Clone this repo
2. Go to the directory containing mf-dl
3. Using your package manager install python3 and download all of the dependencies manually or run `python3 -m pip install -r requirements.txt` in the directory with mf-dl to install them automatically

# mfdl.py
	usage: mfdl.py [-h] [--only-meta] [--archive ARCHIVE] [--threads THREADS]
	               output input [input ...]
	
	Mediafire downloader
	
	positional arguments:
	  output             Output directory
	  input              Input file/files which will be searched for links
	
	optional arguments:
	  -h, --help         show this help message and exit
	  --only-meta        Only download *.info.json files and avatars
	  --archive ARCHIVE  File used to determine which files were already
	                     downloaded
	  --threads THREADS  How many threads to use; in case mediafire starts showing
	                     captchas or smth the amount of threads should be reduced;
	                     default is 6

# web_crawler.py
	usage: web_crawler.py [-h] [--threads THREADS]
	                      [--filter FILTER | --regex REGEX]
	                      start output

	Mediafire link web scraper

	positional arguments:
	  start              Start URL from which the scraper will begin to
	                     recursively scrape pages
	  output             File where a list of links will be saved

	optional arguments:
	  -h, --help         show this help message and exit
	  --threads THREADS  How many threads to use; if the site you're trying to
	                     crawl will start displaying captchas or smth the amount
	                     of threads should be reduced; default is 6
	  --filter FILTER    Only scrape websites where filter is found in the url
	  --regex REGEX      Same as filter but uses regex

# Directory structure:
* File: keys/\*/FILENAME
* File and folder metadata: keys/\*.info.json
* Conv links: conv/\*
* Keys of custom folder names: custom_folders.txt

File keys are always 11, 15 or 31 characters long and folder keys are 13 or 19 characters long.
Folder metadata files contain references to file or folder keys to avoid downloading the same file in a directory
and as a stand alone file. Navigating through folders is a bit of a pain in the ass atm but I plan on making a tool to browse
saved archives

# Supported links
* http(s)://\*.mediafire.com/?KEY
* http(s)://\*.mediafire.com/\*/KEY
* http(s)://\*.mediafire.com/\*.php?KEY
* http(s)://\*.mediafire.com/convkey/\*/KEY??.EXT
* http(s)://\*.mediafire.com/CUSTOM_FOLDER_NAME
* http(s)://\*.mediafire.com/CONV_NAME.EXT (no metadata)
* http(s)://\*.mediafire.com/conv/CONV_NAME.EXT (no metadata)
* mfi.re domain
* Obfuscated versions of the above e.g. mediafire (.) com (/) (?) KEY
