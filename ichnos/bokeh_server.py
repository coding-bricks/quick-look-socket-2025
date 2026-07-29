# bokeh_server.py

import time
import sys
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
    
    # Manteniamo comunque il fallback globale per retrocompatibilità
    state.BOKEH_DOC_STATE = doc_state
    
    # 3. Aggiunge il layout al documento
    doc.add_root(layout_obj)
    
    # 4. Inizializziamo i tracciatori per sapere cosa questa specifica tab ha già renderizzato
    doc.last_map_timestamp = 0.0
    doc.last_scatter_lens = {'Pol0': 0, 'Pol1': 0, 'RL': 0, 'LR': 0}
    doc.last_spec_update_flag = False

    # 5. Definiamo la funzione di controllo periodica per QUESTA tab
    def current_map_tab_check():
        check_for_map_updates_per_tab(doc)
        
    callback_obj = doc.add_periodic_callback(current_map_tab_check, 200)
    
    # PULIZIA ANTI LEAK: Rimuove il callback alla chiusura o refresh (F5) della tab
    def on_session_destroyed(session_context):
        try:
            doc.remove_periodic_callback(callback_obj)
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
        scatter_data = getattr(state, 'CURRENT_SCATTER_DATA', {})
        current_lens = {p: len(scatter_data.get(p, {}).get('x', [])) for p in ['Pol0', 'Pol1', 'RL', 'LR']}
        
        has_new_scatter = any(current_lens[p] != doc.last_scatter_lens.get(p, 0) for p in current_lens)
        
        if has_new_scatter or state.SPECTRUM_UPDATED:
            doc.last_scatter_lens = current_lens
            update_scatter_plot_per_tab(doc)
            
    # CASO MAPPA GRIGLIATA STANDARD (Mappa a pixel + spettrogramma RFI inferiore)
    else:
        current_map_ts = state.LAST_MAP_TIMESTAMP if hasattr(state, 'LAST_MAP_TIMESTAMP') else 0.0
        
        # Se c'è una nuova mappa OPPURE il processor ha segnalato un update dello spettro di strisciata
        if current_map_ts > doc.last_map_timestamp or state.SPECTRUM_UPDATED:
            doc.last_map_timestamp = current_map_ts
            
            # 1. Aggiorna la mappa grigliata a pixel (4 Tab statiche)
            latest_maps = getattr(state, 'LATEST_MAP_RESULTS', {})
            update_bokeh_plot_per_tab(doc, latest_maps)
            
            # 2. Aggiorna lo spettrogramma/grafico RFI inferiore se presente nel layout della mappa
            if 'source_spec' in doc.doc_state:
                update_ancillary_spectrum_for_map(doc)


def update_ancillary_spectrum_for_map(doc):
    """Aggiorna lo spettro RFI inferiore agganciato al layout della mappa grigliata."""
    doc_state = doc.doc_state
    if not doc_state:
        return
    
    def safe_ancillary_update():
        try:
            source_spec = doc_state.get('source_spec')
            fig_map = {
                'p0': doc_state.get('p0_spec'),
                'p1': doc_state.get('p1_spec'),
                'prl': doc_state.get('prl_spec'),
                'plr': doc_state.get('plr_spec'),
            }
            
            if source_spec is not None:
                spec_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
                has_4_pols = (spec_type == 'stokes')
                
                new_label = "Sampling Point [#]" if spec_type == "simple" else "Frequency [MHz]"
                new_title = "Total Power History" if spec_type == "simple" else "Average Spectrum"

                # Estrarre i dati correnti dell'asse X
                f_data = getattr(state, 'LAST_SPECTRUM_X', np.array([]))
                n_samples = len(f_data)

                # --- FIX CRITICO 1: RESET RANGE ASSE X SE CAMBIA DATASET ---
                if n_samples > 0:
                    x_min, x_max = float(np.nanmin(f_data)), float(np.nanmax(f_data))
                    # Se il range è piatto (es. 1 solo punto), estendiamo leggermente
                    if x_min == x_max:
                        x_min -= 0.5
                        x_max += 0.5

                    for fig_key, fig_obj in fig_map.items():
                        if fig_obj:
                            # Aggiorna label e titolo
                            if fig_obj.below: 
                                fig_obj.below[0].axis_label = new_label
                            fig_obj.title.text = f"{new_title} - {fig_key.upper()}"
                            
                            # Forza il riallineamento visivo dell'asse X al nuovo dominio (Sampling Point vs Frequency)
                            fig_obj.x_range.start = x_min
                            fig_obj.x_range.end = x_max

                # Array di riempimento coerente per evitare disallineamenti di dimensione in Bokeh
                dummy_cross = np.full(n_samples, np.nan) if n_samples > 0 else np.array([])

                p0_data = getattr(state, 'LAST_SPECTRUM_POL0', np.array([]))
                p1_data = getattr(state, 'LAST_SPECTRUM_POL1', np.array([]))
                prl_data = getattr(state, 'LAST_SPECTRUM_RL', dummy_cross) if has_4_pols else dummy_cross
                plr_data = getattr(state, 'LAST_SPECTRUM_LR', dummy_cross) if has_4_pols else dummy_cross

                # Garantiamo che tutti gli array inviati a ColumnDataSource abbiano ESATTAMENTE n_samples
                source_spec.data = {
                    'f':   f_data if len(f_data) == n_samples else np.array([]),
                    'p0':  p0_data if len(p0_data) == n_samples else dummy_cross,
                    'p1':  p1_data if len(p1_data) == n_samples else dummy_cross,
                    'prl': prl_data if len(prl_data) == n_samples else dummy_cross,
                    'plr': plr_data if len(plr_data) == n_samples else dummy_cross,
                }
                state.SPECTRUM_UPDATED = False
        except Exception:
            pass

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
        except Exception:
            state.CURRENT_SPEC['updated'] = False

    doc.add_next_tick_callback(safe_update)


