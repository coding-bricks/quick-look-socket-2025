# fits_processor.py

import os
import time
import numpy as np # For generating dummy plot data
from astropy.io import fits
from flask_socketio import SocketIO
from bokeh.plotting import figure, column, show # Import Bokeh plotting tools
from bokeh.resources import CDN # For CDN resources (JS/CSS)
from bokeh.palettes import Category10

from bokeh.embed import file_html # For saving plot to HTML

# Global variable for SocketIO instance
_socketio_instance = None

# Define the directory for saving plots within static
# Ensure this directory exists relative to app.py
PLOT_SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'plots')

# Create the plots directory if it doesn't exist
if not os.path.exists(PLOT_SAVE_DIR):
    os.makedirs(PLOT_SAVE_DIR)
    print(f"Created Bokeh plots directory: {PLOT_SAVE_DIR}")

def set_socketio_instance_for_processor(sio):
    """
    Sets the SocketIO instance that will be used to emit events to clients
    from the FITS processor. Called by fits_watcher.py.
    """
    global _socketio_instance
    _socketio_instance = sio
    print("SocketIO instance passed to fits_processor.py")

def _wait_for_file_completion(filepath, timeout=300, check_interval=0.5, stable_checks=3):
    """
    Robustly waits for a file to stop growing in size, indicating it has
    been completely written to disk. This is crucial for handling files
    that are being actively transferred or generated, preventing premature
    attempts to read incomplete files.
    Adjusted default 'timeout' for better handling of network latency.

    Args:
        filepath (str): The full path to the file to monitor.
        timeout (int): The maximum number of seconds (float) to wait before giving up.
                       Increased default to 300 seconds (5 minutes) for network drives.
        check_interval (float): The time (in seconds) to pause between file size checks.
        stable_checks (int): The number of consecutive times the file size must remain
                             unchanged before considering it "stable" (fully written).

    Returns:
        bool: True if the file became stable within the timeout, False otherwise.
    """
    print(f"Waiting for {os.path.basename(filepath)} to be completely written...")
    start_time = time.time()
    last_size = -1 # Initialize with an invalid size to ensure first check updates it
    stable_count = 0 # Counter for consecutive stable size checks

    while True:
        # Check if timeout has been reached
        if time.time() - start_time > timeout:
            print(f"Timeout waiting for {os.path.basename(filepath)} to complete. Last recorded size: {last_size} bytes.")
            return False

        # Check if the file still exists (it might be moved or deleted during waiting)
        if not os.path.exists(filepath):
            print(f"File {os.path.basename(filepath)} disappeared while waiting.")
            return False

        try:
            current_size = os.path.getsize(filepath)
        except OSError as e:
            # Handle cases where the file might be temporarily locked or inaccessible
            print(f"Warning: Could not get size of {os.path.basename(filepath)}: {e}. Retrying in {check_interval}s...")
            time.sleep(check_interval)
            continue # Skip to the next iteration

        if current_size == last_size:
            # File size is stable, increment counter
            stable_count += 1
            if stable_count >= stable_checks:
                # File has been stable for enough checks, consider it complete
                print(f"File {os.path.basename(filepath)} appears stable at {current_size} bytes.")
                return True
        else:
            # File size has changed, reset stable counter and update last size
            stable_count = 0
            last_size = current_size

        time.sleep(check_interval) # Wait before checking again


