# bokeh_server.py

import time
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
from ichnos import state
# Importa la funzione di creazione del plot iniziale
from ichnos.bokeh_visuals import create_map_layout, create_scatter_layout, create_spectrum_layout

# Variabili Globali per la Gestione del Server
server: Optional[Server] = None
server_thread: Optional[Thread] = None


# ----------------------------------------------------------------------
# 1. FUNZIONE PRINCIPALE DEL DOCUMENTO BOKEH (Mappa & Spettro)
# ----------------------------------------------------------------------

def map_app(doc):
    """Applicazione dedicata alla visualizzazione della MAPPA / SCATTER (Real-time)."""
    # 1. Inizializza il layout specifico in base alla modalità impostata
    if state.USE_SCATTER_MODE:
        layout_obj, doc_state = create_scatter_layout(doc)
    else:
        layout_obj, doc_state = create_map_layout(doc)
    
    # 2. ISOLAMENTO MULTI-UTENTE: Salviamo lo stato dentro il 'doc' della singola tab
    doc.doc_state = doc_state
    
    # Manteniamo comunque il fallback globale per retrocompatibilità, pur sapendo che punterà all'ultima aperta
    state.BOKEH_DOC_STATE = doc_state
    
    # 3. Aggiunge il layout al documento
    doc.add_root(layout_obj)
    
    # 4. Inizializziamo i tracciatori per sapere cosa questa specifica tab ha già renderizzato
    doc.last_map_timestamp = 0.0
    doc.last_scatter_len0 = 0
    doc.last_scatter_len1 = 0
    doc.last_spec_update_flag = False

    # 5. Definiamo la funzione di controllo periodica per QUESTA tab
    def current_map_tab_check():
        check_for_map_updates_per_tab(doc)
        
    callback_obj = doc.add_periodic_callback(current_map_tab_check, 200)
    
    # PULIZIA ANTI LEAK: Rimuove il callback alla chiusura o refresh (F5) della tab
    def on_session_destroyed(session_context):
        try:
            doc.remove_periodic_callback(callback_obj)
            print("BOKEH MAP: Sessione chiusa/refresgata. Periodic callback rimosso.")
        except Exception:
            pass

    doc.on_session_destroyed(on_session_destroyed)


def spec_app(doc):
    """Applicazione dedicata al monitoraggio dello SPETTRO (Real-time)."""
    layout, doc_state = create_spectrum_layout(doc)
    doc.doc_state = doc_state
    state.SPEC_DOC_STATE = doc_state 
    doc.add_root(layout)
    
    def current_tab_check():
        check_for_spec_updates_per_tab(doc)
    
    callback_obj = doc.add_periodic_callback(current_tab_check, 200)
    
    def on_session_destroyed(session_context):
        try:
            doc.remove_periodic_callback(callback_obj)
            print("BOKEH SPEC: Sessione chiusa/refresgata. Periodic callback rimosso.")
        except Exception:
            pass

    doc.on_session_destroyed(on_session_destroyed)


# ----------------------------------------------------------------------
# 2. CONTROLLORI PERIODICI PER SINGOLA TAB (Esecuzione asincrona sicura)
# ----------------------------------------------------------------------

def check_for_spec_updates_per_tab(doc):
    """Controlla se ci sono aggiornamenti dello spettro basandosi sul nome del file per ogni tab."""
    if not hasattr(doc, 'doc_state') or not doc.doc_state:
        return
        
    data = state.CURRENT_SPEC
    current_file = data.get('filename')
    last_displayed_file = getattr(doc, 'last_displayed_file', None)
    
    if (current_file and current_file != last_displayed_file) or data.get('updated'):
        doc.last_displayed_file = current_file
        update_spectrum_plot_per_tab(doc)


