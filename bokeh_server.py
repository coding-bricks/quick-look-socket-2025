# bokeh_server.py

import threading
from bokeh.plotting import curdoc
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.palettes import Category10
from bokeh.server.server import Server
import numpy as np # Importa NumPy
from typing import Dict, Any, List, Optional
from threading import Thread
from bokeh.models import Panel

# Importa i tuoi moduli: stato globale, visualizzazioni e Worker B
import state
# Importa la funzione di creazione del plot iniziale (es. da bokeh_visuals.py)
from bokeh_visuals import create_map_layout, create_scatter_layout, create_spectrum_layout

# Variabili Globali per la Gestione del Server
server: Optional[Server] = None
server_thread: Optional[Thread] = None


# ----------------------------------------------------------------------
# 1. FUNZIONE PRINCIPALE DEL DOCUMENTO BOKEH (chiamata una volta all'avvio)
# ----------------------------------------------------------------------

def map_app(doc):
    """Questa � l'applicazione per le mappe (quella che avevi in modify_doc)"""
    if state.USE_SCATTER_MODE:
        layout_obj, doc_state = create_scatter_layout(doc)
    else:
        layout_obj, doc_state = create_map_layout(doc)
    
    state.BOKEH_DOC_STATE = doc_state
    doc.add_root(layout_obj)



def spec_app(doc):
    """Applicazione dedicata al monitoraggio dello SPETTRO (Real-time)."""
    # 1. Inizializza il layout (Tabs, Figure, Sorgenti)
    layout, doc_state = create_spectrum_layout(doc)
    
    # 2. Salva i riferimenti nello stato specifico per lo spettro
    state.SPEC_DOC_STATE = doc_state 
    
    # 3. Aggiunge il layout al documento
    doc.add_root(layout)
    
    # 4. AVVIA IL MONITORAGGIO: controlla ogni 200ms se ci sono nuovi dati in state.py
    doc.add_periodic_callback(check_for_spec_updates, 200)


def check_for_spec_updates():
    """Funzione chiamata periodicamente da spec_app."""
    # Se il processor ha alzato il flag 'updated' nel dizionario CURRENT_SPEC
    if state.CURRENT_SPEC.get('updated'):
        update_spectrum_plot()