def create_and_save_bokeh_plot(filepath, filename_prefix, filename_extension, feeds, chs, spectrum_type, backend):

    # Use the backend value to extract data correctly and perform calculations on each backend

    """
    Creates the Bokeh plot from the recorded data and saves it
    as an HTML file in the static/plots directory.

    Args:
        filepath (str): A string containing the full FITS filename.
        feeds (list): A list containing the feed used during the data acquisition (i.e. [0,1])

    Returns:
        str: The Flask-accessible URL to the saved Bokeh plot HTML file,
             or None if an error occurred.
    """

    # 1 - Extract Data and computes the averages through multiple raws (single spectra) of the FITS file
    # 2 - Save Data

    # According to the filename_extension [.fits, .fits#] we need to extrapolate data in a different way
    # If the extension is '.fits', this correpsonds to the case mono-feed or nodding observation
    # The logic to extract data for type 'spectra' or 'stokes' is the same
    # However data relative to each pol type is separated in different columns [LCP, RCP] for 'spectra' type otherwise 'stokes' type are all in the same Ch data column
    
    data = [] # generic
    averages = [] # used to compute averages along each raw of data
    data_points = [] # used to get data points when each row contains a single value (e.i. TotalPawer case)
    try:

        # Open the FITS file. 'with' statement ensures the file is closed properly.
        with fits.open(filepath) as hdul:

            # case .fits file i.e. case mono-feed or dual-feed (nodding)
            # case .fits are TotalPower, SARDARA (excluding multi-feed) and SKARAB
            if(filename_extension == '.fits'):
                
                # Extract the number of rows in the SECTION TABLE
                # For SARDARA case this is equal to the number of columns of channel data
                # chs =  len(hdul["SECTION TABLE"].data)
                # print('Sections', chs) # chs, for 'spectra' type is the number of feeds x 2 (because the pol LCP and RCP are separated into dfferent data columns)

                # Contrary to SARDARA (dual, multi-feed), SKARAB has Ch0 and Ch1 columns name ALWAYS even if the feed is 2,3,4,5,6,7 ect. 
                # We can not use a generic loop through the feed numbers. So we process data differently by backend type

                if(backend != 'SKARAB'): # case SARDARA and TotalPower

                    for i in range(len(feeds)):

                        # case type 'spectra' or 'simple' (TotalPower). The Data Table contains data columns separated per feed and per polarization (LCP, RCP)
                        if(spectrum_type == 'spectra' or spectrum_type == 'simple'):

                            index = feeds[i]*2
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                            index = (feeds[i]*2)+1
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))

                        else:
                            # case type 'stokes'. The Data Table contains data columns separated per feed but all polarizations are together (L, R, LL, RR)
                            data.append(np.array(hdul["DATA TABLE"].data[f"Ch{feeds[i]}"]))
                
                else:
                    # Ch0 and Ch1 are fixed column names for the SKARAB backend 
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch0"])) 
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch1"]))

            else: # case .fits# i.e. multi-feed (SARDARA only)

                # For the multi-feed case,  each fits file deals with a specific feed
                # for the 'spectra' case the fits file will have two columns for LCP and RCP polarization
                # In this case we need to retrieve the proper column index
                # for the 'stokes' case the fits file will have one column of data with all polarization included (L, R, LL, RR)
                # In this case the column index is equal to the extracted feed number

                # Retrieve the feed number from the extension itself
                feed_number = filename_extension.removeprefix('.fits')

                # case type 'spectra'. The Data Table contains data columns separated per feed and per polarization (LCP, RCP)
                if(spectrum_type == 'spectra'):

                    index = int(feed_number)*2
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))
                    index = (int(feed_number)*2)+1
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{index}"]))

                else:  # case type 'stokes'. The Data Table contains data columns separated per feed but all polarizations are together (L, R, LL, RR)
                
                    data.append(np.array(hdul["DATA TABLE"].data[f"Ch{int(feed_number)}"]))
                
                    
        # For TOTAL-POWER backend, data are single points per row
        # For SARDARA backend, data are, for example, 1024 channels per raw
        # We need to calculate the average respect to the raws
        # For the SARDARA case, each individual channel is averaged with itself through all the rows

           
        # Loop through each element in the array
        if(type(data[0][0]) == np.ndarray):

            for i in range(len(data)):

                averages.append([float(sum(group) / len(group)) for group in zip(*data[i])])
            
            # Create the x-axis values
            x = np.linspace(0, len(averages[0]), len(averages[0]))
            x_axis_label_val = 'Channel'
        
        else:
           
            # This corresponds to the case of the TotalPower backend
            # There is no need to calculate the average since each row contains a value only and not multiple bins
            # Instead, for TotalPower the plot will display the value contained in each raw as a function of time
            for i in range(len(data)):
                
                # avg = []
                # Calculate the average [case TOTAL POWER]
                # avg = sum(data[i]) / len(data[i])
                # avg = data[i]
                # Store the average in array averages
                # averages.append([avg])
                averages.append(data[i])

            # Create the x-axis values
            x = np.linspace(0, len(averages[0]), len(averages[0]))
            x_axis_label_val = 'Sampling Point [#]'


    except Exception as e:
        
        print(f"Error creating/saving Bokeh plot for {filepath}: {e}")
        return None

    
    # Averages data are used to generate the Bokeh plot
    # Averages data is an array of m raws (corresponding to the number of column Ch{i} and n columns corresponding to the number of bins (single data column rows))

    # Create a new plot with a title and axis labels
    # p0 used as a single plot for type=stokes
    # p1, p2 used for spectra plots. 

    p0 = figure(
        title=f"File: {filename_prefix} - POL [STOKES]",
        x_axis_label=x_axis_label_val,
        y_axis_label='Counts',
        width=740, height=500,
        tools="pan,wheel_zoom,box_zoom,reset"
    )

    p1 = figure(
        title=f"File: {filename_prefix} - POL [LEFT]",
        x_axis_label=x_axis_label_val,
        y_axis_label='Counts',
        width=740, height=250,
        tools="pan,wheel_zoom,box_zoom,reset"
    )

    p2 = figure(
        title=f"File: {filename_prefix} - POL [RIGHT]",
        x_axis_label=x_axis_label_val,
        y_axis_label='Counts',
        width=740, height=250,
        tools="pan,wheel_zoom,box_zoom,reset"
    )

    # Add a line renderer with a legend and color
    # Define line colors
    
    n = len(averages)

    if n in Category10:
        
        colors = Category10[n]  # A palette with 4 distinct colors), case nodding
    
    elif n in (1, 2):
        
        # [:n] ensures you only take what you need (1 or 2 colors)
        colors = ["#1f77b4", "#ff7f0e"][:n]  # First 2 from Category10[3], case mono-feed or multi-feed with data relative to one feed only
    
    # Add each dataset as a line to the plot
    #for i, data in enumerate(averages):
    #    p.line(x, data, legend_label=f"Feed-{feeds[i]} LEFT", line_width=2, color=colors[i])
    #    p.line(x, data, legend_label=f"Feed-{feeds[i+1]} RIGHT", line_width=2, color=colors[i+1])
    #    i = i + 1

    # Draw plot
    # case .fits file i.e. case mono-feed or dual-feed (nodding)
    if(filename_extension == '.fits'):

        f = 0 # index relative to the feed number in the 'feeds' list

        # case type 'spectra'. The Data Table contains data columns separated per feed and per polarization (LCP, RCP)
        if(spectrum_type == 'spectra'):

            for i in range(0, len(averages), 2):
                p1.line(x, averages[i], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i])
                p2.line(x, averages[i+1], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i+1])
                f+=1
                    
        elif(spectrum_type == 'stokes'):  # case type 'stokes'. The Data Table contains data columns separated per feed but all polarizations are together (L, R, LL, RR)
            
            for i in range(0, len(averages), 1):        
                p0.line(x, averages[i], legend_label=f"Feed-{feeds[f]}", line_width=2, color=colors[i])
                f+=1

        elif(spectrum_type == 'simple'):  # case type 'simple'. Data are related to the TotalPower with one column and n rows for polarization LL and RR

            # Get the feed value for the TotalPower. It must be 0
            feed = feeds[0]

            for i in range(0, len(averages), 1): 
                p1.line(x, averages[0], legend_label=f"Feed-{feed}", line_width=2, color=colors[0])
                p2.line(x, averages[1], legend_label=f"Feed-{feed}", line_width=2, color=colors[1])       
               
    else: # i.e. multi-feed (.fits0,....). In this case only one feed at time is displayed [TotalPower can not be multi-feed!]

        # case type 'spectra'. The Data Table contains data columns separated per feed and per polarization (LCP, RCP)
        if(spectrum_type == 'spectra'):

            p1.line(x, averages[0], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[0])
            p2.line(x, averages[1], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[1])
    
        else:  # case type 'stokes'. The Data Table contains data columns separated per feed but all polarizations are together (L, R, LL, RR)
    
            p0.line(x, averages[0], legend_label=f"Feed-{feed_number}", line_width=2, color=colors[0])

    # Configure the legend to be interactive:
    # "hide" will hide the glyph when clicked.
    # "mute" will make the glyph transparent when clicked.
    p0.legend.click_policy = "hide"
    p1.legend.click_policy = "hide"
    p2.legend.click_policy = "hide"

    # You might also want to customize legend location/orientation
    # p.legend.location = "top_left"
    # p.legend.orientation = "horizontal"

    # Arrange the subplots in a column layout
    # You can use `row(p1, p2)` for horizontal layout
    # Or `gridplot([[p1], [p2]])` for more complex grids
    if(spectrum_type == 'spectra' or spectrum_type == 'simple'):
        
        final_plot_layout = column(p1, p2, spacing = 20)

    else:

        final_plot_layout = column(p0)

    # Construct the full path and URL for the HTML file
    # Generate a unique ID using the current timestamp in milliseconds.
    # This is appended to the filename to ensure browser caching doesn't
    # serve an old version of the plot if the content changes but the base name is the same.
    unique_id = int(time.time() * 1000)
    plot_html_filename = f"{filename_prefix}_{unique_id}_plot.html"

    full_plot_path = os.path.join(PLOT_SAVE_DIR, plot_html_filename)
    # The URL for Flask's static files
    plot_static_url = f"/static/plots/{plot_html_filename}"

    # Save the plot to an HTML file
    # CDN resources mean the JS/CSS libraries are loaded from a network
    # rather than being embedded directly in the HTML, making the file smaller.
    with open(full_plot_path, "w") as f:
        f.write(file_html(final_plot_layout, CDN, title=f"FITS Data Plot: {filename_prefix}"))

    print(f"Bokeh plot saved to: {full_plot_path}")
    return plot_static_url

    #except Exception as e:
    #
    #    print(f"Error creating/saving Bokeh plot for {filename_prefix}: {e}")
    #    return None

    