def update_bokeh_plot_per_tab(doc, result_maps: Dict[str, Dict[str, Any]]):
    """Aggiorna le mappe grigliate isolandosi sulla singola istanza della tab browser per le 4 polarizzazioni."""
    doc_state = doc.doc_state
    if not doc_state: 
        return

    def safe_update():
        try:
            sources = {
                'Pol0': doc_state.get('source_pol0'),
                'Pol1': doc_state.get('source_pol1'),
                'RL':   doc_state.get('source_rl'),
                'LR':   doc_state.get('source_lr'),
            }
            
            color_mapper_direct = doc_state.get('color_mapper_direct')
            color_mapper_cross  = doc_state.get('color_mapper_cross')
            
            # --- FIX CRITICO 2: DISABILITAZIONE RIGOROSA DELLE TAB ---
            # Recuperiamo i container delle tab (sia dal dizionario interno che dai layout)
            tabs_dict = doc_state.get('tabs_dict', {})
            spectrum_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
            
            # 4 pol solo se stokes E sono presenti mappe per RL e LR
            has_4_pols = (spectrum_type == 'stokes') and ('RL' in result_maps and 'LR' in result_maps)

            # Sincronizza lo stato di disabilitazione ad OGNI tick
            if 'RL' in tabs_dict and tabs_dict['RL']: 
                tabs_dict['RL'].disabled = not has_4_pols
            if 'LR' in tabs_dict and tabs_dict['LR']: 
                tabs_dict['LR'].disabled = not has_4_pols

            active_keys = ['Pol0', 'Pol1', 'RL', 'LR'] if has_4_pols else ['Pol0', 'Pol1']
            
            # RESET/CALCOLO FRESCO DEI COLORI DIRECT
            direct_vals = []
            for pol_key in ['Pol0', 'Pol1']:
                if pol_key in result_maps:
                    grid_map = result_maps[pol_key]
                    l_val = grid_map.get('low_color')
                    h_val = grid_map.get('high_color')
                    if l_val is not None and h_val is not None and not np.isnan(l_val) and not np.isnan(h_val):
                        direct_vals.extend([l_val, h_val])

            if direct_vals and color_mapper_direct is not None:
                color_mapper_direct.low = float(min(direct_vals))
                color_mapper_direct.high = float(max(direct_vals))

            # RESET/CALCOLO FRESCO DEI COLORI CROSS
            if has_4_pols:
                cross_vals = []
                for pol_key in ['RL', 'LR']:
                    if pol_key in result_maps:
                        grid_map = result_maps[pol_key]
                        l_val = grid_map.get('low_color')
                        h_val = grid_map.get('high_color')
                        if l_val is not None and h_val is not None and not np.isnan(l_val) and not np.isnan(h_val):
                            cross_vals.extend([l_val, h_val])

                if cross_vals and color_mapper_cross is not None:
                    color_mapper_cross.low = float(min(cross_vals))
                    color_mapper_cross.high = float(max(cross_vals))

            # AGGIORNAMENTO DATI DELLE MATRICI
            for key, source in sources.items():
                if source is None: continue
                
                if key in result_maps and key in active_keys:
                    grid_map = result_maps[key]
                    img_data = grid_map['image']
                    
                    if np.iscomplexobj(img_data):
                        img_data = np.abs(img_data)
                    
                    img_data = np.asarray(img_data, dtype=np.float32)

                    source.data = {
                        'image': [img_data], 
                        'x': [grid_map['x']], 'y': [grid_map['y']],
                        'dw': [grid_map['dw']], 'dh': [grid_map['dh']],
                    }
                else:
                    empty_map = np.full((1, 1), np.nan, dtype=np.float32)
                    source.data = {'image': [empty_map], 'x': [0.0], 'y': [0.0], 'dw': [1.0], 'dh': [1.0]}

        except Exception:
            pass

    doc.add_next_tick_callback(safe_update)