def check_for_map_updates_per_tab(doc):
    """Controlla se ci sono nuovi dati di Mappa o Scatter accumulati dal Worker B."""
    if not hasattr(doc, 'doc_state') or not doc.doc_state:
        return

    # CASO SCATTER MODE (Nuvola di punti + spettro ancillare)
    if state.USE_SCATTER_MODE:
        current_len0 = len(state.CURRENT_SCATTER_DATA.get('Pol0', {}).get('x', [])) if hasattr(state, 'CURRENT_SCATTER_DATA') else 0
        current_len1 = len(state.CURRENT_SCATTER_DATA.get('Pol1', {}).get('x', [])) if hasattr(state, 'CURRENT_SCATTER_DATA') else 0
        
        if current_len0 != doc.last_scatter_len0 or current_len1 != doc.last_scatter_len1 or state.SPECTRUM_UPDATED:
            doc.last_scatter_len0 = current_len0
            doc.last_scatter_len1 = current_len1
            update_scatter_plot_per_tab(doc)
            
    # CASO MAPPA GRIGLIATA STANDARD (Mappa a pixel + spettrogramma RFI inferiore)
    else:
        current_map_ts = state.LAST_MAP_TIMESTAMP if hasattr(state, 'LAST_MAP_TIMESTAMP') else 0.0
        
        # Se c'è una nuova mappa OPPURE il processor ha segnalato un update dello spettro di strisciata
        if current_map_ts > doc.last_map_timestamp or state.SPECTRUM_UPDATED:
            doc.last_map_timestamp = current_map_ts
            
            # 1. Aggiorna la mappa grigliata a pixel
            update_bokeh_plot_per_tab(doc, state.LATEST_MAP_RESULTS if hasattr(state, 'LATEST_MAP_RESULTS') else {})
            
            # 2. AGGANCIO FIX: Aggiorna lo spettrogramma/grafico RFI inferiore se presente nel layout della mappa
            if 'source_spec' in doc.doc_state:
                update_ancillary_spectrum_for_map(doc)



def update_ancillary_spectrum_for_map(doc):
    """Aggiorna lo spettro RFI inferiore agganciato al layout della mappa grigliata."""
    doc_state = doc.doc_state
    
    def safe_ancillary_update():
        source_spec = doc_state.get('source_spec')
        p0_fig = doc_state.get('p0_spec')
        p1_fig = doc_state.get('p1_spec')
        
        if source_spec is not None:
            spec_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
            new_label = "Sampling Point [#]" if spec_type == "simple" else "Frequency [MHz]"
            new_title = "Total Power History" if spec_type == "simple" else "Average Spectrum"

            if p0_fig and p0_fig.below:
                p0_fig.below[0].axis_label = new_label
                p0_fig.title.text = f"{new_title} - Pol0"
            if p1_fig and p1_fig.below:
                p1_fig.below[0].axis_label = new_label
                p1_fig.title.text = f"{new_title} - Pol1"
            
            # Spedisce i dati d'intensit� correnti memorizzati nello stato
            source_spec.data = {
                'f':  state.LAST_SPECTRUM_X,
                'p0': state.LAST_SPECTRUM_POL0,
                'p1': state.LAST_SPECTRUM_POL1
            }
            state.SPECTRUM_UPDATED = False
            print("BOKEH: Spettrogramma RFI inferiore aggiornato per la tab corrente.")

    doc.add_next_tick_callback(safe_ancillary_update)






# ----------------------------------------------------------------------
# 3. LOGICHE DI RENDERING E AGGIORNAMENTO PLOT
# ----------------------------------------------------------------------

def update_spectrum_plot_per_tab(doc):
    doc_state = doc.doc_state
    data = state.CURRENT_SPEC
    if not doc_state: return

    def safe_update():
        try:
            t_start = time.time()
            is_stokes = (data.get('spectrum_type') == 'stokes')
            is_simple = (data.get('spectrum_type') == 'simple')
            active_pols = ['I', 'Q', 'U', 'V'] if is_stokes else ['LL', 'RR']
            
            num_pols = len(active_pols)
            num_feeds = len(data['averages']) // num_pols if num_pols > 0 else 0
            file_title = data.get('filename', 'File Sconosciuto')
            labels = data.get('legend_labels', [])
            colors = Category10[10]
            
            new_tabs = []
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

            for p in active_pols:
                if p not in doc_state['figs']: continue
                fig = doc_state['figs'][p]
                source = doc_state['sources'][p]
                
                if fig.below:
                    fig.below[0].axis_label = "Sampling Point" if is_simple else "Channel"
                               
                f_min = data.get('f_min', 0.0)
                f_max = data.get('f_max', 1.0)
                
                if 'freq_range' in fig.extra_x_ranges:
                    fig.extra_x_ranges['freq_range'].start = f_min
                    fig.extra_x_ranges['freq_range'].end = f_max
                    for axis in fig.above:
                        if hasattr(axis, 'x_range_name') and axis.x_range_name == "freq_range":
                            axis.visible = not is_simple
                            axis.axis_label = "Frequency (MHz)" if not is_simple else ""

                freq_info = f" | {f_min:.1f}-{f_max:.1f} MHz" if not is_simple else ""
                fig.title.text = f"FILE: {file_title} | Pol: {p}{freq_info} ({num_feeds} Feeds)"
                fig.renderers = [r for r in fig.renderers if r.name != "data_line"]
                if fig.legend:
                    for leg in fig.legend: leg.items = []
                
                for i in range(num_feeds):
                    current_label = labels[i] if i < len(labels) else f"Feed {i}"
                    is_visible = current_label not in hidden_labels[p]
                    fig.line(x='x', y=f'f{i}', source=source, color=colors[i % 10], legend_label=current_label, line_width=2, name="data_line", visible=is_visible)

                new_dict = {'x': data['x']}
                for i in range(num_feeds):
                    idx = i * num_pols + active_pols.index(p)
                    if idx < len(data['averages']):
                        new_dict[f'f{i}'] = data['averages'][idx]
                source.data = new_dict

                if fig.legend:
                    for leg in fig.legend: leg.click_policy = "hide"
                new_tabs.append(Panel(child=fig, title=f"Pol {p}"))

            doc_state['tabs_container'].tabs = new_tabs
            state.CURRENT_SPEC['updated'] = False
            print(f"Bokeh tab update elapsed: {time.time() - t_start:.3f} s")            
        except Exception as e:
            print(f"BOKEH UPDATE ERROR: {e}")
            state.CURRENT_SPEC['updated'] = False

    doc.add_next_tick_callback(safe_update)


