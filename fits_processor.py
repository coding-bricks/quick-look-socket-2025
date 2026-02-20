# fits_processor.py


from typing import Dict, List, Tuple, Any

from math import pi
import os
import re
import state
import threading
import time
import numpy as np # For generating dummy plot data
import nodding_manager # <--- ASSICURATI CHE IL MODULO SIA ACCESSIBILE


import threading
import map_gridding # Worker B


from astropy.io import fits
from flask_socketio import SocketIO
from bokeh.plotting import figure, column, show # Import Bokeh plotting tools
from bokeh.resources import CDN # For CDN resources (JS/CSS)
from bokeh.palettes import Category10
from bokeh.models import LinearAxis, Range1d
from bokeh_server import update_bokeh_plot, update_scatter_plot, reset_scatter_plot
from bokeh.embed import file_html # For saving plot to HTML


from bokeh_visuals import _plot_and_save_skarab_nodding_html, _plot_and_save_html

# Variabile per tenere traccia del thread di grigliatura attivo
gridding_thread = None


# Global variable for SocketIO instance
_socketio_instance = None

# Define the directory for saving plots within static
# Ensure this directory exists relative to app.py
PLOT_SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'plots')

# Create the plots directory if it doesn't exist
if not os.path.exists(PLOT_SAVE_DIR):
    os.makedirs(PLOT_SAVE_DIR)
    print(f"Created Bokeh plots directory: {PLOT_SAVE_DIR}")

def set_socketio_instance_for_processor(sio):
    """
    Sets the SocketIO instance that will be used to emit events to clients
    from the FITS processor. Called by fits_watcher.py.
    """
    global _socketio_instance
    _socketio_instance = sio
    print("SocketIO instance passed to fits_processor.py")

def _wait_for_file_completion(filepath, timeout=300, check_interval=0.5, stable_checks=3):
    """
    Robustly waits for a file to stop growing in size, indicating it has
    been completely written to disk. This is crucial for handling files
    that are being actively transferred or generated, preventing premature
    attempts to read incomplete files.
    Adjusted default 'timeout' for better handling of network latency.

    Args:
        filepath (str): The full path to the file to monitor.
        timeout (int): The maximum number of seconds (float) to wait before giving up.
                       Increased default to 300 seconds (5 minutes) for network drives.
        check_interval (float): The time (in seconds) to pause between file size checks.
        stable_checks (int): The number of consecutive times the file size must remain
                             unchanged before considering it "stable" (fully written).

    Returns:
        bool: True if the file became stable within the timeout, False otherwise.
    """
    print(f"Waiting for {os.path.basename(filepath)} to be completely written...")
    start_time = time.time()
    last_size = -1 # Initialize with an invalid size to ensure first check updates it
    stable_count = 0 # Counter for consecutive stable size checks

    while True:
        # Check if timeout has been reached
        if time.time() - start_time > timeout:
            print(f"Timeout waiting for {os.path.basename(filepath)} to complete. Last recorded size: {last_size} bytes.")
            return False

        # Check if the file still exists (it might be moved or deleted during waiting)
        if not os.path.exists(filepath):
            print(f"File {os.path.basename(filepath)} disappeared while waiting.")
            return False

        try:
            current_size = os.path.getsize(filepath)
        except OSError as e:
            # Handle cases where the file might be temporarily locked or inaccessible
            print(f"Warning: Could not get size of {os.path.basename(filepath)}: {e}. Retrying in {check_interval}s...")
            time.sleep(check_interval)
            continue # Skip to the next iteration

        if current_size == last_size:
            # File size is stable, increment counter
            stable_count += 1
            if stable_count >= stable_checks:
                # File has been stable for enough checks, consider it complete
                print(f"File {os.path.basename(filepath)} appears stable at {current_size} bytes.")
                return True
        else:
            # File size has changed, reset stable counter and update last size
            stable_count = 0
            last_size = current_size

        time.sleep(check_interval) # Wait before checking again


