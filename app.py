# app.py
# /roach2_nuraghe/data/"

# app.py

import os
import state
import sys # Import sys to access command-line arguments
import threading
import configparser
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# Import functions from fits_watcher.py, including the new set_monitor_directory
from fits_watcher import start_fits_monitor, stop_fits_monitor, set_socketio_instance, set_monitor_directory

app = Flask(__name__)
app.config['SOCKETIO_LOGGER'] = False
app.config['DEBUG'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'
socketio = SocketIO(app, cors_allowed_origins="*")

fits_observer = None

# --- Configuration File Handling ---
CONFIG_FILE_PATH = os.path.join(app.root_path, 'static', 'config.ini')



def _create_default_config():
    """
    Creates a default config.ini file if it doesn't exist.
    """
    config = configparser.ConfigParser()
    config['Drives'] = {
        'local_drive':  os.path.abspath(os.path.join(app.root_path, 'fits_files')), # Relative path for local debugging
        'remote_drive_1': '/roach2_nuraghe/data' # Absolute path example for remote
    }
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, 'w') as configfile:
        config.write(configfile)
    print(f"Created default config.ini at: {CONFIG_FILE_PATH}")
    print("Please edit this file to configure your actual mounted drive paths.")

def _get_drive_paths_from_config():
    """
    Reads drive paths from the config.ini file.
    Returns a dictionary of drive names to absolute paths, or None if config fails.
    """
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE_PATH):
        _create_default_config()
        # After creating, attempt to read again
        config.read(CONFIG_FILE_PATH)
    else:
        config.read(CONFIG_FILE_PATH)

    drive_paths = {}
    if 'Drives' in config:
        for drive_name, drive_path in config['Drives'].items():
            # If path is relative (e.g., 'fits_files'), make it absolute relative to app root
            # If path is already absolute (e.g., '/mnt/my_remote_drive'), abspath just normalizes it.
            # drive_paths[drive_name] = os.path.abspath(os.path.join(app.root_path, drive_path))
            drive_paths[drive_name] = drive_path
    else:
        print("ERROR: No '[Drives]' section found in config.ini. Monitoring will not start.")
        return None
    return drive_paths

def _check_mounted_drives(drive_paths):
    """
    Checks the status of each configured mounted drive and logs it.
    """
    print("\n--- Checking Configured Mounted Drives ---")
    if drive_paths:
        for drive_name, full_path in drive_paths.items():
            if os.path.isdir(full_path):
                print(f"Drive '{drive_name}' ({full_path}): MOUNTED and accessible.")
            else:
                print(f"Drive '{drive_name}' ({full_path}): NOT MOUNTED or inaccessible. Please check the path and mount status.")
    else:
        print("No drive paths found in config.ini to check.")
    print("-------------------------------------------\n")

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def test_connect():
    print('Client connected:', threading.current_thread().name)
    emit('status', {'data': 'Connected'})

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected:', threading.current_thread().name)

@socketio.on('update_feed_selection')
def handle_feed_selection(data):
    """
    It receives the new selected feed from the front-end and updates the global variable.
    """
    # Extra check: be sure that the feed number is an integer and manage the errors
    try:
        # 1. Ottiene e converte il nuovo Feed (new_feed � una variabile locale)
        new_feed = int(data.get('feed', 0))

        # 2. check and update the global state only if the value has changed
        if new_feed != state.CURRENT_SELECTED_FEED:
            
            # update value inside the module 'state'
            state.CURRENT_SELECTED_FEED = new_feed
            
            print(f"=====================================================")
            print(f"SERVER STATE UPDATE: Feed selected to: {state.CURRENT_SELECTED_FEED}")
            print(f"=====================================================")
    
            # (Optional: it is also possible to send a confirmation on the feed selected on the front-end)
            # emit('feed_selection_confirmed', {'feed': CURRENT_SELECTED_FEED})
    except ValueError:
        print(f"ERRORE: No integer value for feed received: {data.get('feed')}")

    # ...


# --- Application Startup and Shutdown ---
def start_app():
    global fits_observer

    # 1. Parse command-line arguments
    is_debug_mode = '-d' in sys.argv

    # 2. Get drive paths from config.ini
    drive_paths = _get_drive_paths_from_config()
    if not drive_paths:
        print("Exiting: Could not load drive configurations from config.ini.")
        return

    # 3. Determine which drive to monitor
    monitor_path = None
    if is_debug_mode:
        monitor_path = drive_paths.get('local_drive')
        if not monitor_path:
            print("ERROR: 'local_drive' not found in config.ini. Cannot start in debug mode.")
            return
        print(f"Starting in DEBUG MODE. Monitoring LOCAL drive: {monitor_path}")
    else:
        # Get the remote_drive_1 path
        monitor_path = drive_paths.get('remote_drive_1')
        if not monitor_path:
            print("ERROR: 'remote_drive_1' not found in config.ini. Cannot start without debug mode.")
            return

        # Attempt to get the authenticated username (the username coincides with the project id)
        # This would be typically used in production mode so that only the project id subfolders are monitored (it requires less machine resources)       
        # In development mode (i.e. using the hpcdev machine) we need to comment all the next lines of code until point #4
        # This because the project id would be 'fschirru' which does not exists inside the '/roach2_nuraghe/data' system

        username = None
        try:
            # os.getlogin() gets the user logged into the controlling tty
            # os.getenv('USER') or os.getenv('USERNAME') are more robust in some environments
            username = os.getlogin()
        except OSError:
            # Fallback if os.getlogin() fails (e.g., in some non-interactive environments)
            username = os.getenv('USER') or os.getenv('USERNAME')

        if username:
            # Join the remote_drive_1 path with the username
            monitor_path = os.path.join(monitor_path, username)
            print(f"Authenticated user: '{username}'.")
            print(f"Starting in PRODUCTION MODE. Monitoring REMOTE drive (user specific): {monitor_path}")
        else:
            print("WARNING: Could not determine authenticated username. Monitoring remote drive without user-specific subdirectory.")
            print(f"Starting in PRODUCTION MODE. Monitoring REMOTE drive (generic): {monitor_path}")

    # 4. Check status of all configured drives (for informational purposes)
    _check_mounted_drives(drive_paths)

    # 5. Set the determined monitor directory in fits_watcher
    set_monitor_directory(monitor_path)

    # 6. Pass the SocketIO instance to the fits_watcher module
    set_socketio_instance(socketio)

    # 7. Start the FITS file monitor
    fits_observer = start_fits_monitor()
    if fits_observer is None: # Check if start_fits_monitor failed (e.g., directory creation failed)
        print("FITS file monitor failed to start. Application will not monitor files.")
        return # Exit if monitor didn't start

    # 8. Run the Flask-SocketIO server
    socketio.run(app, debug=False, allow_unsafe_werkzeug=True, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    try:
        start_app()
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    finally:
        # Stop the FITS file monitor gracefully when the application shuts down
        if fits_observer:
            stop_fits_monitor(fits_observer)

            print("Application gracefully stopped.")

   
