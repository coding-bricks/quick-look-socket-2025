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
from bokeh_visuals import create_map_layout, create_scatter_layout

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
    if state.USE_SCATTER_MODE:
        layout_obj, doc_state = create_scatter_layout(doc)
    else:
        layout_obj, doc_state = create_map_layout(doc)



    #layout_obj, doc_state = create_map_layout(doc)
    
    # 2. Salva gli oggetti Bokeh nello stato globale per l'aggiornamento
    # state.BOKEH_DOC_STATE viene popolato con {'doc': doc, 'source_pol0': ..., ...}
    state.BOKEH_DOC_STATE = doc_state
    
    # 3. Aggiunge il layout al documento
    doc.add_root(layout_obj)

   
  

# ----------------------------------------------------------------------
# 2. GESTIONE AGGIORNAMENTO (Chiamato dal Worker B)
# ----------------------------------------------------------------------

# bokeh_server.py (Sezione 2. GESTIONE AGGIORNAMENTO)

def update_bokeh_plot(result_maps: Dict[str, Dict[str, Any]]):
    """
    Aggiorna i ColumnDataSource del documento Bokeh con le nuove mappe grigliate.
    Questa funzione � CHIAMATA DA UN ALTRO THREAD (Worker B).

    Parametri:
    - result_maps: Dizionario contenente le mappe grigliate (es. {'Pol0': {...}, 'Pol1': {...}})
    """
    
    doc_state = state.BOKEH_DOC_STATE
    if doc_state is None or doc_state['doc'] is None:
        print("BOKEH: Stato del documento non inizializzato. Skippo aggiornamento.")
        return

    # ----------------------------------------------------------------------
    # DEFINIZIONE DEL CALLBACK DI AGGIORNAMENTO SICURO
    # ----------------------------------------------------------------------
    def safe_update():
        """
        Esegue l'aggiornamento dei ColumnDataSource del plot Bokeh in modo sicuro.
        """
        
        # Recupero i riferimenti agli oggetti Bokeh dallo stato globale
        source_pol0 = doc_state['source_pol0']
        source_pol1 = doc_state['source_pol1']
        # Assumiamo che ci sia un solo color_mapper per entrambi i plot (mappa unificata)
        color_mapper = doc_state['color_mapper']
        
        # --- 1. CALCOLA IL RANGE DI COLORE GLOBALE (Pol0 + Pol1) ---
        global_low_color = float('inf')
        global_high_color = float('-inf')

        # Aggregazione dei limiti di colore tra tutte le polarizzazioni disponibili
        for pol_key in ['Pol0', 'Pol1']:
            if pol_key in result_maps:
                grid_map = result_maps[pol_key]
                
                if 'low_color' in grid_map and 'high_color' in grid_map:
                    # Confronta e aggiorna il minimo e massimo globale
                    global_low_color = min(global_low_color, grid_map['low_color'])
                    global_high_color = max(global_high_color, grid_map['high_color'])

        # --- 2. AGGIORNA IL MAPPER UNA SOLA VOLTA ---
        if global_low_color < global_high_color:
            color_mapper.low = global_low_color
            color_mapper.high = global_high_color
            print(f"BOKEH: Range Colore UNIFICATO impostato su [{global_low_color:.2f}, {global_high_color:.2f}]")
        
        print(f"BOKEH: Esecuzione aggiornamento sicuro (safe_update) per {len(result_maps)} mappe.")

        # --- 3. Aggiornamento Pol0 (Aggiornamento Dati) ---
        if 'Pol0' in result_maps:
            grid_map = result_maps['Pol0']
            
            # Aggiornamento dei dati della mappa e delle dimensioni (ImageRenderer)
            source_pol0.data = {
                'image': [grid_map['image']], # La matrice 2D della mappa (ndarray)
                'x': [grid_map['x']],
                'y': [grid_map['y']],
                'dw': [grid_map['dw']],
                'dh': [grid_map['dh']],
            }
            
            print(f"BOKEH: Aggiornamento dati Pol0 completato. Shape: {grid_map['image'].shape}")

        # --- 4. Aggiornamento Pol1 (Aggiornamento Dati) ---
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
            
            print(f"BOKEH: Aggiornamento dati Pol1 completato. Shape: {grid_map['image'].shape}")

        print("BOKEH: Trasmissione dati al frontend completata.")

    # ----------------------------------------------------------------------
    # INIEZIONE DEL CALLBACK
    # ----------------------------------------------------------------------
    # Inietta la funzione di aggiornamento nella coda di esecuzione del server Bokeh
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

    # ?? NUOVE ORIGINI CONSENTITE ??
    # Aggiungi localhost:5000 e 127.0.0.1:5000 alla lista
    allowed_origins = [
        f"localhost:{port}", # L'origine di default di Bokeh stesso
        "localhost:5000",
        "127.0.0.1:5000"
    ]

    print(f"BOKEH: Avvio Server su http://localhost:{port}{app_name}")
    print(f"BOKEH: Origini WebSocket consentite: {allowed_origins}") # Aggiunto log per debug

    # 1. Crea l'Applicazione Bokeh
    app = Application(FunctionHandler(modify_doc))

    # 2. Configura e avvia il Server
    # Passa l'argomento 'allow_websocket_origin' con la lista estesa
    server = Server(
        {app_name: app}, 
        port=port, 
        allow_websocket_origin=allowed_origins # ?? MODIFICA CRUCIALE QUI ??
    )

    

    def run_server():
        # Questo blocca finch� il server non viene spento
        #server.run_until_shutdown()
        
        # Chiamiamo start() per preparare il server e poi eseguiamo il loop I/O
        # Questo evita che Bokeh chiami signal.signal() nel thread secondario.
        server.start()
        # Otteniamo il loop Tornado I/O di Bokeh e lo avviamo.
        server.io_loop.start() # Usa io_loop.start() invece di run_until_shutdown()

    # 3. Avvia il thread del server
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("BOKEH: Server avviato in thread separato.")

