# state.py

import numpy as np
from typing import Dict, Any, Optional

# --------------------------------------------------------
# 1. STATO RELATIVO AL FRONTEND
# --------------------------------------------------------
# Global variable to store the feed selected by the user on the front-end
CURRENT_SELECTED_FEED = 0

# --------------------------------------------------------
# 2. STATO RELATIVO ALLA MAPPA (La Nuvola di Punti Persistente)
# --------------------------------------------------------

# Struttura dati per memorizzare i dati grezzi (RA, DEC, P) e i limiti globali
# La cache viene inizializzata in stato VUOTO.
GLOBAL_MAP_CACHE: Dict = {}

# NUOVA VARIABILE: Memorizza l'HPBW (in secondi d'arco) calcolato da FITS_processor.py.
# Questo � l'input cruciale per map_gridding.py.
GLOBAL_HPBW_ARCSEC: float = 0.0

def initialize_map_cache():
    """Inizializza/Reset la struttura della cache della mappa per le polarizzazioni Pol0 e Pol1."""
    global GLOBAL_MAP_CACHE
    global GLOBAL_HPBW_ARCSEC # Importante: dichiara che stai modificando la globale
    
    # Inizializza gli array
    GLOBAL_MAP_CACHE = {
        'Pol0': { 
            'RA': np.array([]), 'DEC': np.array([]), 'P': np.array([]),            
            'RA_min': float('inf'), 'RA_max': float('-inf'),
            'DEC_min': float('inf'), 'DEC_max': float('-inf')
        },
        'Pol1': { 
            'RA': np.array([]), 'DEC': np.array([]), 'P': np.array([]),
            'RA_min': float('inf'), 'RA_max': float('-inf'),
            'DEC_min': float('inf'), 'DEC_max': float('-inf')
        }
    }
    
    # Reset del valore HPBW (se passi dalla Mappa allo Spettro, questo valore � da ricalcolare)
    GLOBAL_HPBW_ARCSEC = 0.0 

# Inizializza la cache all'avvio del modulo
initialize_map_cache()

# --------------------------------------------------------
# 3. STATO RELATIVO AL BOKEH SERVER (Nuova Sezione)
# --------------------------------------------------------

# Memorizza i riferimenti al documento Bokeh (doc) e ai suoi ColumnDataSource.
# Inizializzato a None. Viene popolato *dopo* l'avvio del server.
BOKEH_DOC_STATE: Optional[Dict[str, Any]] = None