def update_bokeh_plot_per_tab(doc, result_maps: Dict[str, Dict[str, Any]]):
    """Aggiorna le mappe grigliate isolandosi sulla singola istanza della tab browser."""
    doc_state = doc.doc_state
    if not doc_state: return

    def safe_update():
        source_pol0 = doc_state['source_pol0']
        source_pol1 = doc_state['source_pol1']
        color_mapper = doc_state['color_mapper']
        
        global_low_color, global_high_color = float('inf'), float('-inf')
        for pol_key in ['Pol0', 'Pol1']:
            if pol_key in result_maps:
                grid_map = result_maps[pol_key]
                if 'low_color' in grid_map and 'high_color' in grid_map:
                    global_low_color = min(global_low_color, grid_map['low_color'])
                    global_high_color = max(global_high_color, grid_map['high_color'])

        if global_low_color < global_high_color:
            color_mapper.low = global_low_color
            color_mapper.high = global_high_color

        if 'Pol0' in result_maps:
            grid_map = result_maps['Pol0']
            source_pol0.data = {
                'image': [grid_map['image']], 
                'x': [grid_map['x']], 'y': [grid_map['y']],
                'dw': [grid_map['dw']], 'dh': [grid_map['dh']],
            }

        if 'Pol1' in result_maps:
            grid_map = result_maps['Pol1']
            source_pol1.data = {
                'image': [grid_map['image']], 
                'x': [grid_map['x']], 'y': [grid_map['y']],
                'dw': [grid_map['dw']], 'dh': [grid_map['dh']],
            }
        print("BOKEH: Aggiornamento sicuro mappa completato per la sessione corrente.")

    doc.add_next_tick_callback(safe_update)


def update_scatter_plot_per_tab(doc):
    """Esegue lo streaming dei punti e dello spettro ancillare isolandosi sulla singola istanza della tab."""
    doc_state = doc.doc_state
    if not doc_state: return
    
    # Recuperiamo i dati correnti accumulati nello stato
    new_points = state.CURRENT_SCATTER_DATA if hasattr(state, 'CURRENT_SCATTER_DATA') else {}

    def safe_scatter_update():
        source0 = doc_state.get('source_scatter_pol0')
        source1 = doc_state.get('source_scatter_pol1')
        source_spec = doc_state.get('source_spec')
        color_mapper = doc_state.get('color_mapper_scatter')
        p0_fig = doc_state.get('p0_spec')
        p1_fig = doc_state.get('p1_spec')
        
        if source0 is None or source1 is None: return

        if state.IS_NEW_DATASET:
            new_x = state.LAST_SPECTRUM_X
            if new_x is not None and len(new_x) > 0:
                x_min, x_max = min(new_x), max(new_x)
                if p0_fig:
                    p0_fig.x_range.start = x_min
                    p0_fig.x_range.end = x_max
                if p1_fig:
                    p1_fig.x_range.start = x_min
                    p1_fig.x_range.end = x_max
            state.IS_NEW_DATASET = False

        all_z_values = []
        for pol in ['Pol0', 'Pol1']:
            if pol in new_points: all_z_values.extend(new_points[pol].get('z', []))
        
        if all_z_values and color_mapper:
            color_mapper.low = min(color_mapper.low, min(all_z_values))
            color_mapper.high = max(color_mapper.high, max(all_z_values))

        # Nota: per evitare duplicazioni nello streaming cumulativo tra tab,
        # facciamo un assegnamento completo (.data =) basato su quanto memorizzato nello stato complessivo
        if 'Pol0' in new_points:
            source0.data = {'x': new_points['Pol0']['x'], 'y': new_points['Pol0']['y'], 'z': new_points['Pol0']['z']}
        if 'Pol1' in new_points:
            source1.data = {'x': new_points['Pol1']['x'], 'y': new_points['Pol1']['y'], 'z': new_points['Pol1']['z']}

        if state.SPECTRUM_UPDATED and source_spec is not None:
            spec_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
            new_label = "Sampling Point [#]" if spec_type == "simple" else "Frequency [MHz]"
            new_title = "Total Power History" if spec_type == "simple" else "Average Spectrum"

            if p0_fig:
                if p0_fig.below: p0_fig.below[0].axis_label = new_label
                p0_fig.title.text = f"{new_title} - Pol0"
            if p1_fig:
                if p1_fig.below: p1_fig.below[0].axis_label = new_label
                p1_fig.title.text = f"{new_title} - Pol1"
            
            source_spec.data = {
                'f':  state.LAST_SPECTRUM_X,
                'p0': state.LAST_SPECTRUM_POL0,
                'p1': state.LAST_SPECTRUM_POL1
            }
            state.SPECTRUM_UPDATED = False 

    doc.add_next_tick_callback(safe_scatter_update)


