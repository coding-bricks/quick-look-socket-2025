# map_gridding.py (VERSIONE CORRETTA PER L'INTEGRAZIONE BOKEH - Generalizzata X/Y)

import numpy as np
from ichnos import state 
import math
from typing import Dict, Any, Optional

ARCSEC_TO_DEG = 1.0 / 3600.0

# --- Funzione di supporto per preparare l'output Bokeh ---
# Rinominata per coerenza con l'uso di X/Y al posto di RA/DEC
def _package_map_for_bokeh(Z_map, X_grid, Y_grid) -> Dict[str, Any]:
    """Prepara il dizionario di output nel formato richiesto dal bokeh_server."""
    
    # 1. Determinazione dei limiti e delle dimensioni
    # X_grid e Y_grid hanno N+1 elementi (bordi dei bin)
    X_min, X_max = X_grid.min(), X_grid.max()
    Y_min, Y_max = Y_grid.min(), Y_grid.max()
    
    # dw e dh sono le dimensioni totali della griglia (X_max - X_min)
    dw = X_max - X_min
    dh = Y_max - Y_min
    
    # 2. Inversione dell'asse Y (DEC/EL) per la visualizzazione Bokeh
    # Bokeh (ImageRenderer) si aspetta che Y (le righe) siano orientate dal basso verso l'alto.
    # np.histogram2d crea la mappa dall'alto verso il basso.
    # Capovolgiamo la mappa lungo l'asse Y (asse 0).
    Z_map_flipped = np.flipud(Z_map)
    
    # 3. Determinazione del range di colore
    valid_data = Z_map_flipped[~np.isnan(Z_map_flipped)]
    if valid_data.size > 0:
        low_color = np.nanmin(valid_data)
        high_color = np.nanmax(valid_data)
    else:
        # Fallback se la mappa � vuota
        low_color, high_color = 0, 1 
        
    # 4. Impacchettamento finale (usando X/Y come coordinate)
    return {
        'image': Z_map_flipped,
        'x': X_min,  # Punto di partenza X
        'y': Y_min,  # Punto di partenza Y
        'dw': dw,
        'dh': dh,
        'low_color': low_color,
        'high_color': high_color
    }


def perform_gridding() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Esegue la grigliatura 2D dei punti accumulati (X, Y, P) per entrambe le polarizzazioni.
    """
    cache_pol0 = state.GLOBAL_MAP_CACHE['Pol0']
    
    # Controllo usando la chiave X
    if cache_pol0['X'].size == 0: 
        print("ATTENZIONE: La cache della mappa � vuota. Nessuna grigliatura da eseguire.")
        return None

    hpbw_arcsec = state.GLOBAL_HPBW_ARCSEC
    if hpbw_arcsec <= 0:
        print("ERRORE: HPBW non � stato definito nello stato globale o � invalido.")
        return None

        
    grid_step_arcsec = hpbw_arcsec / 25.0
    GRID_STEP_DEG = grid_step_arcsec * ARCSEC_TO_DEG
    
    # ?? CORREZIONE EPSILON INSERITA QUI ??
    # Aggiungiamo un piccolissimo margine per assicurare che i punti sul bordo massimo 
    # della griglia vengano inclusi in np.histogram2d.
    EPSILON = 1e-6 * GRID_STEP_DEG 
    
    print(f"HPBW: {hpbw_arcsec:.2f} arcsec. Passo Griglia: {GRID_STEP_DEG:.6f} gradi.")

    output_maps = {}
    polarization_keys = ['Pol0', 'Pol1']
    
    # 1. Definizione dell'Area della Griglia (Comune)
    X_min_raw, X_max_raw = cache_pol0['X_min'], cache_pol0['X_max']
    Y_min_raw, Y_max_raw = cache_pol0['Y_min'], cache_pol0['Y_max']

    # ?? Soluzione Robustissima: Estensione dei Limiti ai Multipli del Passo ??
    
    # Arrotonda X/Y_min al multiplo del passo pi� vicino (verso l'interno)
    X_min = math.floor(X_min_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    Y_min = math.floor(Y_min_raw / GRID_STEP_DEG) * GRID_STEP_DEG

    # Arrotonda X/Y_max al multiplo del passo pi� vicino (verso l'esterno)
    # NON AGGIUNGIAMO QUI UN ALTRO GRID_STEP_DEG, altrimenti otterremo un bin vuoto.
    # L'arrotondamento per eccesso (ceil) � sufficiente a coprire l'ultimo punto.
    X_max = math.ceil(X_max_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    Y_max = math.ceil(Y_max_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    
    # Calcola il numero di celle (intervalli) necessarie
    # N = (Range Totale) / Passo. Utilizziamo round() per sicurezza numerica.
    N_X = int(round((X_max - X_min) / GRID_STEP_DEG))
    N_Y = int(round((Y_max - Y_min) / GRID_STEP_DEG))
    
    # Genera gli assi della griglia (N+1 bordi), garantendo che X_min e X_max 
    # siano inclusi come bordi e che il numero di passi sia N.
    X_grid = np.linspace(X_min, X_max, N_X + 1)
    Y_grid = np.linspace(Y_min, Y_max, N_Y + 1)
    
    # DEBUG AGGIORNATO
    print(f"DEBUG GRIGLIA: X_min_DISC={X_min:.6f}, X_max_DISC={X_max:.6f}, N_X_bins={N_X + 1}") 
    print(f"DEBUG GRIGLIA: Y_min_DISC={Y_min:.6f}, Y_max_DISC={Y_max:.6f}, N_Y_bins={N_Y + 1}") 
    print(f"Griglia Definita: {N_X} x {N_Y} celle. (Edges: {N_X + 1} x {N_Y + 1})")

   
    
    # 2. Iterazione e Grigliatura
    for pol_key in polarization_keys:
        cache = state.GLOBAL_MAP_CACHE[pol_key]
        
        # Leggiamo i punti X, Y, P dalla cache
        X_points = cache['X']
        Y_points = cache['Y']
        P_points = cache['P']
        
        # --- Grigliatura 2D (Binning) ---
        
        # N.B.: np.histogram2d richiede l'ordine (Y_points, X_points)
        # Calcolo della Somma delle Potenze (Z_sum) e Conteggio (N_count)
        Z_sum, _, _ = np.histogram2d(
            Y_points, X_points, # <--- Ordine Y, X
            bins=[Y_grid, X_grid], # <--- Ordine Y_grid, X_grid
            weights=P_points
        )
        
        N_count, _, _ = np.histogram2d(
            Y_points, X_points, 
            bins=[Y_grid, X_grid] 
        )
        
        # Calcolo della Media (Z_map = Z_sum / N_count)
        Z_map = np.divide(
            Z_sum, N_count, 
            out=np.full_like(Z_sum, np.nan),
            where=N_count!=0
        )
        
        # 3. Impacchettamento per Bokeh (passando i grid X/Y)
        map_data = _package_map_for_bokeh(Z_map, X_grid, Y_grid)
        output_maps[pol_key] = map_data
        
        print(f"Mappa {pol_key} creata con shape {Z_map.shape}. Punti processati: {np.sum(N_count)}.")
        
    # Restituisce il formato finale atteso da bokeh_server.update_bokeh_plot
    return output_maps