def update_scatter_plot_per_tab(doc):
    """Esegue lo streaming dei punti e dello spettro ancillare isolandosi sulla singola istanza della tab."""
    doc_state = doc.doc_state
    if not doc_state: return 
    
    new_points = state.CURRENT_SCATTER_DATA if hasattr(state, 'CURRENT_SCATTER_DATA') else {}

    def safe_scatter_update():
        try:
            sources_scatter = {
                'Pol0': doc_state.get('source_scatter_pol0'),
                'Pol1': doc_state.get('source_scatter_pol1'),
                'RL':   doc_state.get('source_scatter_rl'),
                'LR':   doc_state.get('source_scatter_lr'),
            }
            source_spec = doc_state.get('source_spec')
            
            color_mapper_direct = doc_state.get('color_mapper_direct')
            color_mapper_cross  = doc_state.get('color_mapper_cross')
            
            fig_map = {
                'Pol0': doc_state.get('p0_spec'),
                'Pol1': doc_state.get('p1_spec'),
                'RL':   doc_state.get('prl_spec'),
                'LR':   doc_state.get('plr_spec'),
            }
            
            map_tabs = doc_state.get('map_tabs_dict', {})
            spec_tabs = doc_state.get('spec_tabs_dict', {})

            spectrum_type = getattr(state, 'SPECTRUM_TYPE', 'spectra')
            has_4_pols = (spectrum_type == 'stokes')

            # 1. Abilita / Disabilita Tab in modo deterministico
            for tabs_group in [map_tabs, spec_tabs]:
                if 'RL' in tabs_group: tabs_group['RL'].disabled = not has_4_pols
                if 'LR' in tabs_group: tabs_group['LR'].disabled = not has_4_pols

            # 2. Gestione RESET per NUOVO DATASET (Resetta sia assi che Colorbar)
            if getattr(state, 'IS_NEW_DATASET', False):
                new_x = getattr(state, 'LAST_SPECTRUM_X', None)
                if new_x is not None and len(new_x) > 0:
                    x_min, x_max = min(new_x), max(new_x)
                    for fig in fig_map.values():
                        if fig:
                            fig.x_range.start = x_min
                            fig.x_range.end = x_max
                
                # RESET COLOR MAPPERS SU NUOVO DATASET
                if color_mapper_direct:
                    color_mapper_direct.low = float('inf')
                    color_mapper_direct.high = float('-inf')
                if color_mapper_cross:
                    color_mapper_cross.low = float('inf')
                    color_mapper_cross.high = float('-inf')

                state.IS_NEW_DATASET = False

            # 3. Calcolo dinamico range colori Scatter per il dataset corrente
            z_direct = []
            for pol in ['Pol0', 'Pol1']:
                if pol in new_points:
                    z_direct.extend(new_points[pol].get('z', []))
            if z_direct and color_mapper_direct:
                color_mapper_direct.low = float(min(z_direct))
                color_mapper_direct.high = float(max(z_direct))

            if has_4_pols:
                z_cross = []
                for pol in ['RL', 'LR']:
                    if pol in new_points:
                        z_cross.extend(new_points[pol].get('z', []))
                if z_cross and color_mapper_cross:
                    color_mapper_cross.low = float(min(z_cross))
                    color_mapper_cross.high = float(max(z_cross))

            # 4. Aggiornamento ColumnDataSource per Scatter Plot
            active_pols = ['Pol0', 'Pol1', 'RL', 'LR'] if has_4_pols else ['Pol0', 'Pol1']
            for pol, source in sources_scatter.items():
                if source is None: continue
                
                if pol in new_points and pol in active_pols:
                    source.data = {'x': new_points[pol]['x'], 'y': new_points[pol]['y'], 'z': new_points[pol]['z']}
                else:
                    source.data = {'x': [], 'y': [], 'z': []}

            # 5. Aggiornamento Spettro Ancillare (Coerente per 2 o 4 polarizzazioni)
            if state.SPECTRUM_UPDATED and source_spec is not None:
                new_label = "Sampling Point [#]" if spectrum_type == "simple" else "Frequency [MHz]"
                new_title = "Total Power History" if spectrum_type == "simple" else "Average Spectrum"

                pol_labels = {'Pol0': 'Pol0', 'Pol1': 'Pol1', 'RL': 'Cross RL', 'LR': 'Cross LR'}
                for pol, fig in fig_map.items():
                    if fig:
                        if fig.below: fig.below[0].axis_label = new_label
                        fig.title.text = f"{new_title} - {pol_labels[pol]}"
                
                f_data = getattr(state, 'LAST_SPECTRUM_X', np.array([]))
                n_samples = len(f_data)
                dummy_cross = np.full(n_samples, np.nan) if n_samples > 0 else np.array([])

                source_spec.data = {
                    'f':   f_data,
                    'p0':  getattr(state, 'LAST_SPECTRUM_POL0', np.array([])),
                    'p1':  getattr(state, 'LAST_SPECTRUM_POL1', np.array([])),
                    'prl': getattr(state, 'LAST_SPECTRUM_RL', dummy_cross) if has_4_pols else dummy_cross,
                    'plr': getattr(state, 'LAST_SPECTRUM_LR', dummy_cross) if has_4_pols else dummy_cross,
                }
                state.SPECTRUM_UPDATED = False 

        except Exception:
            pass

    doc.add_next_tick_callback(safe_scatter_update)

