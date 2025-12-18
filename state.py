# state.py

import numpy as np
from typing import Dict, Any, Optional

# --------------------------------------------------------
# 1. STATO RELATIVO AL FRONTEND
# --------------------------------------------------------
# Global variable to store the feed selected by the user on the front-end
CURRENT_SELECTED_FEED = 0


# --------------------------------------------------------
# 1.1 STATO RELATIVO AL SUBSCAN
# --------------------------------------------------------
# Global variable to store the current subscan of the FITS file
LAST_PROCESSED_SUBSCAN_ID = 0

# --------------------------------------------------------
# 1.2 SCATTER MODE
# --------------------------------------------------------
# Global variable to switch between map type
# True: scatter plot
# False grid plot with steps in X e Y
USE_SCATTER_MODE = True




# --------------------------------------------------------
# 2. STATO RELATIVO ALLA MAPPA (La Nuvola di Punti Persistente)
# --------------------------------------------------------

# Struttura dati per memorizzare i dati grezzi (RA, DEC, P) e i limiti globali
# La cache viene inizializzata in stato VUOTO.
GLOBAL_MAP_CACHE: Dict = {}

# NUOVA VARIABILE: Memorizza l'HPBW (in secondi d'arco) calcolato da FITS_processor.py.
# Questo � l'input cruciale per map_gridding.py.
GLOBAL_HPBW_ARCSEC: float = 0.0


# ====================================================================
# STATO GLOBALE PER LA GRIGLIATURA DELLA MAPPA IN TEMPO REALE
# ====================================================================

# Dictionary che conterr� le nuvole di punti (X, Y, P) accumulate.
# NOTA: X/Y sono generici (RA/DEC o AZ/EL).
GLOBAL_MAP_CACHE: Dict[str, Dict[str, Any]] = {}

# Valore HPBW (Half Power Beam Width) in arcsec, usato per definire il passo della griglia.
GLOBAL_HPBW_ARCSEC: float = 0.0


def initialize_map_cache():
    """
    Inizializza la struttura dati per le due polarizzazioni (Pol0 e Pol1).
    Questa funzione viene chiamata all'avvio e ogni volta che il sistema
    passa dalla modalit� Mappa a Spettro e viceversa.
    """
    global GLOBAL_MAP_CACHE
    
    # La cache � strutturata per contenere i punti e i limiti
    # per ciascuna polarizzazione gestita (almeno Pol0 e Pol1)
    GLOBAL_MAP_CACHE = {
        'Pol0': {
            'X': np.array([]),       # Punti X accumulati (RA o AZ)
            'Y': np.array([]),       # Punti Y accumulati (DEC o EL)
            'P': np.array([]),       # Potenza P_i accumulata
            'X_min': np.inf,         # Limite minimo X globale
            'X_max': -np.inf,        # Limite massimo X globale
            'Y_min': np.inf,         # Limite minimo Y globale
            'Y_max': -np.inf,        # Limite massimo Y globale
        },
        'Pol1': {
            'X': np.array([]),
            'Y': np.array([]),
            'P': np.array([]),
            'X_min': np.inf,
            'X_max': -np.inf,
            'Y_min': np.inf,
            'Y_max': -np.inf,
        },
    }
    
    print("? Cache Mappa Globale (X/Y) inizializzata con successo.")
    
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