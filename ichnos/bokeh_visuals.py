import os
import numpy as np
import time

from ichnos import state

# Moduli per la creazione di figure e layout di base
from bokeh.plotting import figure

# Importa le funzioni di composizione
from bokeh.layouts import column, row

from bokeh.embed import file_html # For saving plot to HTML
from bokeh.models import LinearAxis, Range1d
# Moduli per gli elementi dati, i colori, la barra colore e i widget (Tabs)
from bokeh.models import (
    ColumnDataSource, 
    LinearColorMapper, 
    ColorBar, 
    Panel, 
    Tabs
)
from bokeh.models.mappers import LinearColorMapper
from bokeh.palettes import Category10
from bokeh.palettes import Magma256 
from bokeh.plotting import figure, column, show # Import Bokeh plotting tools
from bokeh.plotting import figure
from bokeh.resources import CDN # For CDN resources (JS/CSS)

from typing import Dict, Any, Tuple



def _plot_and_save_skarab_nodding_html(plot_save_dir, 
    filename_prefix, final_averages, x, feeds_for_legend, spectrum_type, x_axis_label_val, start_time_total, freq, lo, bw):
    
    start_time_bokeh_build = time.time()

    f_min = float(freq)
    f_max = float(f_min) + float(bw) 

    # print(freq, lo, bw, f_min, f_max)
    
    try:
        # Inizializzazione figures
        if spectrum_type == 'stokes':
            p0 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [STOKES]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=500, tools="pan,wheel_zoom,box_zoom,reset")
            figures = [p0]

            # Create the upper X-Axis expressed in frequency
            p0.extra_x_ranges = {
                "freq_range": Range1d(start=f_min, end=f_max)
            }
            p0.add_layout(
                LinearAxis(
                    x_range_name="freq_range",
                    axis_label="Frequency (MHz)"
                ),
                "above"
            )
        else:
            p1 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [LEFT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")
            p2 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [RIGHT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")
            figures = [p1, p2]

            # Create the upper X-Axis expressed in frequency
            p1.extra_x_ranges = {
                "freq_range": Range1d(start=f_min, end=f_max)
            }
            p1.add_layout(
                LinearAxis(
                    x_range_name="freq_range",
                    axis_label="Frequency (MHz)"
                ),
                "above"
            )

            p2.extra_x_ranges = {
                "freq_range": Range1d(start=f_min, end=f_max)
            }
            p2.add_layout(
                LinearAxis(
                    x_range_name="freq_range",
                    axis_label="Frequency (MHz)"
                ),
                "above"
            )


        n = len(final_averages)
        colors = Category10[n] if n <= 10 else ["black"] * n # Gestione colori

       

        # Aggiunta delle linee (Logica di Nodding)
        if spectrum_type in ['spectra', 'simple']:
            pol_labels = ["LCP/Pol0", "RCP/Pol1"]
            for i in range(0, n, 2):
                feed_id = feeds_for_legend[i] 
                #figures[0].line(x, final_averages[i], legend_label=f"Feed {feed_id} ({pol_labels[0]})", line_width=2, color=colors[i])
                #figures[1].line(x, final_averages[i+1], legend_label=f"Feed {feed_id} ({pol_labels[1]})", line_width=2, color=colors[i+1])
                figures[0].line(x, final_averages[i], legend_label=f"Feed {feed_id}", line_width=2, color=colors[i])
                figures[1].line(x, final_averages[i+1], legend_label=f"Feed {feed_id}", line_width=2, color=colors[i+1])
            final_plot_layout = column(p1, p2, spacing = 20)
        
        elif spectrum_type == 'stokes':
            for i in range(n):
                 feed_id = feeds_for_legend[i]
                 figures[0].line(x, final_averages[i], legend_label=f"Feed {feed_id} (Stokes)", line_width=2, color=colors[i])
            final_plot_layout = column(p0)
        
        else:
             return None

        for p in figures:
            p.legend.click_policy = "hide"

        end_time_bokeh_build = time.time()
        print(f"PROFILING: [Timer 2 NODDING] Costruzione Oggetto Bokeh completata in {end_time_bokeh_build - start_time_bokeh_build:.4f} secondi.")

        # --- SEZIONE SCRITTURA FILE HTML ---
        start_time_io_write = time.time()
        
        unique_id = int(time.time() * 1000)
        plot_html_filename = f"{filename_prefix}_{unique_id}_skarab_nodding_plot.html"
        full_plot_path = os.path.join(plot_save_dir, plot_html_filename)
        plot_static_url = f"/static/plots/{plot_html_filename}"

        html_content = file_html(final_plot_layout, CDN, title=f"SKARAB Nodding Plot: {filename_prefix}")
        with open(full_plot_path, "w") as f:
            f.write(html_content)

        end_time_io_write = time.time()
        print(f"PROFILING: [Timer 3 NODDING] Scrittura file HTML completata in {end_time_io_write - start_time_io_write:.4f} secondi.")

        end_time_total = time.time()
        print(f"PROFILING: TEMPO TOTALE (Nodding) completato in {end_time_total - start_time_total:.4f} secondi.")
        print("---------------------------------------")
        
        return plot_static_url

    except Exception as e:
        print(f"ERRORE GRAVE nel plotting NODDING per {filename_prefix}: {e}")
        return None



def _plot_and_save_html(plot_save_dir, filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, backend, 
    x_axis_label_val, x, averages, feed_number, start_time_total, freq, lo, bw):

    
    f_min = float(freq)
    f_max = float(f_min) + float(bw)

    print(f_min)
    print(f_max)
    print((f_max-f_min)/chs)



    """
    # conversione canale ? frequenza
    freq_axis = f_min + (x / (len(x) - 1)) * (f_max - f_min)
    print("freq_axis", freq_axis)
    """


        
    # --- SEZIONE 2: CREAZIONE OGGETTI BOKEH (Potenziale bottleneck CPU/Bokeh) ---
    start_time_bokeh_build = time.time()

    try:
        
        # Inizializzazione figure (p0, p1, p2 come nel tuo codice)
        p0 = figure(title=f"File: {filename_prefix} - POL [STOKES]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=500, tools="pan,wheel_zoom,box_zoom,reset")
        p1 = figure(title=f"File: {filename_prefix} - POL [LEFT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=500, tools="pan,wheel_zoom,box_zoom,reset")
        p2 = figure(title=f"File: {filename_prefix} - POL [RIGHT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=500, tools="pan,wheel_zoom,box_zoom,reset")

        # Selezione colori (tua logica originale)
        n = len(averages)
        if n in Category10:
            colors = Category10[n]
        elif n in (1, 2):
            colors = ["#1f77b4", "#ff7f0e"][:n]
        else:
            colors = ["black"] # Fallback


        # ------ ASSE X SUPERIORE (FREQUENZA) ------
        p0.extra_x_ranges = {
            "freq_range": Range1d(start=f_min, end=f_max)
        }
        p0.add_layout(
            LinearAxis(
                x_range_name="freq_range",
                axis_label="Frequency (MHz)"
            ),
            "above"
        )

        p1.extra_x_ranges = {
            "freq_range": Range1d(start=f_min, end=f_max)
        }
        p1.add_layout(
            LinearAxis(
                x_range_name="freq_range",
                axis_label="Frequency (MHz)"
            ),
            "above"
        )


        p2.extra_x_ranges = {
            "freq_range": Range1d(start=f_min, end=f_max)
        }
        p2.add_layout(
            LinearAxis(
                x_range_name="freq_range",
                axis_label="Frequency (MHz)"
            ),
            "above"
        )


        # Aggiunta delle linee (QUI avviene il rendering dei 65.000 punti)
        if(filename_extension == '.fits'):
            f = 0
            if(spectrum_type == 'spectra'):
                for i in range(0, len(averages), 2):
                    # Queste linee contengono l'array enorme (65000 punti)
                    p1.line(x, averages[i], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i])
                    p2.line(x, averages[i+1], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i+1])
                    f+=1
            elif(spectrum_type == 'stokes'):
                for i in range(0, len(averages), 1):
                    p0.line(x, averages[i], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i])
                    f+=1
            elif(spectrum_type == 'simple'):
                feed = feeds[0]
                p1.line(x, averages[0], legend_label=f"Feed-{feed}", line_width=2, color=colors[0])
                p2.line(x, averages[1], legend_label=f"Feed-{feed}", line_width=2, color=colors[1])
        else: # .fits# multi-feed
            if(spectrum_type == 'spectra'):
                p1.line(x, averages[0], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[0])
                p2.line(x, averages[1], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[1])
            else:
                p0.line(x, averages[0], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[0])

        # Configurazione legenda
        p0.legend.click_policy = p1.legend.click_policy = p2.legend.click_policy = "hide"

        # Layout finale
        #if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
        #    final_plot_layout = column(p1, p2, spacing = 20)
        #else:
        #    final_plot_layout = column(p0)

        

        # --- NUOVO LAYOUT CON TABS ---
        if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
            # Creiamo i pannelli per le due polarizzazioni
            tab1 = Panel(child=p1, title="LEFT Polarization (LCP)")
            tab2 = Panel(child=p2, title="RIGHT Polarization (RCP)")
            
            # Li raggruppiamo in un oggetto Tabs
            final_plot_layout = Tabs(tabs=[tab1, tab2])
            
            # Sincronizziamo gli assi X per comodit� di analisi
            p2.x_range = p1.x_range
            p2.extra_x_ranges['freq_range'] = p1.extra_x_ranges['freq_range']
            
        else:
            # Per Stokes o altri, manteniamo il layout a colonna singola (p0)
            final_plot_layout = column(p0)


        # ----------------------------------------------------------------------
        # TIMER 2: Tempo di Generazione Plot (p.line e costruzione del layout)
        end_time_bokeh_build = time.time()
        print(f"PROFILING: [Timer 2] Costruzione Oggetto Bokeh completata in {end_time_bokeh_build - start_time_bokeh_build:.4f} secondi.")


        # --- SEZIONE 3: SCRITTURA FILE HTML (Potenziale bottleneck I/O Rete) ---
        start_time_io_write = time.time()
        
        # Generazione ID univoco e path
        unique_id = int(time.time() * 1000)
        plot_html_filename = f"{filename_prefix}_{unique_id}_plot.html"
        full_plot_path = os.path.join(plot_save_dir, plot_html_filename)
        plot_static_url = f"/static/plots/{plot_html_filename}"

        # Generazione del contenuto HTML e scrittura su disco
        html_content = file_html(final_plot_layout, CDN, title=f"FITS Data Plot: {filename_prefix}")
        with open(full_plot_path, "w") as f:
            f.write(html_content)

        # ----------------------------------------------------------------------
        # TIMER 3: Tempo di Scrittura I/O (file_html e scrittura su disco)
        end_time_io_write = time.time()
        print(f"PROFILING: [Timer 3] Scrittura file HTML completata in {end_time_io_write - start_time_io_write:.4f} secondi.")


        # ----------------------------------------------------------------------
        # END TIME: Tempo Totale
        end_time_total = time.time()
        print(f"PROFILING: TEMPO TOTALE per il plotting completato in {end_time_total - start_time_total:.4f} secondi.")
        print("---------------------------------------")
        
        return plot_static_url

    except Exception as e:
        print(f"ERRORE GRAVE nel plotting per {filename_prefix}: {e}")
        print("---------------------------------------")
        return None


# IMPORTANTE: La firma deve riflettere le importazioni corrette.
# Usiamo 'Tuple' da typing e rimuoviamo 'layout' che non esiste pi� come tipo.
def create_map_layout(doc) -> Tuple[Any, Dict[str, Any]]: 
    """
    Crea il layout iniziale della mappa 2D di Bokeh con 4 pannelli statici
    (Pol0, Pol1, RL, LR) e inizializza i ColumnDataSource per gli aggiornamenti dinamici.

    Parametri:
    - doc: Il documento Bokeh corrente (curdoc()).

    Ritorna:
    - Tuple: (layout finale (tipo Any), dizionario contenente i riferimenti ai DataSource e Tab)
    """

    # --- 1. Definizione di Stili e Mappe Colore ---
    
    # Range iniziale dei colori (verrà aggiornato dinamicamente dal Worker B)
    color_mapper = LinearColorMapper(palette=Magma256, low=0, high=100)

    # --- 2. Inizializzazione dei ColumnDataSource per le 4 Polarizzazioni ---
    
    # Dati iniziali VUOTI: usiamo un array 1x1 con un valore NaN come placeholder
    empty_map_data = np.full((1, 1), np.nan, dtype=np.float32)
    
    initial_source_data = {
        'image': [empty_map_data], 
        'x': [0.0],
        'y': [0.0],
        'dw': [1.0],
        'dh': [1.0],
    }

    source_pol0 = ColumnDataSource(data=initial_source_data)
    source_pol1 = ColumnDataSource(data=initial_source_data)
    source_rl   = ColumnDataSource(data=initial_source_data)
    source_lr   = ColumnDataSource(data=initial_source_data)
    
    # --- 3. Creazione delle Figure ---
    fig_kwargs = dict(
        x_axis_label="X (RA/EL)",
        y_axis_label="Y (DEC/AZ)",
        active_scroll="wheel_zoom",
        width=600, 
        height=500
    )

    # --- Figura Pol0 ---
    p0 = figure(title="Polarizzazione 0 (Pol0)", **fig_kwargs)
    p0.image(image='image', x='x', y='y', dw='dw', dh='dh', source=source_pol0, color_mapper=color_mapper)
    color_bar0 = ColorBar(color_mapper=color_mapper, label_standoff=12, border_line_color=None, location=(0, 0))
    p0.add_layout(color_bar0, 'right')

    # --- Figura Pol1 ---
    p1 = figure(title="Polarizzazione 1 (Pol1)", **fig_kwargs)
    p1.image(image='image', x='x', y='y', dw='dw', dh='dh', source=source_pol1, color_mapper=color_mapper)
    color_bar1 = ColorBar(color_mapper=color_mapper, label_standoff=12, border_line_color=None, location=(0, 0))
    p1.add_layout(color_bar1, 'right')

    # --- Figura Cross-Pol RL ---
    p_rl = figure(title="Stokes / Cross-Pol RL", **fig_kwargs)
    p_rl.image(image='image', x='x', y='y', dw='dw', dh='dh', source=source_rl, color_mapper=color_mapper)
    color_bar_rl = ColorBar(color_mapper=color_mapper, label_standoff=12, border_line_color=None, location=(0, 0))
    p_rl.add_layout(color_bar_rl, 'right')

    # --- Figura Cross-Pol LR ---
    p_lr = figure(title="Stokes / Cross-Pol LR", **fig_kwargs)
    p_lr.image(image='image', x='x', y='y', dw='dw', dh='dh', source=source_lr, color_mapper=color_mapper)
    color_bar_lr = ColorBar(color_mapper=color_mapper, label_standoff=12, border_line_color=None, location=(0, 0))
    p_lr.add_layout(color_bar_lr, 'right')

    # --- 4. Creazione del Layout Finale con 4 Tabs Statistiche ---
    
    # Crea i pannelli (Tabs)
    # NOTA: Usiamo 'Panel' o 'TabPanel' a seconda della versione di Bokeh installata
    tab0  = Panel(child=p0,   title="Pol0")
    tab1  = Panel(child=p1,   title="Pol1")
    tab_rl = Panel(child=p_rl, title="Cross RL")
    tab_lr = Panel(child=p_lr, title="Cross LR")
    
    map_tabs = Tabs(tabs=[tab0, tab1, tab_rl, tab_lr])
    
    final_layout = column(map_tabs)
    
    # --- 5. Ritorno dello Stato per l'Aggiornamento ---
    
    doc_state = {
        'doc': doc,
        'source_pol0': source_pol0,
        'source_pol1': source_pol1,
        'source_rl': source_rl,
        'source_lr': source_lr,
        'color_mapper': color_mapper,
        'tabs_dict': {
            'Pol0': tab0,
            'Pol1': tab1,
            'RL': tab_rl,
            'LR': tab_lr
        }
    }
    
    return final_layout, doc_state



def create_scatter_layout(doc) -> Tuple[Any, Dict[str, Any]]: 
    """
    Crea il layout iniziale con 4 Tab statiche per:
    1. Mappe Scatter (Pol0, Pol1, RL, LR)
    2. Spettro Medio Ancillare (Pol0, Pol1, RL, LR) posizionato sotto la mappa.
    """
    # Recuperiamo il sistema di coordinate attuale dallo stato
    coord_system = getattr(state, 'CURRENT_COORD_SYSTEM', 'AZEL')

    # Configurazione dinamica delle label mappa
    if coord_system == "RADEC":
        x_label, y_label = "RA [deg]", "DEC [deg]"
        plot_title_suffix = "Equatorial (RA/DEC)"
    else:
        x_label, y_label = "AZ [deg]", "EL [deg]"
        plot_title_suffix = "Horizontal (AZ/EL)"

    # --- 1. Definizione Mapper Colore per lo Scatter ---
    color_mapper = LinearColorMapper(palette=Magma256, low=0, high=1)

    # --- 2. Inizializzazione ColumnDataSource (4 Polarizzazioni) ---
    source_scatter_pol0 = ColumnDataSource(data=dict(x=[], y=[], z=[]))
    source_scatter_pol1 = ColumnDataSource(data=dict(x=[], y=[], z=[]))
    source_scatter_rl   = ColumnDataSource(data=dict(x=[], y=[], z=[]))
    source_scatter_lr   = ColumnDataSource(data=dict(x=[], y=[], z=[]))
    
    # Sorgente per lo spettro ancillare (X=frequenza/canale, Y=potenza per le 4 Pol)
    source_spec = ColumnDataSource(data=dict(f=[], p0=[], p1=[], prl=[], plr=[]))

    # --- 3. Creazione Figure MAPPA SCATTER ---
    tooltips = [("X", "@x"), ("Y", "@y"), ("Z (Power)", "@z")]
    map_kwargs = dict(
        x_axis_label=x_label, y_axis_label=y_label,
        width=780, height=560, active_scroll="wheel_zoom", tooltips=tooltips
    )

    p0_map = figure(title=f"Scatter Map - {plot_title_suffix} (Pol0)", **map_kwargs)
    p0_map.circle(x='x', y='y', size=5, source=source_scatter_pol0,
                  color={'field': 'z', 'transform': color_mapper}, line_color=None)

    p1_map = figure(title=f"Scatter Map - {plot_title_suffix} (Pol1)", **map_kwargs)
    p1_map.circle(x='x', y='y', size=5, source=source_scatter_pol1,
                  color={'field': 'z', 'transform': color_mapper}, line_color=None)

    prl_map = figure(title=f"Scatter Map - {plot_title_suffix} (Cross RL)", **map_kwargs)
    prl_map.circle(x='x', y='y', size=5, source=source_scatter_rl,
                   color={'field': 'z', 'transform': color_mapper}, line_color=None)

    plr_map = figure(title=f"Scatter Map - {plot_title_suffix} (Cross LR)", **map_kwargs)
    plr_map.circle(x='x', y='y', size=5, source=source_scatter_lr,
                   color={'field': 'z', 'transform': color_mapper}, line_color=None)

    color_bar = ColorBar(color_mapper=color_mapper, location=(0,0), label_standoff=12)
    p0_map.add_layout(color_bar, 'right')
    p1_map.add_layout(color_bar, 'right')
    prl_map.add_layout(color_bar, 'right')
    plr_map.add_layout(color_bar, 'right')

    # Label dinamiche in base al tipo di spettro
    x_spec_label = "Sampling Point [#]" if state.SPECTRUM_TYPE == "simple" else "Frequency [MHz]"
    title_prefix = "Spectrum" if state.SPECTRUM_TYPE == "simple" else "Average Spectrum"

    # --- 4. Creazione Figure SPETTRO ANCILLARE ---
    spec_kwargs = dict(
        x_axis_label=x_spec_label, y_axis_label="Power [Arb.]",
        width=780, height=250, 
        tools="reset,save,wheel_zoom,pan,box_zoom",
        active_scroll="wheel_zoom",
        active_drag="box_zoom"
    )

    p0_spec = figure(title=f"{title_prefix} - Pol0", **spec_kwargs)
    p0_spec.line(x='f', y='p0', source=source_spec, color="navy", line_width=2)

    p1_spec = figure(title=f"{title_prefix} - Pol1", **spec_kwargs)
    p1_spec.line(x='f', y='p1', source=source_spec, color="red", line_width=2)

    prl_spec = figure(title=f"{title_prefix} - Cross RL", **spec_kwargs)
    prl_spec.line(x='f', y='prl', source=source_spec, color="green", line_width=2)

    plr_spec = figure(title=f"{title_prefix} - Cross LR", **spec_kwargs)
    plr_spec.line(x='f', y='plr', source=source_spec, color="purple", line_width=2)
   
    # --- 5. Organizzazione in 4 TABS ---
    # Tabs per le Mappe Scatter
    map_tab0  = Panel(child=p0_map,  title="Map Pol0")
    map_tab1  = Panel(child=p1_map,  title="Map Pol1")
    map_tab_rl = Panel(child=prl_map, title="Map Cross RL")
    map_tab_lr = Panel(child=plr_map, title="Map Cross LR")
    map_tabs = Tabs(tabs=[map_tab0, map_tab1, map_tab_rl, map_tab_lr])

    # Tabs per gli Spettri Ancillari
    spec_tab0  = Panel(child=p0_spec,  title="Spec Pol0")
    spec_tab1  = Panel(child=p1_spec,  title="Spec Pol1")
    spec_tab_rl = Panel(child=prl_spec, title="Spec Cross RL")
    spec_tab_lr = Panel(child=plr_spec, title="Spec Cross LR")
    spec_tabs = Tabs(tabs=[spec_tab0, spec_tab1, spec_tab_rl, spec_tab_lr])

    # --- 6. Layout Finale ---
    final_layout = column(map_tabs, spec_tabs, spacing=30)

    # --- 7. Stato per aggiornamenti ---
    doc_state = {
        'doc': doc,
        'source_scatter_pol0': source_scatter_pol0,
        'source_scatter_pol1': source_scatter_pol1,
        'source_scatter_rl':   source_scatter_rl,
        'source_scatter_lr':   source_scatter_lr,
        'source_spec': source_spec, 
        'color_mapper_scatter': color_mapper,
        'p0_spec': p0_spec,
        'p1_spec': p1_spec,
        'prl_spec': prl_spec,
        'plr_spec': plr_spec,
        'map_tabs_dict': {
            'Pol0': map_tab0, 'Pol1': map_tab1,
            'RL': map_tab_rl, 'LR': map_tab_lr
        },
        'spec_tabs_dict': {
            'Pol0': spec_tab0, 'Pol1': spec_tab1,
            'RL': spec_tab_rl, 'LR': spec_tab_lr
        }
    }

    return final_layout, doc_state




def create_spectrum_layout(doc):
    pols = ['LL', 'RR', 'I', 'Q', 'U', 'V']
    sources = {p: ColumnDataSource(data=dict(x=[])) for p in pols}
    figs = {}
    freq_ranges = {} # <--- Aggiungiamo questo per tracciare i range

    for p in pols:
        fig = figure(
            title=f"Polarization {p}", 
            x_axis_label="Channels", y_axis_label="Counts",
            width=780, height=840,
            tools="pan,wheel_zoom,box_zoom,reset,save,hover"
        )
        
        # Creiamo un Range1d specifico per questa figura
        f_range = Range1d(start=0, end=1)
        fig.extra_x_ranges = {"freq_range": f_range}
        
        # Aggiungiamo l'asse superiore
        header_axis = LinearAxis(x_range_name="freq_range", axis_label="Frequency (MHz)")
        fig.add_layout(header_axis, "above")
        
        figs[p] = fig
        freq_ranges[p] = f_range # Salviamo il riferimento

    tabs_container = Tabs(tabs=[])

    doc_state = {
        'doc': doc,
        'sources': sources,
        'figs': figs,
        'freq_ranges': freq_ranges, # <--- Fondamentale per l'aggiornamento
        'tabs_container': tabs_container,
        'active_renderers': {p: [] for p in pols}
    }

    return tabs_container, doc_state