def _extract_data_and_perform_averages(filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, backend, freq, lo, bw, sub_scan_type, subscan):

     # ----------------------------------------------------------------------
    # START TIME: Inizio della funzione
    start_time_total = time.time()
    print(f"\n--- PROFILING INIZIATO: {filename_prefix} ---")

    data = []
    data_map_stokes = [] 
    averages = []
    averages_stokes = []

    feed_number = 0 # default value for multi-feed
    
    try:
        # --- SEZIONE 1: I/O DISCO e CALCOLO MEDIA (Potenziale bottleneck I/O/CPU) ---
        start_time_io_calc = time.time()

        # 1 - Extract Data and computes the averages through multiple raws (single spectra) of the FITS file
        with fits.open(filepath) as hdul:

            # Recupero dei dati (stessa logica esistente)
            if(filename_extension == '.fits'):
                
                # ... (Logica di estrazione SARDARA/TotalPower/SKARAB .fits) ...
                if(backend != 'SKARAB'):
                    for i in range(len(feeds)):
                        # Data are dynamically retrieved according to the feed number
                        # For dual polarization and feed number 6, for example columns are Ch6 LL and Ch7 RR
                        if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
                            index = feeds[i]*2
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                            index = (feeds[i]*2)+1
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                        else:
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{feeds[i]}"]))
                else: # SKARAB
                    
                    # SKARAB files have fixed colum names Ch0 and Ch1
                    if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
                        data.append(np.array(hdul["DATA TABLE"].data[f"Ch0"]))
                        data.append(np.array(hdul["DATA TABLE"].data[f"Ch1"]))
                    else: # case STOKES
                        data.append(np.array(hdul["DATA TABLE"].data[f"Ch0"]))
                        # The above line oc code should be like (to be understood if each sub-spectrum is 1024 in lenght...):
                        # data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 0:1024]))
                        # data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 1024:2048]))
                        # data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 2048:3072]))
                        # data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 3072:4096]))

            else: # case .fits# i.e. multi-feed (SARDARA only, SKARAB is always .fits with the feed number specified within the filename)
                
                # ... (Logica di estrazione SARDARA multi-feed .fits#) ...
                feed_number = filename_extension.removeprefix('.fits')
                if(spectrum_type == 'spectra'):
                    
                    index = int(feed_number)*2
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                    index = (int(feed_number)*2)+1
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                
                else: # case Stokes
                    
                    # If we want to generate Maps with Stokes data we need to split the data into 4 chunks (polarizations LL, RR, RL, LR)
                    # Stokes data are stored in a single 1024 channels spectra -> [0:255][256:511][512:767][768:1023]
                    # Then we can add the RR and LL data
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 0:1024]))
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 1024:2048]))
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 2048:3072]))
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 3072:4096]))
                    
                    
                    #data_map_stokes.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 0:1024]))
                    #data_map_stokes.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 1024:2048]))
                    #data_map_stokes.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 2048:3072]))
                    #data_map_stokes.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][:, 3072:4096]))
                    #data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][0:256]))
                    #data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"][256:512]))
            
            # Get the hpbw for grid mapping    
            hpbw_arcsec = calculate_hpbw(float(freq), 64, k_factor=1.22)
            print(f'hpbw in arcsec {hpbw_arcsec}')     
            
            # -------------------------------------------------------------------
            # ?? AGGIORNAMENTO DELLO STATO GLOBALE HPBW ??
            # -------------------------------------------------------------------
            state.GLOBAL_HPBW_ARCSEC = hpbw_arcsec
            
            # Check whether FITS file is part of a map or a single spetrum
            is_map = is_map_by_keyword(sub_scan_type)
            print(f'FITS file relative to a map: {is_map}')

            # -------------------------------------------------------------------
            # ?? Update of the GLOBAL STATE of the COORDINATE SYSTEM ??
            # -------------------------------------------------------------------
      
            if sub_scan_type == 'RA' or sub_scan_type == 'DEC':

                state.CURRENT_COORD_SYSTEM = "AZEL"
            else:
                state.CURRENT_COORD_SYSTEM = "RADEC"

            # Update the spectrum type i.e. 'simple', 'spectra', 'stokes'
            state.SPECTRUM_TYPE = spectrum_type

            if data:

                if not is_map:

                    if(state.IS_MAP):

                        reset_dashboard() # The dashboard is composed by the map and the spectrum in time
                        state.IS_MAP = False

                    # The next condition discriminates for single point data (i.e. TP) or array data (i.e. SARDARA, SKARAB)
                    if(type(data[0][0]) == np.ndarray): # case SARDARA, SKARAB

                        # ----------------------------------------------------
                        # CASO 1: SPETTRO QUICK-LOOK (Media Verticale)
                        # La media viene calcolata per ogni canale lungo l'asse 0 (tempo/righe).
                        # Risultato: array 1D (Spettro Medio).
                        # ----------------------------------------------------
                        print("MODE: SPECTRA (Vertical Averaging)")
                        for i in range(len(data)):
                            averages.append(np.nanmean(data[i], axis=0)) # <--- MEDIA VERTICALE
                            
                        # Creazione asse X (Canali)
                        x = np.linspace(0, len(averages[0]), len(averages[0]))
                        x_axis_label_val = 'Channel'

                    else:

                        # Caso TOTAL POWER (Singolo punto per riga)
                        for i in range(len(data)):
                            # Qui data[i] � gi� un array di singoli punti (la serie temporale)
                            averages.append(data[i]) 
                    
                        # Creazione asse X (Punti Campione)
                        x = np.linspace(0, len(averages[0]), len(averages[0]))
                        x_axis_label_val = 'Sampling Point'

                    # Calcolo frequenze per l'asse superiore
                    f_min_val = float(freq)
                    f_max_val = f_min_val + float(bw)

                    # Caricamento nel dizionario condiviso
                    state.CURRENT_SPEC.update({
                        'x': x,               # Canali (0..65535)
                        'averages': averages, # Lista di array delle polarizzazioni
                        'f_min': f_min_val,   # Inizio banda MHz
                        'f_max': f_max_val,   # Fine banda MHz
                        'filename': filename_prefix,
                        'legend_labels': [f"Feed {f}" for f in feeds],
                        'spectrum_type': spectrum_type,
                        'updated': True       # Notifica il server
                    })

                    set_tab_labels(spectrum_type)

                   
                    #state.CURRENT_SPEC['updated'] = True

                    # --- DEBUG CHECK ---
                    print("--- [DEBUG DIZIONARIO STATE] ---")
                    print(f"Titolo: {state.CURRENT_SPEC['filename']}")
                    print(f"Tipo Spettro: {state.CURRENT_SPEC['spectrum_type']}")
                    print(f"Tab Labels: {state.CURRENT_SPEC['tab_labels']}")
                    print(f"Legend Labels: {state.CURRENT_SPEC['legend_labels']}")
                    print(f"Frequenze: {state.CURRENT_SPEC['f_min']} MHz - {state.CURRENT_SPEC['f_max']} MHz")

                    # Verifica i dati numerici
                    n_array = len(state.CURRENT_SPEC['averages'])
                    print(f"Numero di array (polarizzazioni/feed): {n_array}")
                    if n_array > 0:
                        print(f"Lunghezza primo array: {len(state.CURRENT_SPEC['averages'][0])} canali")
                        print(f"Primi 5 valori primo array: {state.CURRENT_SPEC['averages'][0][:5]}")

                    print("---------------------------------")

                    # ----------------------------------------------------------------------
                    # TIMER 1: Tempo di I/O Disco (fits.open/hdul.data) e Calcolo Media (np.mean)
                    end_time_io_calc = time.time()
                    print(f"PROFILING: [Timer 1] I/O Disco + Calcolo Media completato in {end_time_io_calc - start_time_io_calc:.4f} secondi.")

                    #return _plot_and_save_html(PLOT_SAVE_DIR, filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, 
                    #    backend, x_axis_label_val, x, averages, feed_number, start_time_total, freq, lo, bw)

                else: # is a map

            
                    state.IS_MAP = True

                    # If the subscan number is smaller or equal than that stored in the state.py 
                    # the map is re-initialized because we are starting with a new map
                    if(subscan <= state.LAST_PROCESSED_SUBSCAN_ID):

                        reset_dashboard()
                       



                    # --- GENERAZIONE ASSE X (FREQUENZE) ---
                    # The X AXIS is generated only once
                    # Supponendo che tu abbia estratto freq (f_iniziale) e bw (larghezza banda) dall'header
                    # e che 'chs' sia il numero di canali (es. 1024)

                    
                
                    if(spectrum_type == 'stokes'):

                        chs_pol = data[0].shape[1]

                    else:

                        chs_pol = chs

                    # change the x-axis values dynamically. If spectrum_type == 'simple' i.e. TotalPower use chs for the x axis 
                    if(spectrum_type == 'simple'): # TotalPower

                        chs_pol = len(data[0])
                        print('simple - chs_pol', chs_pol)
                        # Creiamo l'array lineare in numero di canali
                        state.LAST_SPECTRUM_X = np.linspace(0, chs_pol, chs_pol)

                    else:

                        if state.LAST_SPECTRUM_X.size == 0:  # Lo calcoliamo solo se non � gi� presente

                            f_start = float(freq)
                            f_end = f_start + float(bw)
                        
                            print('chs_pol', chs_pol)
                            # Creiamo l'array lineare dei MHz per ogni canale
                            state.LAST_SPECTRUM_X = np.linspace(f_start, f_end, chs_pol)
                    

                    # ----------------------------------------------------
                    # CASO 2: MAPPA (Media Orizzontale)
                    # La media viene calcolata per ogni riga lungo l'asse 1 (canali).
                    # Risultato: array 1D (Potenza P_i) per ogni riga.
                    # ----------------------------------------------------
                    print("MODE: MAP (Horizontal Averaging for P_i)")
                    # Nota: Poich� stiamo mappando, di solito si assume la prima polarizzazione/feed
                    # se ci sono dati duplicati, ma qui manteniamo la struttura esistente:

                    # Check the type of Map i.e. RA-DEC or AZ-EL
                    # We get the answer from th value of sub_sca_type

                    # ----------------------------------------------------
                    # ESTRAZIONE COORDINATE RA/DEC o AZ/EL
                    # ----------------------------------------------------
                    x_data, y_data = _extract_coordinates_for_map(hdul, sub_scan_type)
                    print(f"COORDINATE: Tipo {sub_scan_type} estratte con {x_data.size} punti.")

                    all_pi_data = []

                    print(f'Selected feed for mapping: {state.CURRENT_SELECTED_FEED}')

                    # The next condition discriminates for single point data (i.e. TP) or array data (i.e. SARDARA, SKARAB)
                    if(type(data[0][0]) == np.ndarray): # case SARDARA, SKARAB
       
                        for i in range(len(data)):
                            # Esegui la media orizzontale (lungo i canali)
                            pi_data = np.nanmean(data[i], axis=1) # <--- MEDIA ORIZZONTALE (Potenza P_i)
                            
                            # In modalit� MAPPA, 'averages' conterr� le P_i di tutte le polarizzazioni/feeds
                            # di quel file, ma tipicamente per la mappa userai SOLO il primo set.
                            averages.append(pi_data) 
                            all_pi_data.append(pi_data) # Raccogli tutti i P_i per i metadata
                    
                        # For spectrum_type == 'stokes' we would need to add also data[2] and data[3]
                        state.LAST_SPECTRUM_POL0 = np.nanmean(data[0], axis=0)
                        state.LAST_SPECTRUM_POL1 = np.nanmean(data[1], axis=0)
                        
                        # Una volta calcolati entrambi, segnaliamo a Bokeh che pu� aggiornare
                        state.SPECTRUM_UPDATED = True
                
                    else:

                        # Here we need to filter data only for the selected feed
                        # For TP the average coincides with the data point having only one channel per raw

                        averages.append(data[state.CURRENT_SELECTED_FEED])
                        averages.append(data[state.CURRENT_SELECTED_FEED+1])

                        all_pi_data.append(data[state.CURRENT_SELECTED_FEED]) # Raccogli tutti i P_i per i metadata
                        all_pi_data.append(data[state.CURRENT_SELECTED_FEED+1]) # Raccogli tutti i P_i per i metadata

                        # For spectrum_type == 'stokes' we would need to add also data[2] and data[3]
                        state.LAST_SPECTRUM_POL0 = data[0]
                        state.LAST_SPECTRUM_POL1 = data[1]
                                                
                        # Una volta calcolati entrambi, segnaliamo a Bokeh che pu� aggiornare
                        state.SPECTRUM_UPDATED = True

                    # L'asse X in questo caso non � il canale, ma il Punto Campione (la riga)
                    # Questi P_i verranno poi accoppiati con RA/DEC.
                    x = np.linspace(0, len(averages[0]), len(averages[0]))
                    x_axis_label_val = 'Sampling Point'

                    # --- AGGIORNAMENTO DELLE DUE NUVOLA DI PUNTI ---

                    if len(all_pi_data) >= 2:
                        print("Rilevati dati per due polarizzazioni. Inizio aggiornamento Dual-Pol.")

                        # CHIAMATA ESECUTIVA
                        update_global_point_cloud_dual_pol(
                            x_data_new=x_data, 
                            y_data_new=y_data, 
                            all_pi_data_new=all_pi_data # Passa [P_i_Pol0, P_i_Pol1]
                        )

                        # Trigger Asincrono
                        trigger_gridding_process() # <--- LA CHIAMATA � QUI

                            
                    elif len(all_pi_data) == 1:
                        print("Rilevati dati per singola polarizzazione/feed. Nessuna azione di aggiornamento dual-pol.")
                        # Potresti aggiungere qui una logica per gestire il singolo feed se necessario
                        
                    # --- SUCCESSIVAMENTE: ATTIVAZIONE GRIGLIATORE ASINCRONO (Worker B) ---
                    # worker_b.trigger_regridding()
                        
                # fine blocco if not is_map / else    
                # Update subscan number to state.py
                state.LAST_PROCESSED_SUBSCAN_ID = subscan
                    
            else:
                raise Exception("Nessun dato estratto dal file FITS.")
        
    
    except Exception as e:
        print(f"ERRORE GRAVE nel calcolo delle medie per {filename_prefix}: {e}")
        print("---------------------------------------")
        return None