# --- INTERFACCE COMPATIBILI CON THREAD ESTERNI (WORKER B) ---
# Queste funzioni vengono chiamate dal Worker B per depositare i dati nello stato e notificare il cambio di timestamp

def update_bokeh_plot(result_maps: Dict[str, Dict[str, Any]]):
    """Aggiorna i buffer globali per fare in modo che le singole tab leggano i dati in differita."""
    state.LATEST_MAP_RESULTS = result_maps
    state.LAST_MAP_TIMESTAMP = time.time()  # Fa scattare il controllo periodico di ogni tab indipendente

def update_scatter_plot(new_points: Dict[str, Dict[str, List[float]]]):
    """Aggiorna i buffer globali dello scatter per le tab attive."""
    if not hasattr(state, 'CURRENT_SCATTER_DATA'):
        state.CURRENT_SCATTER_DATA = {'Pol0': {'x': [], 'y': [], 'z': []}, 'Pol1': {'x': [], 'y': [], 'z': []}}
    
    # Estendiamo le liste globali con i nuovi punti in arrivo dal Worker
    for pol in ['Pol0', 'Pol1']:
        if pol in new_points:
            state.CURRENT_SCATTER_DATA[pol]['x'].extend(new_points[pol].get('x', []))
            state.CURRENT_SCATTER_DATA[pol]['y'].extend(new_points[pol].get('y', []))
            state.CURRENT_SCATTER_DATA[pol]['z'].extend(new_points[pol].get('z', []))


def reset_scatter_plot():
    """Pulisce i dati globali dello scatter."""
    if hasattr(state, 'CURRENT_SCATTER_DATA'):
        state.CURRENT_SCATTER_DATA = {'Pol0': {'x': [], 'y': [], 'z': []}, 'Pol1': {'x': [], 'y': [], 'z': []}}
    # Notifichiamo il reset forzando l'aggiornamento a lunghezza zero delle tab
    doc_state = state.BOKEH_DOC_STATE
    if doc_state and 'doc' in doc_state and doc_state['doc']:
        def safe_reset():
            if 'source_scatter_pol0' in doc_state:
                doc_state['source_scatter_pol0'].data = {'x': [], 'y': [], 'z': []}
                doc_state['source_scatter_pol1'].data = {'x': [], 'y': [], 'z': []}
        doc_state['doc'].add_next_tick_callback(safe_reset)


# ----------------------------------------------------------------------
# 4. AVVIO DEL SERVER BOKEH
# ----------------------------------------------------------------------

def start_bokeh_server(port: int = 5006, apps: Dict[str, Any] = None):
    global server, server_thread
    allowed_origins = ["*"]

    if apps is None:
        apps = {'/map_viewer': Application(FunctionHandler(map_app))}
    else:
        apps = {route: Application(FunctionHandler(func)) for route, func in apps.items()}

    server = Server(apps, address="0.0.0.0", port=port, allow_websocket_origin=allowed_origins)

    def run_server():
        server.start()
        server.io_loop.start()

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    print(f"BOKEH: Server multi-app avviato su porta {port}")