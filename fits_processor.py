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
from bokeh_server import update_bokeh_plot
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


def _extract_data_and_perform_averages(filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, backend, freq, lo, bw, sub_scan_type):

     # ----------------------------------------------------------------------
    # START TIME: Inizio della funzione
    start_time_total = time.time()
    print(f"\n--- PROFILING INIZIATO: {filename_prefix} ---")

    data = [] 
    averages = []

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
            
            else: # case .fits# i.e. multi-feed (SARDARA only)
                
                # ... (Logica di estrazione SARDARA multi-feed .fits#) ...
                feed_number = filename_extension.removeprefix('.fits')
                if(spectrum_type == 'spectra'):
                    
                    index = int(feed_number)*2
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                    index = (int(feed_number)*2)+1
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                
                else:
                    
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"]))

            
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

        if data:
            if(type(data[0][0]) == np.ndarray):
                # Caso SPETTRO [righe x canali] o MAPPA [righe x canali]
                
                # *** QUI INSERIAMO LA LOGICA DI BIFORCAZIONE ***
                
                if not is_map:

                    # ----------------------------------------------------
                    # ?? QUI INSERIAMO LA LOGICA DI RESET ??
                    # ----------------------------------------------------
                    
                    # Verifichiamo se Pol0 (o qualsiasi altra Pol) contiene dati.
                    if state.GLOBAL_MAP_CACHE['Pol0']['RA'].size > 0:
                        print(">>> Rilevato cambio di modalit� a Spettro. Reset CACHE MAPPA.")
                        # Chiama la funzione di reset dal modulo state.py
                        state.initialize_map_cache()


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

                    if(sub_scan_type == 'RA' or sub_scan_type == 'DEC'):
                        # Get RA and DEC data
                        x_data = np.array(hdul["DATA TABLE"].data["raj2000"])
                        y_data = np.array(hdul["DATA TABLE"].data["decj2000"])

                    if(sub_scan_type == 'AZ' or sub_scan_type == 'EL'):
                        # Get RA and DEC data
                        x_data = np.array(hdul["DATA TABLE"].data["az"])
                        y_data = np.array(hdul["DATA TABLE"].data["el"])
                      
                    
                    all_pi_data = []
                    for i in range(len(data)):
                        # Esegui la media orizzontale (lungo i canali)
                        pi_data = np.nanmean(data[i], axis=1) # <--- MEDIA ORIZZONTALE (Potenza P_i)

                        print(pi_data)
                        
                        # In modalit� MAPPA, 'averages' conterr� le P_i di tutte le polarizzazioni/feeds
                        # di quel file, ma tipicamente per la mappa userai SOLO il primo set.
                        averages.append(pi_data) 
                        all_pi_data.append(pi_data) # Raccogli tutti i P_i per i metadata
                        
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
                
            else:
                # Caso TOTAL POWER (Singolo punto per riga)
                for i in range(len(data)):
                    # Qui data[i] � gi� un array di singoli punti (la serie temporale)
                    averages.append(data[i]) 
                
                # Creazione asse X (Punti Campione)
                x = np.linspace(0, len(averages[0]), len(averages[0]))
                x_axis_label_val = 'Sampling Point'
                
        else:
            raise Exception("Nessun dato estratto dal file FITS.")
        
       


        # ----------------------------------------------------------------------
        # TIMER 1: Tempo di I/O Disco (fits.open/hdul.data) e Calcolo Media (np.mean)
        end_time_io_calc = time.time()
        print(f"PROFILING: [Timer 1] I/O Disco + Calcolo Media completato in {end_time_io_calc - start_time_io_calc:.4f} secondi.")

        return _plot_and_save_html(PLOT_SAVE_DIR, filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, 
            backend, x_axis_label_val, x, averages, feed_number, start_time_total, freq, lo, bw)
    
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
    # from "load_subscans" first index is the item number in the list, second index the value [0]=file name, [1] signal flag, [2]=time
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
        plot_url = _extract_data_and_perform_averages(filepath, filename_base, filename_extension, 
            acq_feeds_unique_values, int(header_data.get("bins")), header_data.get("spectrum"), backend, freq, lo, bw, header_data.get("sub_scan_type"))

            
        if plot_url:
            header_data["plot_url"] = plot_url
            print(f"Plot URL added to data: {plot_url}")
        else:
            print("No plot URL generated for this FITS file.")


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
        start_time_total 
    )


    # 6. Emissione SocketIO
    if plot_url and _socketio_instance:
         
         # --- UTILIZZO DEI DATI PASSATI ---
         # Usiamo il dizionario header_data gi� passato.
         # Aggiungiamo o modifichiamo i campi per riflettere lo stato di "Nodding Pair".
         
         # L'header reale � gi� contenuto in primary_header_data['header']
         final_data_to_emit = primary_header_data.copy()
         final_data_to_emit['filename'] = f"Nodding Pair: {common_prefix} (Feeds {feed_A_id}, {feed_B_id})"
         final_data_to_emit['plot_url'] = plot_url
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
            
        # APPEND DATA
        cache['RA'] = np.concatenate([cache['RA'], x_data_new])
        cache['DEC'] = np.concatenate([cache['DEC'], x_data_new])
        cache['P'] = np.concatenate([cache['P'], pi_data_current])
        
        # UPDATE GLOBAL LIMITS
        cache['RA_min'] = min(cache['RA_min'], x_min_new)
        cache['RA_max'] = max(cache['RA_max'], x_max_new)
        cache['DEC_min'] = min(cache['DEC_min'], y_min_new)
        cache['DEC_max'] = max(cache['DEC_max'], y_max_new)
        
        print(f"? Aggiornata Nuvola {pol_key}. Totale Punti: {len(cache['RA'])}")



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





