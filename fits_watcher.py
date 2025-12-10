# fits_watcher.py

import os
import re # Import the regular expression module
import threading
# Import PollingObserver specifically for more reliable monitoring on network/remote drives
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import time

# Import the processing functions from the fits_processor.py file
from fits_processor import process_fits_file, set_socketio_instance_for_processor

# Global variable to hold the directory to monitor.
# It's initialized to a default, but can be updated by set_monitor_directory.
MONITOR_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fits_files_default') # Changed to 'default'

# --- NEW: Use a regex pattern for FITS extensions ---
# This regex matches:
# - '.fits' (literally)
# - OR '.fits' followed by one or more digits (e.g., .fits0, .fits12, .fits999)
# The re.IGNORECASE flag makes the match case-insensitive (e.g., .FITS, .FiTs10)

FITS_EXTENSION_PATTERN = re.compile(r'\.fits(\d+)?$', re.IGNORECASE)


# Define subfolders to be explicitly excluded from processing, case-insensitive
EXCLUDED_SUBFOLDERS = {'tempfits', 'tmp'}

# Global variable to hold the SocketIO instance, to be set by app.py
_socketio_instance = None

# Set to store paths of files that are currently being processed or have been queued for processing.
# This helps prevent duplicate processing if watchdog triggers multiple events for the same file.
_processing_files = set()
_processing_lock = threading.Lock() # To ensure thread-safe access to _processing_files


def set_monitor_directory(path):
    """
    Sets the directory that the FITS file watcher should monitor.
    This function allows app.py to dynamically configure the monitoring path.

    Args:
        path (str): The absolute path to the directory to monitor.
    """
    global MONITOR_DIRECTORY
    MONITOR_DIRECTORY = os.path.abspath(path) # Ensure it's an absolute path
    print(f"Monitor directory set to: {MONITOR_DIRECTORY}")



def set_socketio_instance(sio):
    """
    Sets the SocketIO instance for fits_watcher.py and passes it
    to fits_processor.py. This function is called by app.py.

    Args:
        sio (SocketIO): The Flask-SocketIO instance from app.py.
    """
    global _socketio_instance
    _socketio_instance = sio
    set_socketio_instance_for_processor(sio) # Pass it down to the processor module
    print("SocketIO instance passed to fits_watcher.py (and fits_processor.py)")


class FitsFileHandler(FileSystemEventHandler):
    """
    Custom event handler for watchdog. It monitors the specified directory
    for new .fits files and triggers their processing via fits_processor.py.
    """
    def on_created(self, event):
        """
        Called when a new file or directory is created.
        We only care about files ending with the defined FITS extensions,
        whose filenames do not start with 'Sum', and which are not located
        in excluded temporary subfolders ('tempfits', 'tmp').

        Args:
            event (FileSystemEvent): The event object representing the file system change.
        """

        if event.is_directory:
            return # Ignore directory creation events

        filepath = event.src_path
        filename_base = os.path.basename(filepath)
        lower_filename_base = filename_base.lower() # Convert to lowercase once for multiple checks

        # 1. Check if the file ends with any of the defined FITS extensions using regex
        # This will match '.fits', '.fits0', '.fits123', etc. (case-insensitive)
        if not FITS_EXTENSION_PATTERN.search(filename_base): # Search in original case for filename_base
            print(f"File '{filename_base}' skipped: Not a recognized FITS extension.") # Optional: uncomment for verbose logging
            return # Not a FITS file, ignore

        # 2. Exclude files whose filename starts with 'Sum', 'Sum_', or 'summary' (case-insensitive)
        if lower_filename_base.startswith('sum') or \
           lower_filename_base.startswith('sum_') or \
           lower_filename_base.startswith('summary'):
            print(f"File '{filename_base}' skipped: Filename starts with 'Sum', 'Sum_', or 'summary'.")
            return # Ignore this file
       
        # 3. Exclude files located in specified temporary subfolders ('tempfits', 'tmp')
        file_dir = os.path.dirname(filepath)
        # Normalize paths for consistent comparison across operating systems
        norm_monitor_dir = os.path.normpath(MONITOR_DIRECTORY)
        norm_file_dir = os.path.normpath(file_dir)

        # Ensure the file's directory is actually within the monitored directory (or is it)
        if norm_file_dir.startswith(norm_monitor_dir):
            # Get the path components relative to the monitor directory
            relative_path = os.path.relpath(norm_file_dir, norm_monitor_dir)
            # Split the relative path into individual folder names
            path_components = {comp.lower() for comp in relative_path.split(os.sep) if comp} # Convert to set of lowercase components

            # Check if any component matches an excluded subfolder
            if len(EXCLUDED_SUBFOLDERS.intersection(path_components)) > 0:
                print(f"File '{filename_base}' skipped: Located in an excluded temporary subfolder ({filepath}).")
                return # Ignore this file

        # If all checks pass, proceed with processing
        with _processing_lock:
            if filepath in _processing_files:
                print(f"File {os.path.basename(filepath)} is already being processed or was processed. Skipping duplicate event.")
                return
            _processing_files.add(filepath)

        print(f"\n--- Detected new FITS file: {os.path.basename(filepath)} ---")



        threading.Thread(target=self._safe_process_file, args=(filepath,)).start()


    def _safe_process_file(self, filepath):
        """
        A wrapper function to call `process_fits_file` and ensure that the file's path
        is removed from the `_processing_files` set after processing is complete,
        regardless of whether the processing succeeded or failed.

        Args:
            filepath (str): The path to the file being processed.
        """
        try:
            process_fits_file(filepath)
        finally:
            # Ensure the file is removed from the processing set in a thread-safe manner.
            with _processing_lock:
                if filepath in _processing_files:
                    _processing_files.remove(filepath)
                    print(f"Finished processing and removed {os.path.basename(filepath)} from processing list.")


def start_fits_monitor():
    """
    Initializes and starts the watchdog PollingObserver for FITS files.
    This observer periodically scans the directory, making it more reliable
    for monitoring network-mounted or remote drives where native OS events
    might not be consistently propagated.

    Returns:
        PollingObserver: The watchdog PollingObserver instance, which can be
                         used to stop the monitoring gracefully.
    """
    event_handler = FitsFileHandler()
    # Use PollingObserver for robust monitoring, especially on network drives.
    # The 'interval' parameter (in seconds) defines how often the directory is scanned.
    # Adjust this value based on your needs for responsiveness vs. system resource usage.
    observer = PollingObserver(1) # Example: polls every 5 seconds
    # Schedule the event handler to monitor the directory non-recursively (only direct files).
    observer.schedule(event_handler, MONITOR_DIRECTORY, recursive=True)
    observer.start() # Start the observer thread.
    print(f"FITS file monitor started for directory: {MONITOR_DIRECTORY}")
    return observer

def stop_fits_monitor(observer):
    """
    Stops the watchdog observer gracefully.

    Args:
        observer (Observer): The watchdog Observer instance returned by `start_fits_monitor`.
    """
    if observer:
        observer.stop() # Stop the observer thread.
        observer.join() # Wait for the observer thread to terminate.
        print("FITS file monitor stopped.")