def process_fits_file(filepath):
    """
    Manages the processing of a detected .fits file.
    It first waits for the file to be fully written, then attempts to
    extract its primary header, generates a plot, and emits both
    to the frontend via SocketIO. This function is called by fits_watcher.py.
    """
    # Wait for the file to become stable (fully written)
    if not _wait_for_file_completion(filepath):
        print(f"Skipping processing of {os.path.basename(filepath)}: File did not stabilize or disappeared.")
        return

    try:
        with fits.open(filepath) as hdul:
            primary_header = hdul[0].header
            print(f"\n--- Primary Header Keywords and Values for {os.path.basename(filepath)} ---")

            header_data = {
                "filename": os.path.basename(filepath),
                "filename_extension": os.path.splitext(os.path.basename(filepath))[1],
                "header": {}
            }

            for keyword, value in primary_header.items():
                if keyword not in ['COMMENT', 'HISTORY']:
                    print(f"{keyword}: {value}")
                    header_data["header"][keyword] = str(value)

            print("--------------------------------------------------\n")

            # --- Add extra keywords
            for sec in hdul["SECTION TABLE"].data:
                if(sec["id"] == 0):
                    header_data["bins"] =  str(sec["bins"])
                    header_data["bandwidth"] =  str(sec["bandwidth"])
            
            for rf in hdul["RF INPUTS"].data:
                if(rf["section"] == 0):
                    header_data["frequency"] = str(rf["frequency"])
                    header_data["lo"] =  str(rf["localOscillator"])

            # Extract the number of used feeds and create a string
            feeds = hdul["RF INPUTS"].data["feed"] 

            unique_values = sorted(set(feeds))
            feeds_str = "[" + ",".join(str(x) for x in unique_values) + "]"

            header_data["feeds"] = str(feeds_str)

            # Get the type of spectra ('spectra' or 'stoke') and the number of channels per spectra per polarization
            # In case of type 'Spectra' polarization can be LCP or RCP each spectrum of channels given by(sec["bins"]
            # In case of type 'Stokes' polarization ar L, R, LL, RR in the same spectrum with channels given by(sec["bins"] x 4
            chs = hdul["SECTION TABLE"].data["bins"][0]
            spectrum_type = hdul["SECTION TABLE"].data["type"][0]

            # Get the type of backend used (i.e. TotalPower, SARDARA, SKARAB)
            # To recognize the TotalPower backend it is enough to check that the number of bins (i.e. chs) is equal to 1
            if(chs == 1):

                header_data["backend"] = "TotalPower"
            
            else:
                # from "load_subscans" first index is the item number in the list, second index the value [0]=file name, [1] signal flag, [2]=time
                if("FEED_" in str(filepath)):
                    header_data["backend"] = "SKARAB"
                else:
                    header_data["backend"] = "SARDARA"

        backend = header_data["backend"]
        filename_base = os.path.splitext(os.path.basename(filepath))[0]
        filename_extension = os.path.splitext(os.path.basename(filepath))[1]

        # --- Get data and generate the Bokeh plot ---
        # plot_url = create_and_save_bokeh_plot___(filepath)
        plot_url = create_and_save_bokeh_plot(filepath, filename_base, filename_extension, unique_values, chs, spectrum_type, backend)

        if plot_url:
            header_data["plot_url"] = plot_url
            print(f"Plot URL added to data: {plot_url}")
        else:
            print("No plot URL generated for this FITS file.")


        if _socketio_instance:
            print(f"Emitting FITS header and plot URL for {os.path.basename(filepath)} to frontend.")
            _socketio_instance.start_background_task(
                _socketio_instance.emit, 'fits_header_update', header_data
            )
        else:
            print("Warning: SocketIO instance not set in fits_processor.py, cannot emit header data.")

    except Exception as e:

        print(f"Error processing FITS file {os.path.basename(filepath)}: {e}")



