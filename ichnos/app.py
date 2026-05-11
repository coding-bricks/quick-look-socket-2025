# app.py
# Base data directory: /roach2_nuraghe/data/

from ichnos import state
from ichnos import bokeh_server
from ichnos.fits_watcher import (
    start_fits_monitor,
    stop_fits_monitor,
    set_socketio_instance,
    set_monitor_directories
)

import os
import secrets
import sys  # It allows to access command-line arguments
import threading
import configparser
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
# New import for embedding Bokeh apps in Flask
from bokeh.embed import server_document



# This is the main repo folder where 'static' and 'template' folders are located
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
#app = Flask(__name__)
app.config['SOCKETIO_LOGGER'] = False
app.config['DEBUG'] = False
#app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SECRET_KEY'] = secrets.token_hex(32)
#socketio = SocketIO(app, cors_allowed_origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

fits_observer = None

# --- Configuration File Handling ---
#CONFIG_FILE_PATH = os.path.join(app.root_path, 'static', 'config.ini')
CONFIG_FILE_PATH = os.path.join(BASE_DIR, 'static', 'config.ini')


def _create_default_config():
    """
    Creates a default config.ini file if it does not exist.
    """
    config = configparser.ConfigParser()
    config['Drives'] = {
        # Relative path used for local debugging
        'local_drive': os.path.abspath(os.path.join(BASE_DIR, 'fits_files')),
        # Example absolute paths for remote environments
        'remote_drive_1': '/roach2_nuraghe/data',
        'remote_drive_2': '/another_drive/data'
    }
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, 'w') as configfile:
        config.write(configfile)
    print(f"Created default config.ini at: {CONFIG_FILE_PATH}")


def _get_drive_paths_from_config():
    """
    Reads drive paths from the config.ini file.
    Returns a dictionary mapping drive names to paths.
    """
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE_PATH):
        _create_default_config()
        config.read(CONFIG_FILE_PATH)
    else:
        config.read(CONFIG_FILE_PATH)

    drive_paths = {}
    if 'Drives' in config:
        for drive_name, drive_path in config['Drives'].items():
            drive_paths[drive_name] = drive_path
    else:
        print("ERROR: No '[Drives]' section found in config.ini.")
        return None

    return drive_paths


def _check_mounted_drives(drive_paths):
    """
    Checks the accessibility status of each configured drive.
    """
    print("\n--- Checking Configured Mounted Drives ---")
    if drive_paths:
        for drive_name, full_path in drive_paths.items():
            if os.path.isdir(full_path):
                print(f"Drive '{drive_name}' ({full_path}): MOUNTED and accessible.")
            else:
                print(f"Drive '{drive_name}' ({full_path}): NOT MOUNTED or inaccessible.")
    print("-------------------------------------------\n")


# --- Flask Routes ---
@app.route('/')
def index():
    bokeh_url = "http://localhost:5006"
    
    # Generiamo il gancio per la mappa
    map_script = server_document(url=bokeh_url + "/map_viewer")
    
    # Generiamo il gancio per lo spettro monitor
    spec_script = server_document(url=bokeh_url + "/spectrum_monitor")

    # Supponiamo di sapere cosa mostrare in base a una logica o allo stato
    current_type = 'map' if state.IS_MAP else 'spectrum'

    return render_template(
        'index.html',
        map_script=map_script,
        spec_script=spec_script,
        spectrum_type=current_type  # <--- Fondamentale per l'IF nel template
    )
    


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
    try:
        new_feed = int(data.get('feed', 0))
        if new_feed != state.CURRENT_SELECTED_FEED:
            state.CURRENT_SELECTED_FEED = new_feed
            print(f"SERVER STATE UPDATE: Feed selected to: {state.CURRENT_SELECTED_FEED}")
    except ValueError:
        print(f"ERROR: Non-integer feed value received: {data.get('feed')}")

@socketio.on('request_initial_state')
def handle_initial_state():
    # Invia lo switch mappa/spettro
    emit('check_mode', {'is_map': state.IS_MAP})
    
    if state.LAST_FULL_DATA_PACKET:
        emit('new_fits_data', state.LAST_FULL_DATA_PACKET)
    else:
        # Se non c'� nulla, possiamo mandare un segnale di "Reset"
        # o semplicemente lasciare che l'utente veda i campi vuoti
        print("Pagina sincronizzata: in attesa di nuovi dati.")


