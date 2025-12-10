# map_gridding.py

import numpy as np
import state # Per accedere a GLOBAL_MAP_CACHE e GLOBAL_HPBW_ARCSEC
import math

from typing import Dict, Tuple

# Costante per conversione: 1 secondo d'arco = 1/3600 gradi
ARCSEC_TO_DEG = 1.0 / 3600.0

def perform_gridding() -> Dict[str, np.ndarray]:
    """
    Esegue la grigliatura 2D dei punti accumulati per entrambe le polarizzazioni 
    (Pol0 e Pol1) utilizzando la media spaziale (binning).

    La dimensione della cella della griglia � definita dinamicamente come HPBW / 2.

    Ritorna:
    - Dict[str, np.ndarray]: Un dizionario contenente le mappe grigliate (Z_Pol0, Z_Pol1) 
      e gli assi della griglia (RA_grid, DEC_grid).
    """
    
    # 1. Controllo Preliminare e Recupero HPBW
    cache_pol0 = state.GLOBAL_MAP_CACHE['Pol0']
    
    if cache_pol0['RA'].size == 0:
        print("ATTENZIONE: La cache della mappa � vuota. Nessuna grigliatura da eseguire.")
        return {}

    hpbw_arcsec = state.GLOBAL_HPBW_ARCSEC
    if hpbw_arcsec <= 0:
        print("ERRORE: HPBW non � stato definito nello stato globale o � invalido.")
        return {}
        
    # Calcolo del Passo della Griglia Ottimale (HPBW / 2) in gradi
    grid_step_arcsec = hpbw_arcsec / 2.0
    GRID_STEP_DEG = grid_step_arcsec * ARCSEC_TO_DEG
    
    print(f"HPBW: {hpbw_arcsec:.2f} arcsec. Passo Griglia: {GRID_STEP_DEG:.6f} gradi.")

    output_maps = {}
    polarization_keys = ['Pol0', 'Pol1']

    # 2. Definizione dell'Area della Griglia (Comune a entrambe le polarizzazioni)
    # Gli estremi del mosaico sono dati dai limiti globali accumulati
    RA_min, RA_max = cache_pol0['RA_min'], cache_pol0['RA_max']
    DEC_min, DEC_max = cache_pol0['DEC_min'], cache_pol0['DEC_max']

    # Crea gli assi della griglia: np.arange include il minimo ed esclude il massimo
    # Aggiungiamo GRID_STEP_DEG per assicurarci di includere l'estremo massimo
    RA_grid = np.arange(RA_min, RA_max + GRID_STEP_DEG, GRID_STEP_DEG)
    DEC_grid = np.arange(DEC_min, DEC_max + GRID_STEP_DEG, GRID_STEP_DEG)

    output_maps['RA_grid'] = RA_grid
    output_maps['DEC_grid'] = DEC_grid
    print(f"Griglia Definita: {len(RA_grid)} x {len(DEC_grid)} celle.")

    # 3. Iterazione e Grigliatura per ciascuna Polarizzazione
    for pol_key in polarization_keys:
        cache = state.GLOBAL_MAP_CACHE[pol_key]
        
        RA_points = cache['RA']
        DEC_points = cache['DEC']
        P_points = cache['P']
        
        # --- Grigliatura 2D (Binning) ---
        
        # 3.1. Calcolo della Somma delle Potenze (Z_sum)
        # N.B.: np.histogram2d richiede gli assi (Y, X) quindi (DEC, RA)
        Z_sum, _, _ = np.histogram2d(
            DEC_points, RA_points, 
            bins=[DEC_grid, RA_grid], 
            weights=P_points
        )
        
        # 3.2. Calcolo del Conteggio dei Punti (N_count)
        N_count, _, _ = np.histogram2d(
            DEC_points, RA_points, 
            bins=[DEC_grid, RA_grid] 
        )
        
        # 3.3. Calcolo della Media (Z_map = Z_sum / N_count)
        # np.divide gestisce la divisione per zero (se N_count=0, imposta a NaN), 
        # lasciando i buchi (punti non campionati) nella mappa.
        Z_map = np.divide(
            Z_sum, N_count, 
            out=np.full_like(Z_sum, np.nan), # Se N_count=0, il risultato � NaN
            where=N_count!=0
        )
        
        print(f"Mappa {pol_key} creata con shape {Z_map.shape}. Punti mediati: {np.sum(N_count)}.")
        output_maps[f'Z_{pol_key}'] = Z_map
    
    # 4. Interpolazione/Riempimento Buco (Hole Filling) - Logicabile qui in seguito.

    return output_maps