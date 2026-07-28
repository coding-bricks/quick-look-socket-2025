# state.py
import numpy as np
import time
from typing import Dict, Any, Optional

# ----------------------------------------------------------------------
# 1. GENERAL & FRONTEND STATE
# ----------------------------------------------------------------------
# Indice del feed selezionato dall'utente nell'interfaccia (es. 0, 1, 2...)
CURRENT_SELECTED_FEED = 0

# Flag globale per Flask/Jinja2: decide quale script Bokeh iniettare nell'HTML
# True  -> Carica l'app /map_viewer
# False -> Carica l'app /spectrum_monitor
IS_MAP = True

# Flag per il tipo di visualizzazione della mappa (Nuvola di punti vs Griglia)
USE_SCATTER_MODE = True

# Sistema di coordinate corrente per il puntamento (RADEC o AZEL)
CURRENT_COORD_SYSTEM: str = "AZEL"

# spectrum type used to switch X-AXIS labels ('spectra' vs 'stokes')
SPECTRUM_TYPE = "spectra" # by default

# Variables used to reset the x-axis ranges
CURRENT_SCHEDULE = None   # Memorizza l'ultima sorgente elaborata
IS_NEW_DATASET = False  # Il flag che Bokeh "ascolterà"

# --------------------------------------------------------
# 1.1 SUBSCAN STATE
# --------------------------------------------------------
# Global variable storing the ID of the last processed subscan
# from the FITS file
LAST_PROCESSED_SUBSCAN_ID = 0


# ----------------------------------------------------------------------
# 2. MAP DATA CACHE (Persistent Point Cloud - 4 POLARIZZAZIONI)
# ----------------------------------------------------------------------
# Dizionario che accumula i dati grezzi (X, Y, Potenza) durante le scansioni.
# Esteso a 4 polarizzazioni statiche: Pol0 (RR/L), Pol1 (LL/R), RL, LR.
GLOBAL_MAP_CACHE: Dict[str, Dict[str, Any]] = {}

# Valore del fascio calcolato (Half Power Beam Width) in arcosecondi.
GLOBAL_HPBW_ARCSEC: float = 0.0

def initialize_map_cache():
    """Inizializza o svuota la cache delle mappe per tutte le 4 polarizzazioni."""
    global GLOBAL_MAP_CACHE, GLOBAL_HPBW_ARCSEC
    
    empty_pol_structure = lambda: {
        'X': np.array([]), 'Y': np.array([]), 'P': np.array([]),
        'X_min': np.inf,   'X_max': -np.inf,
        'Y_min': np.inf,   'Y_max': -np.inf,
    }
    
    GLOBAL_MAP_CACHE = {
        'Pol0': empty_pol_structure(),
        'Pol1': empty_pol_structure(),
        'RL':   empty_pol_structure(),
        'LR':   empty_pol_structure(),
    }
    GLOBAL_HPBW_ARCSEC = 0.0
    print("✔ Cache mappe (4 Pol) e HPBW inizializzati correttamente.")


# ----------------------------------------------------------------------
# 2.1 NUOVI BUFFER ASINCRONI PER AGGIORNAMENTO MAPPE (MULTI-UTENTE)
# ----------------------------------------------------------------------
# "Cassetta delle lettere" dove il Worker B deposita le mappe grigliate appena calcolate
LATEST_MAP_RESULTS: Dict[str, Dict[str, Any]] = {}

# Campanello per le tab: aggiornato con time.time() dal Worker B per segnalare nuovi dati
LAST_MAP_TIMESTAMP: float = 0.0

# Buffer che accumula lo storico dei punti dello scatter plot per le 4 polarizzazioni
CURRENT_SCATTER_DATA: Dict[str, Dict[str, list]] = {
    'Pol0': {'x': [], 'y': [], 'z': []},
    'Pol1': {'x': [], 'y': [], 'z': []},
    'RL':   {'x': [], 'y': [], 'z': []},
    'LR':   {'x': [], 'y': [], 'z': []},
}


# ----------------------------------------------------------------------
# 3. SPECTRUM DATA (Real-Time Monitor & Ancillary Spectrum)
# ----------------------------------------------------------------------
# Questo dizionario è il "ponte" tra il Processor e l'app Bokeh dello spettro.
CURRENT_SPEC = {
    'x': np.array([]),       # Asse X: canali (es. 0..65535) o frequenze relative
    'averages': [],          # Lista di ndarray con i valori di potenza
    'f_min': 0.0,            # Frequenza minima per l'asse superiore (MHz)
    'f_max': 0.0,            # Frequenza massima per l'asse superiore (MHz)
    'filename': "",          # Nome del file FITS in elaborazione
    'num_feeds': 1,          # Numero di feed rilevati nel file
    'spectrum_type': "",     # Tipo di dato: 'spectra' (2 Pol), 'stokes' (4 Pol)
    'updated': False         # SEMAFORO: True quando il processor ha finito di scrivere i dati
}

# Variabili storiche per gli spettri ancillari (estese a 4 polarizzazioni)
LAST_SPECTRUM_X = np.array([])
LAST_SPECTRUM_POL0 = np.array([])
LAST_SPECTRUM_POL1 = np.array([])
LAST_SPECTRUM_RL   = np.array([])
LAST_SPECTRUM_LR   = np.array([])
SPECTRUM_UPDATED = False 


# ----------------------------------------------------------------------
# 4. BOKEH SERVER INTERNALS (Object References)
# ----------------------------------------------------------------------
BOKEH_DOC_STATE: Optional[Dict[str, Any]] = None
SPEC_DOC_STATE: Optional[Dict[str, Any]] = None


# ----------------------------------------------------------------------
# 5. SOCKETIO RECOVERY STATE
# ----------------------------------------------------------------------
LAST_FULL_DATA_PACKET: Optional[Dict[str, Any]] = None