# ----------------------------------------------------------------------
# 2. LOGICA DI AGGIORNAMENTO SPETTRO (CHIAMATA DA PERIODIC CALLBACK)
# ----------------------------------------------------------------------
def update_spectrum_plot():
    doc_state = state.SPEC_DOC_STATE
    data = state.CURRENT_SPEC
    
    if not doc_state:
        return

    def safe_update():
        try:
            # --- 1. CONFIGURAZIONE E BOLEANI ---
            is_stokes = (data.get('spectrum_type') == 'stokes')
            is_simple = (data.get('spectrum_type') == 'simple')
            active_pols = ['I', 'Q', 'U', 'V'] if is_stokes else ['LL', 'RR']
            
            num_pols = len(active_pols)
            num_feeds = len(data['averages']) // num_pols if num_pols > 0 else 0
            file_title = data.get('filename', 'File Sconosciuto')
            labels = data.get('legend_labels', [])
            colors = Category10[10]
            
            new_tabs = []

            # --- 2. MEMORIA STATO VISIBILIT� LEGENDA ---
            # Serve per evitare che i feed "spenti" dall'utente si riaccendano al nuovo file
            hidden_labels = {p: set() for p in active_pols}
            for p in active_pols:
                if p in doc_state['figs']:
                    fig_old = doc_state['figs'][p]
                    if fig_old.legend:
                        for leg in fig_old.legend:
                            for leg_item in leg.items:
                                label = leg_item.label.get('value')
                                if any(not r.visible for r in leg_item.renderers):
                                    hidden_labels[p].add(label)

            # --- 3. CICLO DI AGGIORNAMENTO PER OGNI POLARIZZAZIONE ---
            for p in active_pols:
                if p not in doc_state['figs']:
                    continue
                    
                fig = doc_state['figs'][p]
                source = doc_state['sources'][p]
                
                # A. Gestione Assi (Inferiore e Superiore)
                fig.xaxis.axis_label = "Sampling Point" if is_simple else "Channel"
                
                f_min = data.get('f_min', 0.0)
                f_max = data.get('f_max', 1.0)
                
                # Cerchiamo l'asse superiore per aggiornare etichetta e visibilit�
                if 'freq_range' in fig.extra_x_ranges:
                    # Aggiorna i limiti numerici
                    fig.extra_x_ranges['freq_range'].start = f_min
                    fig.extra_x_ranges['freq_range'].end = f_max
                    
                    for axis in fig.above:
                        if hasattr(axis, 'x_range_name') and axis.x_range_name == "freq_range":
                            axis.visible = not is_simple
                            # FORZA l'etichetta corretta qui
                            axis.axis_label = "Frequency (MHz)" if not is_simple else ""

                # B. Titolo dinamico
                freq_info = f" | {f_min:.1f}-{f_max:.1f} MHz" if not is_simple else ""
                fig.title.text = f"FILE: {file_title} | Pol: {p}{freq_info} ({num_feeds} Feeds)"
                
                # C. Pulizia Renderer e Legenda
                fig.renderers = [r for r in fig.renderers if r.name != "data_line"]
                if fig.legend:
                    for leg in fig.legend:
                        leg.items = []
                
                # D. Creazione Nuove Linee (Feed)
                for i in range(num_feeds):
                    current_label = labels[i] if i < len(labels) else f"Feed {i}"
                    is_visible = current_label not in hidden_labels[p]

                    fig.line(
                        x='x', y=f'f{i}', source=source, 
                        color=colors[i % 10], 
                        legend_label=current_label,
                        line_width=2,
                        name="data_line",
                        visible=is_visible 
                    )

                # E. Update Dati (Mapping dei dati nelle colonne della sorgente)
                new_dict = {'x': data['x']}
                for i in range(num_feeds):
                    # Calcolo indice: alterna le pol per ogni feed (es: Feed0_L, Feed0_R, Feed1_L...)
                    idx = i * num_pols + active_pols.index(p)
                    if idx < len(data['averages']):
                        new_dict[f'f{i}'] = data['averages'][idx]
                source.data = new_dict

                # F. Configurazione Interattivit� Legenda
                if fig.legend:
                    for leg in fig.legend:
                        leg.click_policy = "hide"
                
                new_tabs.append(Panel(child=fig, title=f"Pol {p}"))

            # --- 4. AGGIORNAMENTO INTERFACCIA ---
            doc_state['tabs_container'].tabs = new_tabs
            state.CURRENT_SPEC['updated'] = False

        except Exception as e:
            print(f"BOKEH UPDATE ERROR: {e}")
            import traceback
            traceback.print_exc()
            state.CURRENT_SPEC['updated'] = False

    # Invia l'aggiornamento al thread principale di Bokeh
    doc_state['doc'].add_next_tick_callback(safe_update)


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

def start_bokeh_server(port: int = 5006, apps: Dict[str, Any] = None):
    """
    Versione aggiornata che accetta un dizionario di applicazioni.
    """
    global server, server_thread

    allowed_origins = [f"localhost:{port}", "localhost:5000", "127.0.0.1:5000"]

    # Se non passiamo apps, carichiamo quella di default (retrocompatibilit�)
    if apps is None:
        apps = {'/map_viewer': Application(FunctionHandler(map_app))}
    else:
        # Trasformiamo le funzioni passate in Application Bokeh
        apps = {route: Application(FunctionHandler(func)) for route, func in apps.items()}

    server = Server(apps, port=port, allow_websocket_origin=allowed_origins)

    def run_server():
        server.start()
        server.io_loop.start()

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    print(f"BOKEH: Server multi-app avviato su porta {port}")

'''
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

'''

# ----------------------------------------------------------------------
# 4. NUOVA GESTIONE AGGIORNAMENTO SCATTER PLOT (Metodo Generico X, Y, Z)
# ----------------------------------------------------------------------

