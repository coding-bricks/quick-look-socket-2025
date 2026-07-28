# map_gridding.py (VERSIONE CORRETTA E COMPLETA - Generalizzata per 4 Polarizzazioni: Pol0, Pol1, RL, LR)

import numpy as np
from ichnos import state 
import math
from typing import Dict, Any, Optional

ARCSEC_TO_DEG = 1.0 / 3600.0


def _package_map_for_bokeh(Z_map: np.ndarray, X_grid: np.ndarray, Y_grid: np.ndarray) -> Dict[str, Any]:
    """Prepara il dizionario di output nel formato richiesto dal bokeh_server."""
    
    # 1. Determinazione dei limiti e delle dimensioni
    # X_grid e Y_grid hanno N+1 elementi (bordi dei bin)
    X_min, X_max = X_grid.min(), X_grid.max()
    Y_min, Y_max = Y_grid.min(), Y_grid.max()
    
    # dw e dh sono le dimensioni totali della griglia
    dw = X_max - X_min
    dh = Y_max - Y_min
    
    # 2. Inversione dell'asse Y per la visualizzazione Bokeh
    # Bokeh (ImageRenderer) si aspetta Y dal basso verso l'alto.
    # np.histogram2d crea la mappa dall'alto verso il basso, quindi la capovolgiamo.
    Z_map_flipped = np.flipud(Z_map)
    
    # 3. Determinazione del range di colore
    valid_data = Z_map_flipped[~np.isnan(Z_map_flipped)]
    if valid_data.size > 0:
        low_color = float(np.nanmin(valid_data))
        high_color = float(np.nanmax(valid_data))
    else:
        # Fallback se la mappa è vuota
        low_color, high_color = 0.0, 1.0 
        
    # 4. Impacchettamento finale
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
    Esegue la grigliatura 2D dei punti accumulati (X, Y, P) per tutte le polarizzazioni disponibili.
    """
    cache_pol0 = state.GLOBAL_MAP_CACHE.get('Pol0')
    
    # Controllo usando la chiave X della prima polarizzazione
    if cache_pol0 is None or cache_pol0['X'].size == 0: 
        print("ATTENZIONE: La cache della mappa è vuota. Nessuna grigliatura da eseguire.")
        return None

    hpbw_arcsec = state.GLOBAL_HPBW_ARCSEC
    if hpbw_arcsec <= 0:
        print("ERRORE: HPBW non è stato definito nello stato globale o è invalido.")
        return None

    grid_step_arcsec = hpbw_arcsec / 25.0
    GRID_STEP_DEG = grid_step_arcsec * ARCSEC_TO_DEG
    
    EPSILON = 1e-6 * GRID_STEP_DEG 
    
    print(f"HPBW: {hpbw_arcsec:.2f} arcsec. Passo Griglia: {GRID_STEP_DEG:.6f} gradi.")

    output_maps = {}
    
    # Rileviamo dinamicamente TUTTE le polarizzazioni presenti nella Cache Globale
    # (Gestisce Pol0, Pol1, RL, LR in automatico senza hardcoding)
    polarization_keys = [
        k for k, v in state.GLOBAL_MAP_CACHE.items() 
        if isinstance(v, dict) and 'X' in v and v['X'].size > 0
    ]
    
    print(f"Polarizzazioni da grigliare identificate: {polarization_keys}")

    # 1. Definizione dell'Area della Griglia (Comune a tutte le polarizzazioni)
    X_min_raw, X_max_raw = cache_pol0['X_min'], cache_pol0['X_max']
    Y_min_raw, Y_max_raw = cache_pol0['Y_min'], cache_pol0['Y_max']

    # Estensione dei Limiti ai Multipli del Passo
    X_min = math.floor(X_min_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    Y_min = math.floor(Y_min_raw / GRID_STEP_DEG) * GRID_STEP_DEG

    X_max = math.ceil(X_max_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    Y_max = math.ceil(Y_max_raw / GRID_STEP_DEG) * GRID_STEP_DEG
    
    # Calcolo del numero di celle
    N_X = int(round((X_max - X_min) / GRID_STEP_DEG))
    N_Y = int(round((Y_max - Y_min) / GRID_STEP_DEG))
    
    # Generazione bordi griglia
    X_grid = np.linspace(X_min, X_max, N_X + 1)
    Y_grid = np.linspace(Y_min, Y_max, N_Y + 1)
    
    print(f"DEBUG GRIGLIA: X_range=[{X_min:.6f}, {X_max:.6f}], Y_range=[{Y_min:.6f}, {Y_max:.6f}]") 
    print(f"Griglia Definita: {N_X} x {N_Y} celle. (Edges: {N_X + 1} x {N_Y + 1})")

    # 2. Iterazione e Grigliatura su ciascuna polarizzazione (Pol0, Pol1, RL, LR)
    for pol_key in polarization_keys:
        cache = state.GLOBAL_MAP_CACHE[pol_key]
        
        X_points = cache['X']
        Y_points = cache['Y']
        P_points = cache['P']
        
        # --- Grigliatura 2D (Binning) ---
        Z_sum, _, _ = np.histogram2d(
            Y_points, X_points, 
            bins=[Y_grid, X_grid], 
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
        
        # 3. Impacchettamento per Bokeh
        map_data = _package_map_for_bokeh(Z_map, X_grid, Y_grid)
        output_maps[pol_key] = map_data
        
        print(f"Mappa {pol_key} creata con shape {Z_map.shape}. Punti processati: {np.sum(N_count)}.")
        
    return output_maps