def _extract_skarab_nodding_data(filepath, spectrum_type, start_time_total):
    """
    Estrae i dati (Ch0 e/o Ch1) da un singolo file SKARAB Nodding e calcola le medie.
    La logica dipende dal tipo di spettro (SPECTRA/SIMPLE vs STOKES).
    
    Returns:
        dict: Contenente 'averages', 'x', 'x_axis_label_val', 'spectrum_type', o None in caso di errore.
    """
    data = []
    averages = []
    x = None
    
    try:
        with fits.open(filepath) as hdul:
            data_table_columns = hdul["DATA TABLE"].columns.names
            
            # --- LOGICA DI ESTRAZIONE SKARAB (come richiesto) ---

            
            if spectrum_type in ['spectra', 'simple']:
                # Caso SPECTRA/SIMPLE: Dati in due canali (Ch0 e Ch1)
                if 'Ch0' in data_table_columns and 'Ch1' in data_table_columns:
                    data.append(np.array(hdul["DATA TABLE"].data["Ch0"]))
                    data.append(np.array(hdul["DATA TABLE"].data["Ch1"]))
                else:
                    print(f"SKARAB NODDING EXTRACT: Canali Ch0/Ch1 non trovati per tipo '{spectrum_type}'.")
                    return None
            
            elif spectrum_type == 'stokes':
                # Caso STOKES: Tutti i dati sono in un unico canale (Ch0)
                if 'Ch0' in data_table_columns:
                    data.append(np.array(hdul["DATA TABLE"].data["Ch0"]))
                    # The above line oc code should be like (to be understood if each sub-spectrum is 1024 in lenght...):
                    # data.append(np.array(hdul["DATA TABLE"].data["Ch0"][:, 0:1024]))
                    # data.append(np.array(hdul["DATA TABLE"].data["Ch0"][:, 1024:2048]))
                    # data.append(np.array(hdul["DATA TABLE"].data["Ch0"][:, 2048:3072]))
                    # data.append(np.array(hdul["DATA TABLE"].data["Ch0"][:, 3072:4096]))

                else:
                    print(f"SKARAB NODDING EXTRACT: Canale Ch0 non trovato per tipo '{spectrum_type}'.")
                    return None
            
            else:
                 print(f"SKARAB NODDING EXTRACT: Tipo di spettro '{spectrum_type}' non gestito.")
                 return None

        if data and data[0].ndim == 2:
            # Calcolo della media lungo l'asse del tempo (axis=0)
            for item in data:
                # np.nanmean per gestione di eventuali NaN (sicurezza)
                averages.append(np.nanmean(item, axis=0)) 
            
            # Creazione asse X (Canali)
            x = np.linspace(0, len(averages[0]), len(averages[0]))
            x_axis_label_val = 'Channel'


            
            return {
                'averages': averages, 
                'x': x, 
                'x_axis_label_val': x_axis_label_val, 
                'spectrum_type': spectrum_type,
                'start_time_total': start_time_total # Utile per il logging finale
            }
            
        else:
            print(f"SKARAB NODDING EXTRACT: Dati non validi o non 2D in {os.path.basename(filepath)}")
            return None
            
    except Exception as e:
        print(f"SKARAB NODDING EXTRACT: Errore durante l'estrazione dati da {os.path.basename(filepath)}: {e}")
        return None