# --- Application Startup and Shutdown ---
def start_app():
    global fits_observer

    # 1. Parse command-line arguments
    is_debug_mode = '-d' in sys.argv
    is_user_mode = '-u' in sys.argv

    # --- Check for incompatible flags ---
    if is_debug_mode and is_user_mode:
        print("ERROR: Options '-d' (debug) and '-u' (user mode) cannot be used together.")
        sys.exit(1)

    # --- Log operating mode ---
    if is_debug_mode:
        print("\n[MODE] DEBUG MODE (-d): using local drive\n")
    elif is_user_mode:
        print("\n[MODE] USER MODE (-u): using username-based subdirectories\n")
    else:
        print("\n[MODE] DEFAULT MODE: using base paths from config.ini\n")  

    # 2. Load drive paths from config.ini
    drive_paths = _get_drive_paths_from_config()
    if not drive_paths:
        print("Exiting: Unable to load drive configuration.")
        return

    # 3. Determine which directories should be monitored
    valid_paths = []

    if is_debug_mode:
        monitor_path = drive_paths.get('local_drive')
        if monitor_path and os.path.isdir(monitor_path):
            valid_paths.append(os.path.abspath(monitor_path))
            print(f"Starting in DEBUG MODE. Monitoring local drive: {monitor_path}")
    else:
        if is_user_mode:
            # --- USER-BASED MODE ---
            # Determine the authenticated username for production subdirectories
            username = None
            try:
                username = os.getlogin()
            except OSError:
                username = os.getenv('USER') or os.getenv('USERNAME')

            # Collect all configured remote drives
            for drive_key, base_path in drive_paths.items():
                if drive_key.startswith('remote_drive'):
                    full_path = os.path.join(base_path, username) if username else base_path
                    if os.path.isdir(full_path):
                        valid_paths.append(os.path.abspath(full_path))
                        print(f"Adding to monitor list: {full_path}")
                    else:
                        print(f"Drive '{drive_key}' path not found/accessible: {full_path}")
        
        else:
            # --- DEFAULT MODE ---
            # Extract the base path directly from the config.ini file
            for drive_key, base_path in drive_paths.items():
                if drive_key.startswith('remote_drive'):
                    if os.path.isdir(base_path):
                        valid_paths.append(os.path.abspath(base_path))
                        print(f"[DEFAULT MODE] Adding base path: {base_path}")
                    else:
                        print(f"[DEFAULT MODE] Path not found/accessible: {base_path}")

    if not valid_paths:
        print("ERROR: No valid directories found to monitor. Check config.ini and mount points.")
        return

    # 3.5 initialize the map_cash 
    state.initialize_map_cache()

    # 4. Log the status of all drives
    _check_mounted_drives(drive_paths)

    # 5. Set the list of directories to be monitored by fits_watcher
    set_monitor_directories(valid_paths)

    # 6. Pass the SocketIO instance to the fits_watcher module
    set_socketio_instance(socketio)

    # 7. Start monitoring FITS files
    fits_observer = start_fits_monitor()
    if fits_observer is None:
        print("FITS monitor failed to start. File monitoring disabled.")
        return

    # 7.5. Start the Bokeh server with multiple applications
    try:
        # Definiamo le applicazioni e le loro funzioni di setup
        # Assicurati che 'spec_app' sia definita o importata da bokeh_server
        apps_to_load = {
            '/map_viewer': bokeh_server.map_app,
            '/spectrum_monitor': bokeh_server.spec_app
        }
        
        # Passiamo il dizionario invece della singola stringa
        bokeh_server.start_bokeh_server(port=5006, apps=apps_to_load)
        print("BOKEH: Visualization server started with Map and Spectrum apps.")
        
    except Exception as e:
        print(f"CRITICAL ERROR: Unable to start Bokeh server: {e}")

   

    # 8. Start the Flask-SocketIO server
    # Server in 'Development' mode
    '''
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=True,
        #allow_unsafe_werkzeug=True,
        use_reloader=False
    )'''

    # Server in 'Production' mode
    
    socketio.run( 
        app, 
        host='0.0.0.0', 
        port=5000,
        debug=False,
        use_reloader=False
    )

   



def main():
    try:
        start_app()
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    finally:
        global fits_observer
        if fits_observer:
            stop_fits_monitor(fits_observer)
            print("Application gracefully stopped.")

if __name__ == "__main__":
    main()


