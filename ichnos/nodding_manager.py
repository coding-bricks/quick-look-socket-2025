import threading
import os
import re

_nodding_state = {} 
_state_lock = threading.Lock() 

# Assumiamo che SKARAB Nodding sia sempre Dual-Feed (2 files).
# Se questa logica deve supportare anche multi-feed > 2 files, 
# dobbiamo introdurre un controllo nell'header per l'expected_feed_count.
# Per ora, lo fissiamo a 2 (Dual Feed / Nodding).
EXPECTED_FEED_COUNT = 2

# Regex per estrarre l'ID di Accoppiamento e l'ID del Feed
SKARAB_NODDING_PATTERN = re.compile(r"(.+)_FEED_(\d+)\.fits$", re.IGNORECASE)

# Vecchio Pattern (catturava tutto, incluso il timestamp, nel Gruppo 1)
# Non funziona perché il time-stamp può variare anche se di 1 solo secondo (vedi dati )
# SKARAB_NODDING_PATTERN = re.compile(r"(.+)_FEED_(\d+)\.fits$", re.IGNORECASE)

# Nuovo Pattern (cattura SOLO la parte dopo il timestamp nel Gruppo 1)
# ^\d{8}-\d{6}-: Cattura e scarta l'inizio (es. 20241024-150917-)
# (.+): Cattura la parte stabile (es. S0000-W3OH_001_005). Questo sar� match.group(1)
# _FEED_(\d+)\.fits$: Cattura il Feed ID (Gruppo 2)
# SKARAB_NODDING_PATTERN = re.compile(r"^\d{8}-\d{6}-(.+)_FEED_(\d+)\.fits$", re.IGNORECASE)





def check_and_pair_skarab_nodding(filepath):
    """
    Controlla se il file appartiene a un'osservazione SKARAB a Feed Multipli.
    Se la lista dei file per quell'osservazione raggiunge la dimensione EXPECTED_FEED_COUNT,
    restituisce tutti i percorsi e pulisce lo stato.
    
    Returns:
        tuple or None: (filepath_1, filepath_2) se i file sono accoppiati, altrimenti None.
    """
    filename = os.path.basename(filepath)
    match = SKARAB_NODDING_PATTERN.search(filename)
    
    if not match:
        # Non � un file SKARAB con il pattern FEED_#, non gestito da questo manager
        return None 
        
    base_id = match.group(1) # L'ID di Osservazione (chiave di accoppiamento)
    feed_index = int(match.group(2)) # L'indice del Feed (non usato per la logica di accoppiamento, solo per debug)
    
    with _state_lock:
        
        # Inizializza la lista se l'ID di Osservazione � nuovo
        if base_id not in _nodding_state:
            _nodding_state[base_id] = []

        # 1. Controlla che il file non sia gi� stato registrato (utile per on_modified)
        if filepath in _nodding_state[base_id]:
            print(f"NODDING MANAGER: {filename} gi� registrato. Ignorato l'evento duplicato.")
            return None

        # 2. Aggiungi il file alla lista dei file associati
        _nodding_state[base_id].append(filepath)
        print(f"NODDING MANAGER: {filename} registrato (Feed: {feed_index}). Stato attuale per {base_id}: {len(_nodding_state[base_id])}/{EXPECTED_FEED_COUNT}")
        
        # 3. Verifica se l'accoppiamento � completo
        if len(_nodding_state[base_id]) == EXPECTED_FEED_COUNT:
            
            # Accoppiamento completato. Recupera i file.
            coupled_files = tuple(_nodding_state[base_id])
            
            # Pulisci lo stato
            del _nodding_state[base_id]
            
            print(f"NODDING MANAGER: Accoppiamento completato per {base_id}. Pronti i file: {', '.join(os.path.basename(f) for f in coupled_files)}")
            return coupled_files # Restituisce una tupla (file_A, file_B)
        
        else:
            # In attesa del partner
            return None # Non pronto per l'elaborazione