def process_fits_file(filepath):
    """
    Manages the processing of a detected .fits file.
    It first waits for the file to be fully written, then attempts to
    extract its primary header, generates a plot, and emits both
    to the frontend via SocketIO. This function is called by fits_watcher.py.
    """
    
    # Wait for the file to become stable (fully written)
    if not _wait_for_file_completion(filepath):
        print(f"Skipping processing of {os.path.basename(filepath)}: File did not stabilize or disappeared.")
        return

    try:
        with fits.open(filepath) as hdul:

            print(f"\n--- Primary Header Keywords and Values for {os.path.basename(filepath)} ---")

            # ?? NUOVA LOGICA: ESTRAZIONE E FILTRO ??
            header_data, acq_feeds_unique_values, should_process = extract_metadata_and_filter(filepath, hdul)

            if not should_process:
                return # File scartato dal filtro feed


            # ----------------------------------------------------------------------
            # ?? PUNTO DI DISCRIMINAZIONE E INOLTRO AL NODDING MANAGER
            # ----------------------------------------------------------------------

            if header_data.get("backend") == 'SKARAB' and header_data.get("acq_type") == 'DUAL':
        
                # Chiama il Nodding Manager per accoppiare il file.
                # Il manager restituisce i file accoppiati (filepath_A, filepath_B) SOLO se la coppia � completa.
                coupled_files = nodding_manager.check_and_pair_skarab_nodding(filepath)
                
                if coupled_files:
                    # ?? Accoppiamento completato. Avviamo l'elaborazione ad-hoc in un thread separato.
                    # L'elaborazione Nodding � bloccante (I/O + Calcolo), quindi � bene usare un thread.
                    
                    # Estrazione dei metadati di accoppiamento necessari (common_prefix, feed_IDs)
                    # Dobbiamo riottenere common_prefix e i feed IDs dato che il manager ha solo restituito i path.
                    
                    # Usiamo il pattern regex per re-estrarre i dati necessari da uno dei file accoppiati
                    base_filename = os.path.basename(coupled_files[0])
                    match = nodding_manager.SKARAB_NODDING_PATTERN.search(base_filename)
                    common_prefix = match.group(1) if match else os.path.splitext(base_filename)[0]
                    
                    # Estrazione degli ID di Feed e tipo di spettro (ricarica l'header se necessario)
                    try:
                        # Estraiamo l'ID di Feed e il tipo di spettro dai metadati originali
                        feed_A_id = _get_skarab_feed_id_from_path(coupled_files[0])
                        feed_B_id = _get_skarab_feed_id_from_path(coupled_files[1])
                        
                        with fits.open(coupled_files[0]) as hdul_A:
                            spectrum_type_pair = hdul_A["SECTION TABLE"].data["type"][0]
                
                    except Exception as e:
                        print(f"SKARAB NODDING: Impossibile estrarre metadati per la coppia. Errore: {e}")
                        return # Interrompiamo il processo se i metadati non sono validi
                    
                    # Avviamo il processo Nodding nel thread
                    threading.Thread(
                        target=process_skarab_nodding_pair, 
                        args=(coupled_files, common_prefix, feed_A_id, feed_B_id, spectrum_type_pair, header_data)
                    ).start()
                    
                    return # <--- INTERRUZIONE: L'elaborazione Nodding � gestita.
                
                else:
                    # File registrato, ma non � ancora pronto per l'accoppiamento.
                    return # <--- INTERRUZIONE: In attesa del partner.

            # ----------------------------------------------------------------------
            # ?? CONTINUAZIONE DEL FLUSSO NORMALE (NON NODDING O SKARAB MONO/MULTI)
            # ----------------------------------------------------------------------

        backend = header_data["backend"]
        freq = header_data["frequency"]
        lo =  header_data["lo"] 
        bw = header_data["bandwidth"]

        

        filename_base = os.path.splitext(os.path.basename(filepath))[0]
        filename_extension = os.path.splitext(os.path.basename(filepath))[1]

        # --- Get data and generate the Bokeh plot ---
        # plot_url = create_and_save_bokeh_plot___(filepath)

        _extract_data_and_perform_averages(filepath, filename_base, filename_extension, 
            acq_feeds_unique_values, int(header_data.get("bins")), header_data.get("spectrum"), backend, freq, lo, bw, header_data.get("sub_scan_type"),
            int(header_data["header"]["SubScanID"]))
        
        
        '''
        plot_url = _extract_data_and_perform_averages(filepath, filename_base, filename_extension, 
            acq_feeds_unique_values, int(header_data.get("bins")), header_data.get("spectrum"), backend, freq, lo, bw, header_data.get("sub_scan_type"),
            int(header_data["header"]["SubScanID"]))

            
        if plot_url:
            header_data["plot_url"] = plot_url
            print(f"Plot URL added to data: {plot_url}")
        else:
            print("No plot URL generated for this FITS file.")
        '''

        if _socketio_instance:
            print(f"Emitting FITS header and plot URL for {os.path.basename(filepath)} to frontend.")
            _socketio_instance.start_background_task(
                _socketio_instance.emit, 'fits_header_update', header_data
            )
        else:
            print("Warning: SocketIO instance not set in fits_processor.py, cannot emit header data.")

    except Exception as e:

        print(f"Error processing FITS file {os.path.basename(filepath)}: {e}")



