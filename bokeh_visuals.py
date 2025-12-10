import os
import numpy as np
import state
import time

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
    filename_prefix, final_averages, x, feeds_for_legend, spectrum_type, x_axis_label_val, start_time_total):
    
    start_time_bokeh_build = time.time()
    
    try:
        # Inizializzazione figures
        if spectrum_type == 'stokes':
            p0 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [STOKES]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=500, tools="pan,wheel_zoom,box_zoom,reset")
            figures = [p0]
        else:
            p1 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [LEFT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")
            p2 = figure(title=f"SKARAB Nodding: {filename_prefix} - POL [RIGHT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")
            figures = [p1, p2]


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
        p1 = figure(title=f"File: {filename_prefix} - POL [LEFT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")
        p2 = figure(title=f"File: {filename_prefix} - POL [RIGHT]", x_axis_label=x_axis_label_val, y_axis_label='Counts', width=740, height=250, tools="pan,wheel_zoom,box_zoom,reset")

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
        if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
            final_plot_layout = column(p1, p2, spacing = 20)
        else:
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
    Crea il layout iniziale della mappa 2D di Bokeh con due pannelli (Pol0, Pol1)
    e inizializza i ColumnDataSource per gli aggiornamenti dinamici.

    Parametri:
    - doc: Il documento Bokeh corrente (curdoc()).

    Ritorna:
    - Tuple: (layout finale (tipo Any), dizionario contenente i riferimenti ai DataSource)
    """

    # --- 1. Definizione di Stili e Mappe Colore ---
    
    # Range iniziale dei colori (verr� aggiornato dinamicamente dal Worker B)
    # Range arbitrario iniziale, ad esempio [0, 100]
    color_mapper = LinearColorMapper(palette=Magma256, low=0, high=100)

    # --- 2. Inizializzazione dei ColumnDataSource ---
    
    # Dati iniziali VUOTI: usiamo un array 1x1 con un valore NaN come placeholder
    empty_map_data = np.full((1, 1), np.nan, dtype=np.float32)
    
    initial_source_data = {
        # La matrice 2D (deve essere in una lista per l'ImageRenderer)
        'image': [empty_map_data], 
        # Coordinate e dimensioni (valori placeholder)
        'x': [0.0],
        'y': [0.0],
        'dw': [1.0],
        'dh': [1.0],
    }

    source_pol0 = ColumnDataSource(data=initial_source_data)
    source_pol1 = ColumnDataSource(data=initial_source_data)
    
    # --- 3. Creazione delle Figure (p0 e p1) ---

    # --- Figura Pol0 ---
    p0 = figure(
        title="Polarizzazione 0 (Pol0)",
        x_axis_label="X (RA/EL)",
        y_axis_label="Y (DEC/AZ)",
        active_scroll="wheel_zoom",
        width=600, height=500
    )

    p0.image(
        image='image',
        x='x', y='y', dw='dw', dh='dh',
        source=source_pol0,
        color_mapper=color_mapper,
        # La colorbar � unica e collegata al color_mapper
    )
    
    # Aggiunge la ColorBar
    color_bar = ColorBar(color_mapper=color_mapper, label_standoff=12, 
                         border_line_color=None, location=(0, 0))
    p0.add_layout(color_bar, 'right')


    # --- Figura Pol1 ---
    # Usiamo lo stesso ColorMapper
    p1 = figure(
        title="Polarizzazione 1 (Pol1)",
        x_axis_label="X (RA/EL)",
        y_axis_label="Y (DEC/AZ)",
        active_scroll="wheel_zoom",
        width=600, height=500
    )

    p1.image(
        image='image',
        x='x', y='y', dw='dw', dh='dh',
        source=source_pol1,
        color_mapper=color_mapper,
    )
    
    # Aggiungiamo la ColorBar anche a P1 per consistenza (o la si omette per P1)
    p1.add_layout(color_bar, 'right')


    # --- 4. Creazione del Layout Finale con Tabs e Column ---
    
    # Crea i pannelli (Tabs)
    tab0 = Panel(child=p0, title="Pol0")
    tab1 = Panel(child=p1, title="Pol1")
    map_tabs = Tabs(tabs=[tab0, tab1])
    
    # Usa 'column' per definire il layout principale che sar� la root del documento
    final_layout = column(map_tabs)
    
    # --- 5. Ritorno dello Stato per l'Aggiornamento ---
    
    # Questo � il dizionario che verr� salvato in state.BOKEH_DOC_STATE
    doc_state = {
        'doc': doc,
        'source_pol0': source_pol0,
        'source_pol1': source_pol1,
        'color_mapper': color_mapper 
    }
    
    return final_layout, doc_state

