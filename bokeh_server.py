# bokeh_server.py

import threading
from bokeh.plotting import curdoc
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.server.server import Server
import numpy as np # Importa NumPy
from typing import Dict, Any, List, Optional
from threading import Thread

# Importa i tuoi moduli: stato globale, visualizzazioni e Worker B
import state
# Importa la funzione di creazione del plot iniziale (es. da bokeh_visuals.py)
from bokeh_visuals import create_map_layout 

# Variabili Globali per la Gestione del Server
server: Optional[Server] = None
server_thread: Optional[Thread] = None


# ----------------------------------------------------------------------
# 1. FUNZIONE PRINCIPALE DEL DOCUMENTO BOKEH (chiamata una volta all'avvio)
# ----------------------------------------------------------------------

def modify_doc(doc):
    """
    Funzione eseguita dal Server Bokeh per popolare il documento (curdoc()).
    Qui si crea la struttura iniziale (figure, source) e si salvano i riferimenti.
    """
    
    # 1. Creazione degli elementi Bokeh iniziali (figure, sources, color_mapper)
    layout_obj, doc_state = create_map_layout(doc)
    
    # 2. Salva gli oggetti Bokeh nello stato globale per l'aggiornamento
    # state.BOKEH_DOC_STATE viene popolato con {'doc': doc, 'source_pol0': ..., ...}
    state.BOKEH_DOC_STATE = doc_state
    
    # 3. Aggiunge il layout al documento
    doc.add_root(layout_obj)

# ----------------------------------------------------------------------
# 2. GESTIONE AGGIORNAMENTO (Chiamato dal Worker B)
# ----------------------------------------------------------------------

def update_bokeh_plot(result_maps: Dict[str, Dict[str, Any]]):
    """
    Aggiorna i ColumnDataSource del documento Bokeh con le nuove mappe grigliate.
    Questa funzione � CHIAMATA DA UN ALTRO THREAD (Worker B).

    Parametri:
    - result_maps: Dizionario contenente le mappe grigliate (es. {'Pol0': {...}, 'Pol1': {...}})
    """
    global server
    
    doc_state = state.BOKEH_DOC_STATE
    if doc_state is None or doc_state['doc'] is None:
        print("BOKEH: Stato del documento non inizializzato. Skippo aggiornamento.")
        return

    def safe_update():
        """
        Esegue l'aggiornamento dei ColumnDataSource del plot Bokeh in modo sicuro,
        essendo chiamata tramite doc.add_next_tick_callback.
        """
        
        # Recupero i riferimenti agli oggetti Bokeh dallo stato globale
        source_pol0 = doc_state['source_pol0']
        source_pol1 = doc_state['source_pol1']
        color_mapper = doc_state['color_mapper']
        
        print(f"BOKEH: Esecuzione aggiornamento sicuro (safe_update) per {len(result_maps)} mappe.")

        # --- Aggiornamento Pol0 ---
        if 'Pol0' in result_maps:
            grid_map = result_maps['Pol0']
            
            # Aggiornamento dei dati della mappa e delle dimensioni (ImageRenderer)
            source_pol0.data = {
                'image': [grid_map['image']], # La matrice 2D della mappa (ndarray)
                'x': [grid_map['x']],         # RA/X iniziale
                'y': [grid_map['y']],         # DEC/Y iniziale
                'dw': [grid_map['dw']],       # Larghezza mappa in RA
                'dh': [grid_map['dh']],       # Altezza mappa in DEC
            }
            
            # Aggiornamento del Range di Colore (CRUCIALE per la ColorBar)
            if 'low_color' in grid_map and 'high_color' in grid_map:
                 color_mapper.low = grid_map['low_color']
                 color_mapper.high = grid_map['high_color']

            print(f"BOKEH: Aggiornamento dati Pol0 completato. Range colore: [{color_mapper.low:.2f}, {color_mapper.high:.2f}]")

        # --- Aggiornamento Pol1 ---
        if 'Pol1' in result_maps:
            grid_map = result_maps['Pol1']
            
            # Aggiornamento dei dati della mappa e delle dimensioni
            source_pol1.data = {
                'image': [grid_map['image']], 
                'x': [grid_map['x']],         
                'y': [grid_map['y']],         
                'dw': [grid_map['dw']],       
                'dh': [grid_map['dh']],       
            }
            
            # Aggiornamento del Range di Colore
            if 'low_color' in grid_map and 'high_color' in grid_map:
                 color_mapper.low = grid_map['low_color']
                 color_mapper.high = grid_map['high_color']

            print(f"BOKEH: Aggiornamento dati Pol1 completato. Range colore: [{color_mapper.low:.2f}, {color_mapper.high:.2f}]")

        print("BOKEH: Trasmissione dati al frontend completata.")


    # Inietta la funzione di aggiornamento (safe_update) nella coda di esecuzione del server Bokeh
    # Questo garantisce che l'aggiornamento avvenga sul thread corretto di Bokeh.
    doc_state['doc'].add_next_tick_callback(safe_update)
    print("BOKEH: Richiesta di aggiornamento inviata al thread del server.")


# ----------------------------------------------------------------------
# 3. AVVIO DEL SERVER
# ----------------------------------------------------------------------

def start_bokeh_server(port: int = 5006, app_name: str = '/map_viewer'):
    """
    Avvia il server Bokeh in un thread separato.
    """
    global server, server_thread

    if server_thread and server_thread.is_alive():
        print("BOKEH: Server gi� attivo.")
        return

    print(f"BOKEH: Avvio Server su http://localhost:{port}{app_name}")
    
    # 1. Crea l'Applicazione Bokeh (usa la funzione modify_doc come handler)
    app = Application(FunctionHandler(modify_doc))

    # 2. Configura e avvia il Server
    server = Server({app_name: app}, port=port, allow_websocket_origin=[f"localhost:{port}"])

    def run_server():
        # Questo blocca finch� il server non viene spento
        server.run_until_shutdown()

    # 3. Avvia il thread del server
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("BOKEH: Server avviato in thread separato.")