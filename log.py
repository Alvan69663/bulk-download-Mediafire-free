import threading
from colorama import init
init() #This should fix ansi escape codes on windows TODO: test it

def log(msg):
	thread_name = threading.current_thread().name
	if(thread_name != "MainThread"):
		print("\033[90mThread #{}\033[0m ".format(thread_name), end="")
	print(msg)
