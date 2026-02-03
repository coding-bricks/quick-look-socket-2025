# state.py

import numpy as np
from typing import Dict, Any, Optional

# --------------------------------------------------------
# 1. FRONTEND-RELATED STATE
# --------------------------------------------------------
# Global variable storing the feed currently selected by the user
# on the frontend interface
CURRENT_SELECTED_FEED = 0


# --------------------------------------------------------
# 1.1 SUBSCAN STATE
# --------------------------------------------------------
# Global variable storing the ID of the last processed subscan
# from the FITS file
LAST_PROCESSED_SUBSCAN_ID = 0

# --------------------------------------------------------
# 1.2 SCATTER MODE
# --------------------------------------------------------
# Global flag used to switch between map visualization modes
# True  -> scatter plot
# False -> grid plot with fixed steps in X and Y
USE_SCATTER_MODE = True


# --------------------------------------------------------
# 2. MAP-RELATED STATE (Persistent Point Cloud)
# --------------------------------------------------------

# Data structure used to store raw map data (RA, DEC, P)
# together with their global limits.
# The cache is initialized in an EMPTY state.
GLOBAL_MAP_CACHE: Dict = {}

# Global variable storing the HPBW (Half Power Beam Width) in arcseconds
# computed by FITS_processor.py.
# This value is a critical input for map_gridding.py.
GLOBAL_HPBW_ARCSEC: float = 0.0


# ====================================================================
# GLOBAL STATE FOR REAL-TIME MAP GRIDDING
# ====================================================================

# Dictionary containing the accumulated point clouds (X, Y, P).
# NOTE: X and Y are generic coordinates (e.g. RA/DEC or AZ/EL).
GLOBAL_MAP_CACHE: Dict[str, Dict[str, Any]] = {}

# HPBW (Half Power Beam Width) value in arcseconds,
# used to define the grid step size.
GLOBAL_HPBW_ARCSEC: float = 0.0


def initialize_map_cache():
    """
    Initialize the data structure for the two polarizations (Pol0 and Pol1).

    This function is called at startup and every time the system
    switches between Map mode and Spectrum mode.
    """
    global GLOBAL_MAP_CACHE
    
    # The cache is structured to store accumulated points and
    # global coordinate limits for each supported polarization
    # (at least Pol0 and Pol1)
    GLOBAL_MAP_CACHE = {
        'Pol0': {
            'X': np.array([]),       # Accumulated X coordinates (RA or AZ)
            'Y': np.array([]),       # Accumulated Y coordinates (DEC or EL)
            'P': np.array([]),       # Accumulated power values P_i
            'X_min': np.inf,         # Global minimum X value
            'X_max': -np.inf,        # Global maximum X value
            'Y_min': np.inf,         # Global minimum Y value
            'Y_max': -np.inf,        # Global maximum Y value
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
    
    print("? Global map cache (X/Y) successfully initialized.")
    
    # Reset the HPBW value.
    # When switching from Map mode to Spectrum mode,
    # this value must be recomputed.
    GLOBAL_HPBW_ARCSEC = 0.0 


# Initialize the map cache when the module is loaded
initialize_map_cache()

# --------------------------------------------------------
# 3. BOKEH SERVER STATE
# --------------------------------------------------------

# Stores references to the Bokeh document (doc) and its
# associated ColumnDataSource objects.
# Initialized to None and populated *after* the server starts.
BOKEH_DOC_STATE: Optional[Dict[str, Any]] = None