# fits_watcher.py

import os
import re
import threading
import time
# PollingObserver is used for more reliable monitoring on network/remote drives (NFS/Lustre)
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# Import processing logic from the fits_processor module
from fits_processor import process_fits_file, set_socketio_instance_for_processor

# Global list to hold multiple monitoring paths
MONITOR_DIRECTORIES = [] 

# Regex pattern for FITS extensions (matches .fits, .fits0, .fits12, etc.)
# The re.IGNORECASE flag makes the match case-insensitive
FITS_EXTENSION_PATTERN = re.compile(r'\.fits(\d+)?$', re.IGNORECASE)

# Subfolders explicitly excluded from processing
EXCLUDED_SUBFOLDERS = {'tempfits', 'tmp'}

# Global variable to hold the SocketIO instance
_socketio_instance = None

# Set and lock to handle thread-safe duplicate file detection
_processing_files = set()
_processing_lock = threading.Lock()


def set_monitor_directories(paths):
    """
    Sets the list of directories that the FITS file watcher should monitor.
    This function allows app.py to dynamically configure multiple monitoring paths.

    Args:
        paths (list): A list of absolute paths to monitor.
    """
    global MONITOR_DIRECTORIES
    MONITOR_DIRECTORIES = [os.path.abspath(p) for p in paths]
    for p in MONITOR_DIRECTORIES:
        print(f"ICHNOS: Added to monitor list: {p}")


def set_socketio_instance(sio):
    """
    Sets the SocketIO instance and passes it to the processor module.
    """
    global _socketio_instance
    _socketio_instance = sio
    set_socketio_instance_for_processor(sio)
    print("SocketIO instance synchronized in fits_watcher.py")


class FitsFileHandler(FileSystemEventHandler):
    """
    Custom watchdog event handler to monitor directories for new FITS files.
    """
    def on_created(self, event):
        if event.is_directory:
            return 

        filepath = event.src_path
        filename_base = os.path.basename(filepath)
        lower_filename_base = filename_base.lower()

        # 1. Extension check using Regex
        if not FITS_EXTENSION_PATTERN.search(filename_base):
            return 

        # 2. Exclude summary or cumulative files
        if lower_filename_base.startswith(('sum', 'sum_', 'summary')):
            print(f"File '{filename_base}' skipped: Starts with 'Sum' or 'summary'.")
            return 
       
        # 3. Dynamic subfolder exclusion check across all monitored roots
        file_dir = os.path.normpath(os.path.dirname(filepath))
        is_excluded = False
        
        for root_dir in MONITOR_DIRECTORIES:
            norm_root = os.path.normpath(root_dir)
            # Check if the file belongs to this specific root directory
            if file_dir.startswith(norm_root):
                # Calculate relative path to identify subfolder names
                relative_path = os.path.relpath(file_dir, norm_root)
                path_components = {c.lower() for c in relative_path.split(os.sep) if c}
                
                # Skip the file if it is located in an excluded subfolder (e.g., 'tmp')
                if EXCLUDED_SUBFOLDERS.intersection(path_components):
                    is_excluded = True
                    break
        
        if is_excluded:
            print(f"Skipping file '{filename_base}': Located in excluded folder.")
            return

        # 4. Thread-safe duplicate check
        with _processing_lock:
            if filepath in _processing_files:
                print(f"File {filename_base} is already being processed. Skipping duplicate event.")
                return
            _processing_files.add(filepath)

        print(f"\n--- [ICHNOS] Detected new FITS file: {filename_base} ---")

        # Launch processing in a separate thread to keep the watcher responsive
        threading.Thread(target=self._safe_process_file, args=(filepath,)).start()


    def _safe_process_file(self, filepath):
        """
        Wrapper to ensure file is removed from the processing set regardless of success/failure.
        """
        try:
            process_fits_file(filepath)
        finally:
            with _processing_lock:
                if filepath in _processing_files:
                    _processing_files.remove(filepath)
                    print(f"Finished processing and removed {os.path.basename(filepath)} from processing list.")


def start_fits_monitor():
    """
    Starts the PollingObserver for all directories in MONITOR_DIRECTORIES.
    Polling is preferred for network-mounted drives (NFS/Lustre).
    """
    if not MONITOR_DIRECTORIES:
        print("Error: MONITOR_DIRECTORIES list is empty. Monitoring cannot start.")
        return None

    event_handler = FitsFileHandler()
    
    # Scans directories every 1 second (interval can be adjusted)
    observer = PollingObserver(1) 
    
    # Schedule each valid directory for monitoring
    for directory in MONITOR_DIRECTORIES:
        if os.path.isdir(directory):
            observer.schedule(event_handler, directory, recursive=True)
        else:
            print(f"Warning: Directory not found, skipping: {directory}")
    
    observer.start()
    print(f"FITS file monitor started for {len(MONITOR_DIRECTORIES)} paths.")
    return observer


def stop_fits_monitor(observer):
    """
    Stops the observer thread gracefully.
    """
    if observer:
        observer.stop()
        observer.join()
        print("FITS file monitor stopped.")