# ----------------------------------------------------------------------
# 4. NUOVA GESTIONE AGGIORNAMENTO SCATTER PLOT (Metodo Generico X, Y, Z)
# ----------------------------------------------------------------------

def update_scatter_plot(new_points: Dict[str, Dict[str, List[float]]]):
    """
    Esegue lo streaming dei nuovi punti (X, Y, Z) ai ColumnDataSource dello scatter.
    La struttura attesa per new_points �:
    {
        'Pol0': {'x': [...], 'y': [...], 'z': [...]},
        'Pol1': {'x': [...], 'y': [...], 'z': [...]}
    }
    """
    
    doc_state = state.BOKEH_DOC_STATE
    if doc_state is None or doc_state['doc'] is None:
        print("BOKEH: Stato per Scatter Plot non inizializzato.")
        return

    def safe_scatter_update():
        # Recupero sorgenti e mapper (verranno inizializzati in bokeh_visuals)
        source0 = doc_state.get('source_scatter_pol0')
        source1 = doc_state.get('source_scatter_pol1')
        color_mapper = doc_state.get('color_mapper_scatter')
        
        if source0 is None or source1 is None:
            # Se i sorgenti non esistono, significa che il layout scatter non � attivo
            return

        # --- 1. AGGIORNAMENTO DINAMICO RANGE COLORI ---
        # Unifichiamo i valori Z di entrambe le polarizzazioni per la scala colori
        all_z_values = []
        for pol in ['Pol0', 'Pol1']:
            if pol in new_points:
                all_z_values.extend(new_points[pol].get('z', []))
        
        if all_z_values and color_mapper:
            current_min, current_max = min(all_z_values), max(all_z_values)
            # Aggiornamento "espansivo": la scala si adatta al minimo e massimo assoluti visti finora
            color_mapper.low = min(color_mapper.low, current_min)
            color_mapper.high = max(color_mapper.high, current_max)

        # --- 2. STREAMING DEI DATI (APPEND) ---
        # Pol0: Aggiunge i nuovi punti senza cancellare i precedenti
        if 'Pol0' in new_points and len(new_points['Pol0']['x']) > 0:
            source0.stream({
                'x': new_points['Pol0']['x'],
                'y': new_points['Pol0']['y'],
                'z': new_points['Pol0']['z']
            })
            
        # Pol1: Aggiunge i nuovi punti senza cancellare i precedenti
        if 'Pol1' in new_points and len(new_points['Pol1']['x']) > 0:
            source1.stream({
                'x': new_points['Pol1']['x'],
                'y': new_points['Pol1']['y'],
                'z': new_points['Pol1']['z']
            })

        print(f"BOKEH: Scatter Update - Aggiunti {len(all_z_values)} punti totali.")

    # Iniezione sicura nel loop di Bokeh
    doc_state['doc'].add_next_tick_callback(safe_scatter_update)



def reset_scatter_plot():
    """Svuota completamente i punti dallo scatter plot."""
    doc_state = state.BOKEH_DOC_STATE
    if doc_state and 'source_scatter_pol0' in doc_state:
        def safe_reset():
            doc_state['source_scatter_pol0'].data = {'x': [], 'y': [], 'z': []}
            doc_state['source_scatter_pol1'].data = {'x': [], 'y': [], 'z': []}
            # Resetta anche i limiti della colormap se necessario
            doc_state['color_mapper_scatter'].low = 0
            doc_state['color_mapper_scatter'].high = 1
        
        doc_state['doc'].add_next_tick_callback(safe_reset)