def process_skarab_nodding_pair(filepaths_tuple, common_prefix, feed_A_id, feed_B_id, spectrum_type, primary_header_data):
    """
    Orchestra l'elaborazione di una coppia di file SKARAB per il Nodding.
    Chiama le funzioni ad-hoc di estrazione e plotting, includendo il profiling del tempo.
    
    Args:
        filepaths_tuple (tuple): (percorso_file_A, percorso_file_B)
        common_prefix (str): L'ID comune dell'osservazione (es. '20241024-150917-S0000-W3OH_001_005')
        feed_A_id (int): L'ID numerico del Feed A (es. 0)
        feed_B_id (int): L'ID numerico del Feed B (es. 1)
        spectrum_type (str): Il tipo di spettro ('spectra', 'stokes', 'simple')
    """
    file_A_path, file_B_path = filepaths_tuple
    start_time_total = time.time() 
    BACKEND = 'SKARAB'
    
    print(f"\n--- PROFILING INIZIATO: Nodding Pair {common_prefix} ---")

    # ----------------------------------------------------------------------
    # TIMER 1: I/O Disco e Calcolo Media per entrambi i file A e B
    start_time_io_calc = time.time()
    
    # 1. ESTRAZIONE DATI FILE A
    # _extract_skarab_nodding_data esegue I/O e calcola np.nanmean
    result_A = _extract_skarab_nodding_data(file_A_path, spectrum_type, start_time_total)
    if result_A is None: 
        print(f"Errore estrazione dati A per {common_prefix}")
        return

    # 2. ESTRAZIONE DATI FILE B
    result_B = _extract_skarab_nodding_data(file_B_path, spectrum_type, start_time_total)
    if result_B is None: 
        print(f"Errore estrazione dati B per {common_prefix}")
        return
    
    end_time_io_calc = time.time()
    print(f"PROFILING: [Timer 1 NODDING] I/O Disco + Calcolo Media completato in {end_time_io_calc - start_time_io_calc:.4f} secondi.")
    # ----------------------------------------------------------------------
    

    # 3. UNIFICAZIONE DEI DATI
    # averages_A = [A_Ch0, A_Ch1] o [A_Ch0]. averages_B = [B_Ch0, B_Ch1] o [B_Ch0]
    final_averages = result_A['averages'] + result_B['averages']
    
    # 4. Preparazione della Legenda (per il plotter)
    if spectrum_type in ['spectra', 'simple']:
        # 4 linee totali: [A_Ch0, A_Ch1, B_Ch0, B_Ch1] -> 4 label
        feeds_for_legend = [feed_A_id, feed_A_id, feed_B_id, feed_B_id]
        expected_lines = 4
    elif spectrum_type == 'stokes':
        # 2 linee totali: [A_Ch0, B_Ch0] -> 2 label
        feeds_for_legend = [feed_A_id, feed_B_id]
        expected_lines = 2
    else:
        print(f"Tipo di spettro non riconosciuto per Nodding: {spectrum_type}")
        return

    if len(final_averages) != expected_lines:
         print(f"Errore di unificazione Nodding: attese {expected_lines} linee, trovate {len(final_averages)}.")
         return

    # Extract data from primary header for upper x-axis
    freq = primary_header_data["frequency"]
    lo =  primary_header_data["lo"] 
    bw = primary_header_data["bandwidth"]

    feeds = [feed_A_id, feed_B_id]

    # Calcolo frequenze per l'asse superiore
    f_min_val = float(freq)
    f_max_val = f_min_val + float(bw)

    x = np.linspace(0, len(final_averages[0]), len(final_averages[0]))

    # Caricamento nel dizionario condiviso
    state.CURRENT_SPEC.update({
        'x': x,               # Canali (0..65535)
        'averages': final_averages, # Lista di array delle polarizzazioni
        'f_min': f_min_val,   # Inizio banda MHz
        'f_max': f_max_val,   # Fine banda MHz
        'filename': common_prefix,
        'legend_labels': [f"Feed {f}" for f in feeds],
        'spectrum_type': spectrum_type,
        'updated': True       # Notifica il server
    })

    set_tab_labels(spectrum_type)

   

    #state.CURRENT_SPEC['updated'] = True
         

    '''
    # 5. GENERAZIONE PLOT (Contiene i Timer 2 e 3)
    # L'argomento start_time_total viene usato qui per calcolare il tempo totale finale
    plot_url = _plot_and_save_skarab_nodding_html(
        PLOT_SAVE_DIR,
        common_prefix, 
        final_averages, 
        result_A['x'], 
        feeds_for_legend, 
        spectrum_type,
        result_A['x_axis_label_val'],
        start_time_total,
        freq,
        lo,
        bw
    )
    '''
    


    
    # 6. Emissione SocketIO
    # if plot_url and _socketio_instance:
    if _socketio_instance:
         
        # --- UTILIZZO DEI DATI PASSATI ---
        # Usiamo il dizionario header_data gi� passato.
        # Aggiungiamo o modifichiamo i campi per riflettere lo stato di "Nodding Pair".
        
        # L'header reale � gi� contenuto in primary_header_data['header']
        final_data_to_emit = primary_header_data.copy()
        final_data_to_emit['filename'] = f"Nodding Pair: {common_prefix} (Feeds {feed_A_id}, {feed_B_id})"
        # final_data_to_emit['plot_url'] = plot_url
        final_data_to_emit['feeds'] = f"[{feed_A_id}, {feed_B_id}]"
        final_data_to_emit['backend'] = BACKEND
        final_data_to_emit['spectrum'] = spectrum_type
        
        # Modifica l'header stesso per aggiungere un commento sul Nodding
        if 'header' in final_data_to_emit:
            # Sovrascrive/Aggiunge il commento per chiarire
            final_data_to_emit['header']['COMMENT'] = "Dati Nodding Pair (Unificazione Feeds A+B)"
            
            
            _socketio_instance.start_background_task(
                _socketio_instance.emit, 'fits_header_update', final_data_to_emit
            )
            
            print(f"NODDING: Emesso header e plot URL per la coppia {common_prefix}.")
    
    
    """
    # 6. Emissione SocketIO
    if plot_url and _socketio_instance:
         # Assumendo che tu abbia un modo per recuperare l'header (es. dal file A)
         nodding_data = {
             "filename": f"Nodding Pair: {common_prefix} (Feeds {feed_A_id}, {feed_B_id})",
             "plot_url": plot_url,
             "feeds": f"[{feed_A_id}, {feed_B_id}]",
             "backend": BACKEND,
             "spectrum_type": spectrum_type,
             "header": {"COMMENT": "Dati generati dal Nodding Pair Manager"}
         }
         # Assumiamo _socketio_instance.start_background_task sia il metodo corretto
         _socketio_instance.start_background_task(
             _socketio_instance.emit, 'fits_header_update', nodding_data
         )
    
    # Non � necessario un return esplicito per il thread, la funzione termina qui. """