def trigger_gridding_process():
    """
    Avvia il grigliamento in un thread separato se non c'� gi� un processo attivo.
    """
    global gridding_thread
    
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
    Estrae tutti i metadati FITS, determina l'acquisizione, e filtra
    se il file non contiene dati per il feed selezionato dall'utente.

    Ritorna: 
    - (header_data, should_process): Dizionario con i metadati OPPURE None, e un flag
                                     che indica se l'elaborazione deve continuare.
    """
    
    header = hdul[0].header
    filename = os.path.basename(filepath)
    filename_extension = os.path.splitext(filename)[1]
    
    header_data = {
        "filename": filename,
        "filename_extension": filename_extension,
        "header": {}, # Per keyword generiche
        "feeds": "[]", # Stringa di tutti i feed (es. "[0,1,2]")
        "acq_type": "UNKNOWN", # MONO, DUAL, MULTI
        "backend": "UNKNOWN", # TotalPower, SKARAB, SARDARA
        "feeds_relative_to_file": [], # I feed i cui dati sono effettivamente in questo file
        "spectrum": hdul["SECTION TABLE"].data["type"][0]
    }

     
    # STEP 0  - get the number of feeds used during the acquisition. This allows to check the type of acquisition:
    #   1 feed  - mono feed (as in the position switching)
    #   2 feeds - dual feed (as in the nodding mode)
    # > 2 feeds - multi feed

    # Extract the feed number
    acq_feeds = []
    acq_type = ""
    acq_feeds = hdul["RF INPUTS"].data["feed"] # In 'spectra' type we get the same feed value for LL and RR
    # Prepare the list of feeds with unique numbers
    acq_feeds_unique_values = sorted(set(acq_feeds))
    acq_feeds_str = "[" + ",".join(str(x) for x in acq_feeds_unique_values) + "]"
    header_data["feeds"] = str(acq_feeds_str)
    
    # store the acq_type
    num_unique_feeds = len(acq_feeds_unique_values)
    if num_unique_feeds == 1: header_data["acq_type"] = "MONO"
    elif num_unique_feeds == 2: header_data["acq_type"] = "DUAL"
    elif num_unique_feeds > 2: header_data["acq_type"] = "MULTI"

    acq_type = header_data["acq_type"]

    # Get the backend type
    # Get the feed number relative to file and according to the backend type
    # .fits0 .i.e. multi-feed we extract the feed number from the file extension
    # .fits 
    # - if the backend is SARDARA or TOTAL POWER, we extract the feed from the RF INPUTS table
    # - if the backend is SKARAB, we extract the feed number from the file name
    # Once the feed value is extrated, allow the process only for the feed selected by the user on the front-end
    # This approach avoids to pre-process data relative to feeds not selected by the user
    chs = hdul["SECTION TABLE"].data["bins"][0]
    header_data["bins"] = chs
    # Get the backend type (i.e. TotalPower, SARDARA, SKARAB)
    # To recognize the TotalPower backend it is enough to check that the number of bins (i.e. chs) is equal to 1 (or spectra type 'SIMPLE')

    feeds_relative_to_file = [] # these are the feeds whose data are included in the fits file 

    if(chs == 1):

        header_data["backend"] = "TotalPower"
        # get the feed relative to the file  
        if(filename_extension == '.fits'):  # case MONO-feed or DUAL-feed
                
            feeds_relative_to_file = acq_feeds_unique_values
        
        else: # case multi-feed i.e. .fit0, .fits1 ...
            
            # Retrieve the feed number from the extension itself
            feeds_relative_to_file.append(filename_extension.removeprefix('.fits'))

    else:

        if("FEED_" in str(filepath)): # case SKARAB backend
            
            header_data["backend"] = "SKARAB"
            # Extract the feed number relative to the file (20241024-150917-S0000-W3OH_001_005_FEED_0.fits)
            match = re.search(r"FEED_(\d+)", filename)
            if match:
                feed_number = int(match.group(1))
                # print(feed_number) 
                feeds_relative_to_file.append(feed_number)       

        else: # case SARDARA backend
            
            header_data["backend"] = "SARDARA"
            # case .fits file i.e. case mono-feed or dual-feed (nodding)
            # case .fits are TotalPower, SARDARA (excluding multi-feed) and SKARAB
            # get the feed relative to the file  
            if(filename_extension == '.fits'):  # case MONO-feed or DUAL-feed
                
                feeds_relative_to_file = acq_feeds_unique_values
        
            else: # case multi-feed i.e. .fit0, .fits1 ...
            
                # Retrieve the feed number from the extension itself
                feeds_relative_to_file.append(filename_extension.removeprefix('.fits'))
                        

    print('*** List of feeds relative to acquisition:',  acq_feeds_unique_values)
    print('*** List of feeds relative to file:', feeds_relative_to_file)

    # We process data only if the fits file has data related to the feed selected by the user in the front-end
    # Get the feed selected by the user
    selected_feed_str = str(state.CURRENT_SELECTED_FEED)
    # Convert unique_values in a string for omogeneous comparison
    if(acq_type == "DUAL" and header_data["backend"] == "SKARAB"):

        unique_values_str = [str(x) for x in acq_feeds_unique_values] 

    else:

        unique_values_str = [str(x) for x in feeds_relative_to_file] 
            
    # Process data only if feed contained in the fits file coincide with that selected one by he user

    header_data["feeds_relative_to_file"] = unique_values_str


    if selected_feed_str not in unique_values_str: 
        
        print(f"PROCESSOR FILTER: File discarded: {filename}. Selected Feed ({selected_feed_str}) not found in those listed in the fits file ({acq_feeds_str}).")
        return None, False # File will not be processed
        
      
    for keyword, value in header.items():
        if keyword not in ['COMMENT', 'HISTORY']:
            print(f"{keyword}: {value}")
            header_data["header"][keyword] = str(value)

    print("--------------------------------------------------\n")

    # Keyword aggiuntive da HduTables
    try:
        sec = hdul["SECTION TABLE"].data[0]
        header_data["bins"] = str(sec["bins"])
        header_data["bandwidth"] = str(sec["bandwidth"])
        
        rf = hdul["RF INPUTS"].data[0] # Assumiamo la prima riga ?? sufficiente per questi valori
        header_data["frequency"] = str(rf["frequency"])
        header_data["lo"] = str(rf["localOscillator"])
        header_data["sub_scan_type"] = header_data["header"].get("SubScanType") # Gi?? pulito in step 3
    
    except Exception as e:
        
        print(f"Attention - error while extracting values from extension tables: {e}")
    
    return header_data, acq_feeds_unique_values,True # Tutto ?? OK, processa 



def determine_map_coordinates(header_data: Dict[str, Any]) -> str:
    """
    Determina il tipo di operazione (Mappa o Non-Mappa) e, in caso di Mappa, 
    il sistema di coordinate da estrarre, basandosi sulla chiave 'SubScanType'.

    Ritorna:
    - 'RA_DEC': Mappa in coordinate Celesti (usa le colonne 'ra'/'dec').
    - 'EL_AZ': Mappa in coordinate Orizzontali (usa le colonne 'el'/'az').
    - 'OTHER': Scansione NON-MAPPA (es. 'TRACKING', 'SPECTRUM').
    """
    
    # ?? Usa la chiave specifica fornita: "SubScanType" ??
    subscan_type = header_data.get("SubScanType")

    if subscan_type is None:
        print("WARNING: Keyword 'SubScanType' mancante nell'header.")
        return "OTHER"
        
    # Standardizza il valore per la comparazione (opzionale, ma sicuro)
    subscan_type = subscan_type.upper().strip()

    # --- 1. CASI NON-MAPPA ---
    if subscan_type == "TRACKING" or subscan_type == "SPECTRUM":
        return "OTHER" 

    # --- 2. CASI MAPPA (Coordinate Celesti) ---
    elif subscan_type in ["RA", "DEC"]:
        # Se la scansione avviene in RA o DEC, usiamo le coordinate celesti.
        print(f"DEBUG: SubScanType '{subscan_type}'. Scelgo RA/DEC.")
        return "RA_DEC"
        
    # --- 3. CASI MAPPA (Coordinate Orizzontali) ---
    elif subscan_type in ["AZ", "EL"]:
        # Se la scansione avviene in AZ o EL, usiamo le coordinate orizzontali.
        print(f"DEBUG: SubScanType '{subscan_type}'. Scelgo EL/AZ.")
        return "EL_AZ"
        
    # --- 4. FALLBACK ---
    else:
        print(f"PROCESSOR: Tipo di scansione '{subscan_type}' non riconosciuto per la mappatura. Skippo.")
        return "OTHER"


def _get_map_coordinates(header_data: Dict[str, Any]) -> str:
    """
    Determina il tipo di operazione e il sistema di coordinate da estrarre
    basandosi sul valore di SUBSCAN (o una keyword simile).

    Ritorna:
    - 'RA_DEC': Mappa in coordinate Celesti.
    - 'EL_AZ': Mappa in coordinate Orizzontali.
    - 'OTHER': Scansione NON-MAPPA (es. Tracking, Spettro, ecc.).
    """
    
    subscan_type = header_data.get("SUBSCAN") # Assumiamo che "SUBSCAN" sia la chiave corretta

    if subscan_type is None:
        print("WARNING: Keyword 'SUBSCAN' mancante nell'header. Skippo l'elaborazione.")
        return "OTHER"
        
    # --- 1. CASI NON-MAPPA ---
    if subscan_type == "TRACKING":
        # Se � tracking, � un'acquisizione di spettro/pointing, non una mappa
        return "OTHER" 

    # --- 2. CASI MAPPA (Coordinate Celesti) ---
    elif subscan_type in ["RA", "DEC"]:
        # Se la scansione avviene in RA o DEC, usiamo le coordinate celesti.
        print(f"DEBUG: SUBSCAN � '{subscan_type}'. Scelgo RA/DEC.")
        return "RA_DEC"
        
    # --- 3. CASI MAPPA (Coordinate Orizzontali) ---
    elif subscan_type in ["AZ", "EL"]:
        # Se la scansione avviene in AZ o EL, usiamo le coordinate orizzontali.
        print(f"DEBUG: SUBSCAN � '{subscan_type}'. Scelgo EL/AZ.")
        return "EL_AZ"
        
    # --- 4. FALLBACK ---
    else:
        # Qualsiasi altro valore che non � esplicitamente gestito
        print(f"PROCESSOR: Tipo di scansione '{subscan_type}' non riconosciuto per la mappatura. Skippo.")
        return "OTHER"