# --- INTERFACCE COMPATIBILI CON THREAD ESTERNI (WORKER B) ---

def update_bokeh_plot(result_maps: Dict[str, Dict[str, Any]]):
    """Aggiorna i buffer globali per fare in modo che le singole tab leggano i dati in differita."""
    state.LATEST_MAP_RESULTS = result_maps
    state.LAST_MAP_TIMESTAMP = time.time()  # Fa scattare il controllo periodico di ogni tab indipendente

def update_scatter_plot(new_points: Dict[str, Dict[str, List[float]]]):
    """Aggiorna i buffer globali dello scatter per le tab attive (supporta 4 polarizzazioni)."""
    if not hasattr(state, 'CURRENT_SCATTER_DATA'):
        state.CURRENT_SCATTER_DATA = {
            'Pol0': {'x': [], 'y': [], 'z': []},
            'Pol1': {'x': [], 'y': [], 'z': []},
            'RL':   {'x': [], 'y': [], 'z': []},
            'LR':   {'x': [], 'y': [], 'z': []},
        }
    
    for pol in ['Pol0', 'Pol1', 'RL', 'LR']:
        if pol in new_points:
            state.CURRENT_SCATTER_DATA[pol]['x'].extend(new_points[pol].get('x', []))
            state.CURRENT_SCATTER_DATA[pol]['y'].extend(new_points[pol].get('y', []))
            state.CURRENT_SCATTER_DATA[pol]['z'].extend(new_points[pol].get('z', []))


def reset_scatter_plot():
    """Pulisce i dati globali dello scatter per tutte e 4 le polarizzazioni."""
    if hasattr(state, 'CURRENT_SCATTER_DATA'):
        state.CURRENT_SCATTER_DATA = {
            'Pol0': {'x': [], 'y': [], 'z': []},
            'Pol1': {'x': [], 'y': [], 'z': []},
            'RL':   {'x': [], 'y': [], 'z': []},
            'LR':   {'x': [], 'y': [], 'z': []},
        }
    doc_state = state.BOKEH_DOC_STATE
    if doc_state and 'doc' in doc_state and doc_state['doc']:
        def safe_reset():
            for pol_key in ['source_scatter_pol0', 'source_scatter_pol1', 'source_scatter_rl', 'source_scatter_lr']:
                if pol_key in doc_state:
                    doc_state[pol_key].data = {'x': [], 'y': [], 'z': []}
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