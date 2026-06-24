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

# spectrum type used to switch X-AXIS labels
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
# 2. MAP DATA CACHE (Persistent Point Cloud)
# ----------------------------------------------------------------------
# Dizionario che accumula i dati grezzi (X, Y, Potenza) durante le scansioni.
# Serve per mantenere i punti precedenti mentre ne arrivano di nuovi.
GLOBAL_MAP_CACHE: Dict[str, Dict[str, Any]] = {}

# Valore del fascio calcolato (Half Power Beam Width) in arcosecondi.
# Fondamentale per determinare la risoluzione della griglia nelle mappe.
GLOBAL_HPBW_ARCSEC: float = 0.0

def initialize_map_cache():
    """Inizializza o svuota la cache delle mappe per Pol0 e Pol1."""
    global GLOBAL_MAP_CACHE, GLOBAL_HPBW_ARCSEC
    GLOBAL_MAP_CACHE = {
        'Pol0': {
            'X': np.array([]), 'Y': np.array([]), 'P': np.array([]),
            'X_min': np.inf,   'X_max': -np.inf,
            'Y_min': np.inf,   'Y_max': -np.inf,
        },
        'Pol1': {
            'X': np.array([]), 'Y': np.array([]), 'P': np.array([]),
            'X_min': np.inf,   'X_max': -np.inf,
            'Y_min': np.inf,   'Y_max': -np.inf,
        },
    }
    GLOBAL_HPBW_ARCSEC = 0.0
    print("✔ Cache mappe e HPBW inizializzati correttamente.")


# ----------------------------------------------------------------------
# 2.1 NUOVI BUFFER ASINCRONI PER AGGIORNAMENTO MAPPE (MULTI-UTENTE)
# ----------------------------------------------------------------------
# "Cassetta delle lettere" dove il Worker B deposita le mappe grigliate appena calcolate
LATEST_MAP_RESULTS: Dict[str, Dict[str, Any]] = {}

# Campanello per le tab: aggiornato con time.time() dal Worker B per segnalare nuovi dati
LAST_MAP_TIMESTAMP: float = 0.0

# Buffer che accumula lo storico dei punti dello scatter plot per Pol0 e Pol1,
# evitando che le tab perdano o duplichino punti durante lo streaming asincrono
CURRENT_SCATTER_DATA: Dict[str, Dict[str, list]] = {
    'Pol0': {'x': [], 'y': [], 'z': []},
    'Pol1': {'x': [], 'y': [], 'z': []}
}


# ----------------------------------------------------------------------
# 3. SPECTRUM DATA (Real-Time Monitor)
# ----------------------------------------------------------------------
# Questo dizionario è il "ponte" tra il Processor e l'app Bokeh dello spettro.
CURRENT_SPEC = {
    'x': np.array([]),       # Asse X: canali (es. 0..65535) o frequenze relative
    'averages': [],          # Lista di ndarray con i valori di potenza (uno per linea/feed)
    'f_min': 0.0,            # Frequenza minima per l'asse superiore (MHz)
    'f_max': 0.0,            # Frequenza massima per l'asse superiore (MHz)
    'filename': "",          # Nome del file FITS in elaborazione (per il titolo del plot)
    'num_feeds': 1,          # Numero di feed rilevati nel file (per i colori e la legenda)
    'spectrum_type': "",     # Tipo di dato: 'spectra' (LL, RR), 'stokes' (I,Q,U,V), 'simple'
    'updated': False         # SEMAFORO: True quando il processor ha finito di scrivere i dati
}

# Variabili storiche (usate anche dallo scatter plot ancillare)
LAST_SPECTRUM_X = np.array([])
LAST_SPECTRUM_POL0 = np.array([])
LAST_SPECTRUM_POL1 = np.array([])
SPECTRUM_UPDATED = False 


# ----------------------------------------------------------------------
# 4. BOKEH SERVER INTERNALS (Object References)
# ----------------------------------------------------------------------
# ATTENZIONE: Questi oggetti NON sono dati, ma i riferimenti ai componenti
# live di Bokeh (Documenti, Sorgenti, Layout). Permettono l'aggiornamento push.
# NOTA MULTI-UTENTE: Punteranno all'ultima sessione attiva, ma l'architettura
# ora preferisce l'uso del doc.doc_state isolato per singola tab.

# Stato per l'app /map_viewer
BOKEH_DOC_STATE: Optional[Dict[str, Any]] = None

# Stato per l'app /spectrum_monitor
SPEC_DOC_STATE: Optional[Dict[str, Any]] = None


# Inizializzazione automatica all'import del modulo
# initialize_map_cache()


# ----------------------------------------------------------------------
# 5. SOCKETIO RECOVERY STATE
# ----------------------------------------------------------------------
# Memorizza l'ultimo pacchetto dati inviato via SocketIO per i nuovi client
LAST_FULL_DATA_PACKET: Optional[Dict[str, Any]] = None