def update_scatter_plot(new_points: Dict[str, Dict[str, List[float]]]):
    doc_state = state.BOKEH_DOC_STATE
    if doc_state is None or doc_state['doc'] is None:
        print("BOKEH: Stato per Scatter Plot non inizializzato.")
        return

    def safe_scatter_update():
        
        # Recupero sorgenti e figure (assicurati che p0_spec/p1_spec siano nel doc_state)
        source0 = doc_state.get('source_scatter_pol0')
        source1 = doc_state.get('source_scatter_pol1')
        source_spec = doc_state.get('source_spec')
        color_mapper = doc_state.get('color_mapper_scatter')
        
        # --- MODIFICA QUI: Recupero le figure per cambiare i titoli/assi ---
        p0_fig = doc_state.get('p0_spec')
        p1_fig = doc_state.get('p1_spec')
        
        if source0 is None or source1 is None:
            return

        print('DEBUG: Valore flag ->', state.IS_NEW_DATASET)


       
        if state.IS_NEW_DATASET:
            print("DEBUG: Entrato nella IF!") # Se questa non esce, c'� un problema di logica Python assurdo
            # 1. Recuperiamo i nuovi dati per calcolare i limiti
            # Usiamo LAST_SPECTRUM_X perch� contiene l'asse delle ascisse aggiornato
            new_x = state.LAST_SPECTRUM_X
            
            if new_x is not None and len(new_x) > 0:
                x_min = min(new_x)
                x_max = max(new_x)
                
                # 2. Imponiamo i limiti numerici esatti
                # Questo sovrascrive lo zoom manuale dell'utente
                p0_fig.x_range.start = x_min
                p0_fig.x_range.end = x_max
                p1_fig.x_range.start = x_min
                p1_fig.x_range.end = x_max
                
                print(f"BOKEH: Zoom resettato sui nuovi limiti: [{x_min}, {x_max}]")
    
            # 3. Importante: resettiamo il flag
            state.IS_NEW_DATASET = False



       

       
        # --- 1. AGGIORNAMENTO DINAMICO RANGE COLORI (Invariato) ---
        all_z_values = []
        for pol in ['Pol0', 'Pol1']:
            if pol in new_points:
                all_z_values.extend(new_points[pol].get('z', []))
        
        if all_z_values and color_mapper:
            current_min, current_max = min(all_z_values), max(all_z_values)
            color_mapper.low = min(color_mapper.low, current_min)
            color_mapper.high = max(color_mapper.high, current_max)

        # --- 2. STREAMING DEI DATI MAPPA (Invariato) ---
        if 'Pol0' in new_points and len(new_points['Pol0']['x']) > 0:
            source0.stream({
                'x': new_points['Pol0']['x'],
                'y': new_points['Pol0']['y'],
                'z': new_points['Pol0']['z']
            })
        if 'Pol1' in new_points and len(new_points['Pol1']['x']) > 0:
            source1.stream({
                'x': new_points['Pol1']['x'],
                'y': new_points['Pol1']['y'],
                'z': new_points['Pol1']['z']
            })

        # --- 3. AGGIORNAMENTO SPETTRO + CAMBIO ASSI DINAMICO ---
        if state.SPECTRUM_UPDATED and source_spec is not None:
            
            # --- MODIFICA QUI: LOGICA CAMALEONTE ---
            # Controlliamo il tipo di spettro globale
            spec_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
            
            if spec_type == "simple":
                new_label = "Sampling Point [#]"
                new_title = "Total Power History"
            else:
                new_label = "Frequency [MHz]"
                new_title = "Average Spectrum"

            # Applichiamo i cambiamenti agli assi e ai titoli
            if p0_fig:
                p0_fig.xaxis.axis_label = new_label
                p0_fig.title.text = f"{new_title} - Pol0"
            if p1_fig:
                p1_fig.xaxis.axis_label = new_label
                p1_fig.title.text = f"{new_title} - Pol1"
            
            # ---------------------------------------

            # 1. Spediamo i dati al browser
            source_spec.data = {
                'f':  state.LAST_SPECTRUM_X,
                'p0': state.LAST_SPECTRUM_POL0,
                'p1': state.LAST_SPECTRUM_POL1
            }
    
            # 2. Reset semaforo
            state.SPECTRUM_UPDATED = False 
            print(f"BOKEH: Spettro ({spec_type}) visualizzato, assi aggiornati.")

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