def _get_skarab_feed_id_from_path(filepath):
    """
    Estrae l'ID numerico del Feed da un percorso file SKARAB Nodding.
    Es: path/a/20241024-150917-S0000-W3OH_001_005_FEED_0.fits -> 0
    """
    filename = os.path.basename(filepath)
    match = re.search(r"FEED_(\d+)\.fits$", filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    raise ValueError(f"SKARAB NODDING: ID Feed non trovato nel nome file: {filename}")



def calculate_hpbw(frequency_mhz, antenna_diameter_m, k_factor=1.22):
    # Costanti
    c = 3.0e8  # Velocit� della luce in m/s
    
    # 1. Conversione Frequenza
    frequency_hz = frequency_mhz * 1e6
    
    # 2. Calcolo Lunghezza d'onda (lambda)
    lambda_m = c / frequency_hz
    
    # 3. Calcolo HPBW in radianti
    hpbw_rad = k_factor * (lambda_m / antenna_diameter_m)
    
    # 4. Conversione in secondi d'arco (arcsec)
    hpbw_arcsec = hpbw_rad * (180 / pi) * 3600
    
    return hpbw_arcsec



def is_map_by_keyword(raw_keyword_value: str) -> bool:
    """
    Determina se il valore grezzo della keyword FITS indica una scansione di mappa.
    
    Si assume che 'RA', 'DEC' 'AZ', 'EL' (dopo aver rimosso gli spazi) indichino una mappa.
    """
    
    # 1. Pulizia e normalizzazione del valore della keyword
    cleaned_value = raw_keyword_value.strip()

    print(f"SubScanType: {cleaned_value}")
    
    # 2. Regola di Decisione
    # Se la keyword pulita corrisponde a uno degli assi di scansione, � una Mappa.
    if cleaned_value in ['RA', 'DEC', 'EL', 'AZ']:
        return True
    else:
        # Assumiamo che qualsiasi altro valore (es. 'TRACKING', '', 'None') sia Spettro.
        return False



def update_global_point_cloud_dual_pol(
    x_data_new: np.ndarray, 
    y_data_new: np.ndarray, 
    all_pi_data_new: List[np.ndarray]
) -> None:

    if(state.USE_SCATTER_MODE != True):


        """
        Aggiorna due Nuvole di Punti (Pol0 e Pol1) all'interno dello stato globale (state.py) 
        con i nuovi dati P_i e aggiorna i rispettivi limiti globali.
        
        Non richiede pi� global_map_cache come parametro, accede direttamente a state.GLOBAL_MAP_CACHE.

        Parametri:
        - ra_data_new: Array NumPy delle coordinate RA della nuova strisciata (in gradi).
        - dec_data_new: Array NumPy delle coordinate DEC della nuova strisciata (in gradi).
        - all_pi_data_new: Lista NumPy 1D di Potenze P_i (index 0 = Pol0, index 1 = Pol1).
        """
        
        # Chiavi di polarizzazione e limite massimo di polarizzazioni da gestire
        polarization_keys = ['Pol0', 'Pol1'] 
        num_pols = min(len(all_pi_data_new), 2)
        
        # 1. Calcola i limiti RA/DEC della nuova strisciata (sono uguali per entrambe le pol.)
        x_min_new = x_data_new.min()
        x_max_new = x_data_new.max()
        y_min_new = y_data_new.min()
        y_max_new = y_data_new.max()

        # 2. Cicla sulle polarizzazioni disponibili e aggiorna la cache
        for i in range(num_pols):
            pol_key = polarization_keys[i]
            pi_data_current = all_pi_data_new[i]
            
            # Accede direttamente allo stato globale importato
            cache = state.GLOBAL_MAP_CACHE[pol_key] 
            
            # CONTROLLO DI CONSISTENZA:
            if len(x_data_new) != len(pi_data_current):
                print(f"ERRORE: Dati RA/DEC ({len(x_data_new)}) e P_i ({len(pi_data_current)}) per {pol_key} non corrispondono. Skippo.")
                continue

            # UPDATE GLOBAL LIMITS
            cache['X_min'] = min(cache['X_min'], x_min_new) # Usare X_min
            cache['X_max'] = max(cache['X_max'], x_max_new) # Usare X_max
            cache['Y_min'] = min(cache['Y_min'], y_min_new) # Usare Y_min
            cache['Y_max'] = max(cache['Y_max'], y_max_new) # Usare Y_max

            # APPEND DATA
            # Le coordinate X e Y sono accoppiate con P
            cache['X'] = np.concatenate([cache['X'], x_data_new])
            cache['Y'] = np.concatenate([cache['Y'], y_data_new]) 
            cache['P'] = np.concatenate([cache['P'], pi_data_current])

            print(f"? Aggiornata Nuvola {pol_key}. Totale Punti: {len(cache['X'])}. X Range: {cache['X_min']:.4f}/{cache['X_max']:.4f}")
            print(f"? Aggiornata Nuvola {pol_key}. Totale Punti: {len(cache['Y'])}. Y Range: {cache['Y_min']:.4f}/{cache['Y_max']:.4f}")
            
    else:

        x_deg = x_data_new * (180.0 / np.pi)
        y_deg = y_data_new * (180.0 / np.pi)

        try:
            # Prepariamo il pacchetto dati per Bokeh
            # Usiamo i dati "freschi" appena estratti dal file FITS corrente
            scatter_payload = {
                'Pol0': {
                    'x': x_deg.tolist(), 
                    'y': y_deg.tolist(), 
                    'z': all_pi_data_new[0].tolist()
                },
                'Pol1': {
                    'x': x_deg.tolist(), 
                    'y': y_deg.tolist(), 
                    'z': all_pi_data_new[1].tolist()
                }
            }


            # Invio asincrono a Bokeh
            update_scatter_plot(scatter_payload)
        except Exception as e:
            print(f"Errore durante lo streaming scatter: {e}")


# FITS_processor.py

# ... (altre importazioni)
import map_gridding
import state
import bokeh_server
# ...

def run_gridding_task():
    """
    Worker B: Esegue la grigliatura e aggiorna l'interfaccia Bokeh.
    Chiamata in un thread separato.
    """
    
    # 1. Chiama la funzione di grigliatura (Worker B)
    map_data = map_gridding.perform_gridding()

    if map_data is None:
        return
        
    # --- DIAGNOSTICA IN CONSOLE (Punto di interesse) ---
    print("\n----------------------------------------------------")
    print("DIAGNOSTICA MAPPA GRIGLIATA RICEVUTA:")
    
    for pol_key in ['Pol0', 'Pol1']:
        if pol_key in map_data:
            data = map_data[pol_key]
            
            # Verifichiamo che l'immagine sia un array NumPy e non vuota
            if isinstance(data['image'], np.ndarray) and data['image'].size > 0:
                print(f"- Mappa {pol_key} -")
                print(f"  Shape: {data['image'].shape}")
                print(f"  Range Potenza (Min/Max): {data['low_color']:.4f} / {data['high_color']:.4f}")
                print(f"  Dimensioni (X/Y): {data['dw']:.4f} x {data['dh']:.4f} gradi")
            else:
                print(f"- Mappa {pol_key}: Dati non validi o vuoti.")

    print("----------------------------------------------------")
    # --------------------------------------------------------

    # 2. Aggiorna il plot in Bokeh (Worker C)
    bokeh_server.update_bokeh_plot(map_data)



'''
def run_gridding_task():
    """
    Wrapper che esegue il compito di grigliatura (Worker B) e gestisce l'output.
    Viene eseguito nel thread separato avviato da trigger_gridding_process().
    """
    try:
        print("Worker B: Grigliatura in corso...")
        
        # Chiama la funzione principale del Worker B, che legge lo stato globale
        # e restituisce le mappe grigliate (es. {'Pol0': mappa_2D, 'Pol1': mappa_2D})
        result_maps = map_gridding.perform_gridding()
        
        if result_maps:
            print(f"Worker B: GRIGLIATURA COMPLETATA. Mappe pronte per la visualizzazione.")
            
            # CHIAMATA AL WORKER C (Bokeh Server)
            # Invia le mappe grigliate al server Bokeh per l'aggiornamento dinamico del browser
            update_bokeh_plot(result_maps)
            
    except Exception as e:
        print(f"Worker B: ERRORE grave durante il grigliamento: {e}")
'''




def trigger_gridding_process():
    
    global gridding_thread

    # --- NUOVO BYPASS ---
    if getattr(state, 'USE_SCATTER_MODE', True): # valore di default se 'USE_SCATTER_MODE' non è definito in state.py. Più robusto della semplice if
        # Se siamo in modalit� scatter, non vogliamo attivare il grigliatore.
        # Lo scatter plot viene gi� aggiornato direttamente nel Worker A.
        return

    """
    Avvia il grigliamento in un thread separato se non c'� gi� un processo attivo.
    """
    
    # Controlla se il thread precedente � terminato o non � mai partito
    if gridding_thread is None or not gridding_thread.is_alive():
        
        print(">>> Worker A: ATTIVAZIONE ASINCRONA DEL GRIGLIATORE...")
        
        # Crea e avvia il nuovo thread
        gridding_thread = threading.Thread(target=run_gridding_task)
        gridding_thread.start()
    else:
        # Se il grigliatore � ancora occupato a elaborare la strisciata precedente,
        # la richiesta viene ignorata (o potresti implementare una coda).
        print(">>> Worker A: Grigliatore gi� attivo. Richiesta di grigliatura ignorata.")




def extract_metadata_and_filter(filepath: str, hdul: fits.HDUList) -> tuple[Dict[str, Any] | None, bool]:
    """
    Extracts all FITS metadata, determines the acquisition, and filters
    out files that do not contain data for the feed selected by the user.

    Returns:
    - (header_data, should_process): A dictionary with the metadata OR None, and a flag
                                     indicating whether processing should continue.
    """
    
    header = hdul[0].header
    filename = os.path.basename(filepath)
    filename_extension = os.path.splitext(filename)[1]

    # Retrieve the raw value and convert it to uppercase for comparison
    raw_spectrum = str(hdul["SECTION TABLE"].data["type"][0]).upper()

    # Apply the logic: FULL if STOKES, otherwise DUAL
    polarization_value = "FULL" if raw_spectrum == "STOKES" else "DUAL"

    header_data = {
        "filename": filename,
        "filename_extension": filename_extension,
        "header": {}, 
        "feeds": "[]", 
        "acq_type": "UNKNOWN", 
        "backend": "UNKNOWN", 
        "feeds_relative_to_file": [],
        "mode": polarization_value, # conterrà FULL o DUAL 
        "spectrum": str(hdul["SECTION TABLE"].data["type"][0]) # conterrà 'simple', 'spectra', 'stokes'
    }
         
    # Get the number of feeds used during the acquisition. This allows to check the type of acquisition:
    #   1 feed  - mono feed (as in 'position switching')
    #   2 feeds - dual feed (as in 'nodding mode')
    # > 2 feeds - multi feed

    # Extract the feed number
    acq_feeds = []
    acq_type = ""

    # All feeds relative to the receiver used can be read out from:
    # feeds = hdul["FEED TABLE"].data["id"]

    # However, the only feeds used to acquire the data are indeicated in 'hdul["RF INPUTS"].data["feed"]'
    # For 'simple' and 'spectra' spectrum type we get two rows per feed for pol LL and RR -> i.ei feed number duplicated
    acq_feeds = hdul["RF INPUTS"].data["feed"] 
    # Get unique feed numbers
    acq_feeds_unique_values = sorted(set(acq_feeds))
    # Construct a string containing the feeds used during the acquisition abd update the header dictionary
    acq_feeds_str = "[" + ",".join(str(x) for x in acq_feeds_unique_values) + "]"
    header_data["feeds"] = str(acq_feeds_str)
    
    # Get the number of feeds used, deduce the type of acquisition and update the header 
    num_unique_feeds = len(acq_feeds_unique_values)
    if num_unique_feeds == 1: header_data["acq_type"] = "MONO"
    elif num_unique_feeds == 2: header_data["acq_type"] = "DUAL"
    elif num_unique_feeds > 2: header_data["acq_type"] = "MULTI"

    acq_type = header_data["acq_type"]

    # Get the backend type (i.e. TotalPower, SARDARA, SKARAB)
    # Get the feed number relative to file and according to the backend type
    # .fits0 .i.e. multi-feed we extract the feed number from the file extension
    # .fits 
    # - if the backend is SARDARA or TOTAL POWER, we extract the feed from the RF INPUTS table
    # - if the backend is SKARAB, we extract the feed number from the file name
    # Once the feed value is extrated, allow the process only for the feed selected by the user on the front-end
    # This approach avoids to pre-process data relative to feeds not selected by the user   
   
    feeds_relative_to_file = [] # it contains the feeds whose data are included in the fits file 

    # To recognize the TotalPower backend it is enough to check, within the SECTION TABLE, that 
    # the number of 'bins' is equal to 1 or the 'type' is 'simple')
    chs = hdul["SECTION TABLE"].data["bins"][0]
    header_data["bins"] = chs

    # case: TotalPower
    if(chs == 1):

        header_data["backend"] = "TotalPower"
        # get the feed relative to the file  
        if(filename_extension == '.fits'):  # case MONO-feed or DUAL-feed
                
            feeds_relative_to_file = acq_feeds_unique_values
        
        else: # case multi-feed i.e. .fit0, .fits1 ...
            
            # Retrieve the feed number from the extension itself
            feeds_relative_to_file.append(filename_extension.removeprefix('.fits'))

    else:

        # case: SKARAB 
        # the filename produced by SKARAB contains 'FEED_'
        if("FEED_" in str(filepath)): 
            
            header_data["backend"] = "SKARAB"
            # Extract the feed number relative to the file (ex: 20241024-150917-S0000-W3OH_001_005_FEED_0.fits)
            match = re.search(r"FEED_(\d+)", filename)
            if match:
                feed_number = int(match.group(1))
                # print(feed_number) 
                feeds_relative_to_file.append(feed_number)       

        # case: SARDARA
        else: 
            
            header_data["backend"] = "SARDARA"
          
            if(filename_extension == '.fits'):  # case MONO-feed or DUAL-feed
                
                feeds_relative_to_file = acq_feeds_unique_values
        
            else: # case multi-feed i.e. .fit0, .fits1 ...
            
                # Retrieve the feed number from the extension itself
                feeds_relative_to_file.append(filename_extension.removeprefix('.fits'))
                        
    print('*** List of feeds used for acquisition and listed in the RF INPUTS table:',  acq_feeds_unique_values)
    print('*** List of feeds used for acquisition and extracted from filename:', feeds_relative_to_file) # case .fits# and SKARAB

    # Process data only for FITS file containing data relative to the feed selected by the user in the front-end
    # Get the feed selected by the user in the front-end
    selected_feed_str = str(state.CURRENT_SELECTED_FEED)
    # Convert unique_values in a string for omogeneous comparison
    if(acq_type == "DUAL" and header_data["backend"] == "SKARAB"):

        unique_values_str = [str(x) for x in acq_feeds_unique_values] 

    else: # According to the acq_type MONO or MULTI, feeds_relative_to_file is taken from acq_feeds_unique_values or from the file name

        unique_values_str = [str(x) for x in feeds_relative_to_file] 

    header_data["feeds_relative_to_file"] = unique_values_str

    # case: FITS file will not be processed
    if selected_feed_str not in unique_values_str: 
        
        print(f"PROCESSOR FILTER: File discarded: {filename}. Selected Feed ({selected_feed_str}) not found in those listed in the fits file ({acq_feeds_str}).")
        return None, False # FITS file will not be processed
    
    # Extract header data
    for keyword, value in header.items():
        if keyword not in ['COMMENT', 'HISTORY']:
            # 1. Preserve the original value for conversions
            processed_value = str(value)

            # 2. Intercept astronomical keywords
            if keyword == 'RightAscension':
                # Pass the float to the function and get the string in hms format
                processed_value = rad_to_hms_string(float(value))
            
            elif keyword == 'Declination':
                # Pass the float to the function and get the string in dms format
                processed_value = rad_to_dms_string(float(value))

        # 3. Save the value inside the dictionary
        header_data["header"][keyword] = processed_value
        # Print the value of the current keyword 
        # print(f"{keyword}: {processed_value}")

    # Read the schedule name from the FITS file
    schedule_name = header_data["header"]["ScheduleName"]

    # Update the flag if schedule name is different as compared to the saved one
    if  schedule_name != state.CURRENT_SCHEDULE:
        state.CURRENT_SCHEDULE = schedule_name  # Update the schedule name with the new one
        state.IS_NEW_DATASET = True             # Set the flag to True for Bokeh
        print(f"PROCESSOR: Cambio sorgente rilevato -> {schedule_name}")
    else:
        # Keep the flag to False is the current schedule name is equal to the stored one
        state.IS_NEW_DATASET = False

    # Additional keywords to be added from hdul
    try:
        sec = hdul["SECTION TABLE"].data[0] # get first raw of data from the SECTION TABLE
        header_data["bins"] = str(sec["bins"])
        header_data["bandwidth"] = str(sec["bandwidth"])
        
        rf = hdul["RF INPUTS"].data[0] # get first raw of data from RF INPUTS table
        header_data["frequency"] = str(rf["frequency"])
        header_data["lo"] = str(rf["localOscillator"])

        # get the subscan type. The value allows to discriminate between maps and simple spectra
        header_data["sub_scan_type"] = header_data["header"].get("SubScanType") # Gi?? pulito in step 3
    
    except Exception as e:
        
        print(f"Attention - error while extracting values from extension tables: {e}")
    
    return header_data, acq_feeds_unique_values,True # the flag True allows to process data and display the plot 



def _extract_coordinates_for_map(hdul, sub_scan_type) -> Tuple[np.ndarray, np.ndarray]:
    
    """Extract the X and Y coordinates (RA/DEC or AZ/EL) based on the scan type"""
    
    if sub_scan_type == 'RA' or sub_scan_type == 'DEC':
        # Assume RA/DEC as (X, Y)
        x_data = np.array(hdul["DATA TABLE"].data["raj2000"])
        y_data = np.array(hdul["DATA TABLE"].data["decj2000"])
        return x_data, y_data
        
    elif sub_scan_type == 'AZ' or sub_scan_type == 'EL':
        # Assume AZ/EL as (X, Y)
        x_data = np.array(hdul["DATA TABLE"].data["az"])
        y_data = np.array(hdul["DATA TABLE"].data["el"])
        return x_data, y_data

    else:
        # if 'is_map' is 'True' but the sub_scan_type is unexpected, 
        # return empty arrays to avoid gridding errors
        print(f"CRITICAL ERROR: SubScanType '{sub_scan_type}' not managed for maps.")
        return np.array([]), np.array([])



def rad_to_hms_string(rad):

    """Converts radians to a string DD° MM' SS" (for RA, AZ)"""
    
    if rad is None or np.isnan(rad): return "--"
    
    # Normalize between 0 and 2pi
    rad = rad % (2 * np.pi)
    # Convert in decimal hours (2pi rad = 24h)
    hours_dec = rad * (12.0 / np.pi)
    
    h = int(hours_dec)
    m = int((hours_dec - h) * 60)
    s = (hours_dec - h - m/60) * 3600
    
    return f"{h:02d}h {m:02d}m {s:05.2f}s"



def rad_to_dms_string(rad):
    
    """Converts radians to a string DD° MM' SS" (for DEC, EL)"""
    
    if rad is None or np.isnan(rad): return "--"
    
    # Convert to decimal degrees
    deg_dec = np.degrees(rad)
    
    sign = "+" if deg_dec >= 0 else "-"
    deg_dec = abs(deg_dec)
    
    d = int(deg_dec)
    m = int((deg_dec - d) * 60)
    s = (deg_dec - d - m/60) * 3600
    
    # Use \u00b0 for the degree symbol (encoding safety)
    return f"{sign}{d:02d}\u00b0 {m:02d}' {s:05.2f}\""
  


def reset_dashboard():
    
    # This method reset the dashboard which contain the map and the spectrum in time
    # ----------------------------------------------------
    # ?? This is the reset logic for the map
    # ----------------------------------------------------

    # We verify if Pol0 (or any other Pol) contains data
    if state.GLOBAL_MAP_CACHE['Pol0']['X'].size > 0:
        print(">>> Cahne of modality Dashboard/Single Spectrum detected. Reset Map CACHE.")
        # Call the reset function from the state.py module
        state.initialize_map_cache()

    # We add this important check for the scatter plot:
    if state.USE_SCATTER_MODE:
        reset_scatter_plot()
       
    # Reset of the X-axis values and data of the spectrum in time
    state.LAST_SPECTRUM_X = np.array([])
    state.LAST_SPECTRUM_POL0 = np.array([])
    state.LAST_SPECTRUM_POL1 = np.array([])



def set_tab_labels(spectrum_type):

    # This method set the correct description of each tab label in the spectrum according to the spectrum_type(simple, spectra and stokes)
    if spectrum_type == 'spectra' or 'simple':
        state.CURRENT_SPEC['tab_labels'] = ["LEFT (LCP)", "RIGHT (RCP)"]
    elif spectrum_type == 'stokes':
        state.CURRENT_SPEC['tab_labels'] = ["Stokes I", "Stokes Q", "Stokes U", "Stokes V"]