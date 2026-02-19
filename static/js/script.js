// script.js

// Function to clear the display if no match with the selected feed number
function clearData() {

    headerFilenameDisplay.textContent = 'N/A';
    sourceValueDisplay.textContent = 'N/A';
    raDisplay.textContent = 'N/A';
    decDisplay.textContent = 'N/A';
    loMHzDisplay.textContent = 'N/A';
    bwMHzDisplay.textContent = 'N/A';
    scanNumDisplay.textContent = 'N/A';
    subScanNumDisplay.textContent = 'N/A';
    channelsNumDisplay.textContent = 'N/A';
    feedNumDisplay.textContent = 'N/A'; // Clear this too
    bandDisplay.textContent = 'N/A';
    backendDisplay.textContent = 'N/A';
    signalValueDisplay.textContent = 'N/A';
    modeDisplay.textContent = 'N/A';
    fitsPlotContainer.innerHTML = '<p class="text-muted">Waiting for a FITS file to be processed...</p>';
}

// JavaScript to update the current time in the status bar
function updateCurrentTime() {
    const now = new Date();
    // Format the time (e.g., "HH:MM:SS AM/PM")
    const timeOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
    const timeString = now.toLocaleTimeString('en-US', timeOptions);

    // Format the date (e.g., "Month Day, Year")
    const dateOptions = { year: 'numeric', month: 'long', day: 'numeric' };
    const dateString = now.toLocaleDateString('en-US', dateOptions);

    // Assuming CET for your context (Sassari, Sardinia, Italy)
    document.getElementById('currentTime').textContent = `${dateString} ${timeString} CET`;
}

// Update time immediately and then every second
updateCurrentTime();
setInterval(updateCurrentTime, 1000);

// --- Socket.IO Client Logic ---
// Connect to the Socket.IO server running on the same host and port
const socket = io();
const connectionStatusSpan = document.getElementById('connectionStatus');
const sourceValueDisplay = document.getElementById('sourceValueDisplay'); // Get the element for SOURCE value
const fitsPlotContainer = document.getElementById('fitsPlotContainer'); // Re-introduce this for plot logic
const feedCombobox = document.getElementById('feedCombobox'); // Get reference to the combobox

// Global variable to store the last band used to populate the combobox
let lastPopulatedBand = null;

// =============================================
// Listener to send selected feed to the backend
// =============================================

feedCombobox.addEventListener('change', function() {
    const selectedFeed = feedCombobox.value;
    console.log(`Feed selected changed to: ${selectedFeed}. Sending to server...`);
    
    // Invia i dati al backend tramite SocketIO
    socket.emit('update_feed_selection', { feed: selectedFeed });
});


// Function to update the connection status display
function updateConnectionStatus(isConnected) {
    if (isConnected) {
        connectionStatusSpan.textContent = 'Online';
        connectionStatusSpan.classList.remove('status-offline');
        connectionStatusSpan.classList.add('status-online');
    } else {
        connectionStatusSpan.textContent = 'Offline';
        connectionStatusSpan.classList.remove('status-online');
        connectionStatusSpan.classList.add('status-offline');
    }
}

// Initial status when the page loads (before connection is established)
updateConnectionStatus(false); // Set to offline initially

// Event listener for successful connection
socket.on('connect', function() {
    console.log('Connected to Flask-SocketIO server!');
    updateConnectionStatus(true); // Update status to online
});

// Event listener for disconnection
socket.on('disconnect', function() {
    console.log('Disconnected from Flask-SocketIO server.');
    updateConnectionStatus(false); // Update status to offline
});

// Event listener for 'fits_header_update' events from the server
socket.on('fits_header_update', function(data) {
    console.log('Received fits_header_update event:', data);

    // --- Always post the header info immediately ---
    console.groupCollapsed(`New FITS Header Received for: ${data.filename}`);
    console.log('Full Data:', data);
    console.log('Filename:', data.filename);
    console.log('Header Keywords and Values:');
    for (const key in data.header) {
        if (Object.hasOwnProperty.call(data.header, key)) {
            console.log(`  ${key}: ${data.header[key]}`);
        }
    }
    console.groupEnd();

    // --- FEED FILTERING LOGIC ---
    const selectedFeed = feedCombobox.value; // Get the currently selected value from the combobox (string)
    const headerFeedString = data.feeds; // Get the FEED string from the FITS header (e.g., "[0,1]")
    const currentBand = data.header['Receiver Code'] ? data.header['Receiver Code'].toUpperCase() : null; // Get current BAND, convert to uppercase

    console.log(headerFeedString);
    console.log(currentBand);
    
    let headerFeedsArray = [];
    if (headerFeedString) {
        try {
            // Remove brackets and split by comma, then convert to numbers
            headerFeedsArray = headerFeedString
                                .replace(/[\[\]]/g, '') // Remove square brackets
                                .split(',')             // Split by comma
                                .map(s => parseInt(s.trim(), 10)) // Trim whitespace and parse as integer
                                .filter(n => !isNaN(n)); // Filter out any non-numeric results
        } catch (e) {
            console.error("Error parsing data.header.FEED string:", headerFeedString, e);
            // If parsing fails, treat it as no valid feeds, and potentially skip
            headerFeedsArray = [];
        }
    }

    // --- NEW: Populate Feed Combobox based on BAND and prevent redundant refreshes ---
    if (currentBand !== lastPopulatedBand) {
        console.log(`Band changed from '${lastPopulatedBand}' to '${currentBand}'. Repopulating feed combobox.`);
        feedCombobox.innerHTML = ''; // Clear existing options

        if (currentBand === 'KKG') {
            // Populate with 0 to 6 for KKG receiver
            for (let i = 0; i < 7; i++) {
                const option = document.createElement('option');
                option.value = i;
                option.textContent = i;
                feedCombobox.appendChild(option);
            }
            // Try to select '0' by default if it's available
            feedCombobox.value = '0';
        } else {
            // For other bands, populate with only '0'
            const option = document.createElement('option');
            option.value = '0';
            option.textContent = '0';
            feedCombobox.appendChild(option);
            feedCombobox.value = '0';
        }
        
        
        // Send the default feed value (0) after updating the backend
        socket.emit('update_feed_selection', { feed: feedCombobox.value }); // 
        
        lastPopulatedBand = currentBand; // Update the last populated band


    } else {
        console.log(`Band '${currentBand}' is the same as last time. Skipping combobox repopulation.`);
    }
    // --- END NEW: Populate Feed Combobox ---
    
    
    // --- start FILTERING LOGIC ---

    // Check if the selected feed is present in the FITS header's feed array
    // Convert selectedFeed to number for strict comparison
    // This check is valid for mono-feed or dual-feed mode (nodding)
    // For multi-feed case the check fails because the string (for example K-BAND) contains always all feeds i.e. [0,1,2,3,4,5,6]
    const selectedFeedNum = parseInt(selectedFeed, 10);

    if (headerFeedsArray.includes(selectedFeedNum)) {

        // --- 1. Aggiornamento Testi (Sempre uguale) ---
        sourceValueDisplay.textContent = data.header.SOURCE || 'N/A';
        raDisplay.textContent = data.header.RightAscension || 'N/A';
        decDisplay.textContent = data.header.Declination || 'N/A';
        loMHzDisplay.textContent = data.lo || 'N/A';
        bwMHzDisplay.textContent = data.bandwidth || 'N/A';
        scanNumDisplay.textContent = data.header.SCANID || 'N/A';
        subScanNumDisplay.textContent = data.header.SubScanID || 'N/A';
        channelsNumDisplay.textContent = data.bins || 'N/A';
        feedNumDisplay.textContent = data.feeds || 'N/A';
        bandDisplay.textContent = data.header['Receiver Code'] || 'N/A';
        backendDisplay.textContent = data.backend || 'N/A';
        signalValueDisplay.textContent = data.header.SIGNAL || 'N/A';
        modeDisplay.textContent = data.mode.toUpperCase() || 'N/A';
    
        // --- 2. Nuova Logica di Switch (Semplice e Pulita) ---
        const mapWrapper = document.getElementById('mapWrapper');
        const specWrapper = document.getElementById('specWrapper');
    
        // Determiniamo se � una mappa in base al sub_scan_type
        const isMap = (data.sub_scan_type !== 'TRACKING');
    
        if (isMap) {
            console.log('Switching to MAP view');
            mapWrapper.className = 'plot-visible';
            specWrapper.className = 'plot-hidden';
        } else {
            console.log('Switching to SPECTRUM view');
            mapWrapper.className = 'plot-hidden';
            specWrapper.className = 'plot-visible';
        }
    }

    if (headerFeedsArray.includes(selectedFeedNum)) {

        // --- Update Header Info Display ---
        //headerFilenameDisplay.textContent = data.filename || 'N/A';
        sourceValueDisplay.textContent = data.header.SOURCE || 'N/A';
        raDisplay.textContent = data.header.RightAscension || 'N/A';
        decDisplay.textContent = data.header.Declination || 'N/A';
        loMHzDisplay.textContent = data.lo || 'N/A';
        bwMHzDisplay.textContent = data.bandwidth || 'N/A';
        scanNumDisplay.textContent = data.header.SCANID || 'N/A';
        subScanNumDisplay.textContent = data.header.SubScanID || 'N/A';
        channelsNumDisplay.textContent = data.bins || 'N/A';
        feedNumDisplay.textContent = data.feeds || 'N/A';
        bandDisplay.textContent = data.header['Receiver Code'] || 'N/A';
        backendDisplay.textContent = data.backend || 'N/A';
        signalValueDisplay.textContent = data.header.SIGNAL || 'N/A';
        modeDisplay.textContent = data.mode.toUpperCase() || 'N/A';

    } else {

        console.log(`Skipping file '${data.filename}': Selected feed (${selectedFeed}) does not match any feed in header (${headerFeedString}).`);
        // Uncomment to clear the display, otherwise, leave the last data while returning
        //clearData();
        return; // Stop processing this event if no match
    }
});

/**
 * Gestione dinamica della visualizzazione Mappa/Spettro
 * Questo evento viene attivato dal backend quando cambia il tipo di file FITS
 */
 socket.on('check_mode', function(data) {
    const mapDiv = document.getElementById('mapWrapper');
    const specDiv = document.getElementById('specWrapper');

    // Verifichiamo che gli elementi esistano nel DOM per evitare errori in console
    if (mapDiv && specDiv) {
        if (data.is_map) {
            console.log("Switching UI to: MAP MODE");
            mapDiv.className = 'plot-visible';
            specDiv.className = 'plot-hidden';
        } else {
            console.log("Switching UI to: SPECTRUM MODE");
            mapDiv.className = 'plot-hidden';
            specDiv.className = 'plot-visible';
        }
    }
});

// --- GESTIONE RICONNESSIONE AUTOMATICA ---
let isInitialConnection = true; // Variabile per distinguere il primo avvio dal riavvio

socket.on('connect', function() {
    if (isInitialConnection) {
        // � la prima volta che apriamo la pagina: chiediamo solo i dati
        console.log("Connessione iniziale stabilita. Richiedo stato...");
        socket.emit('request_initial_state');
        isInitialConnection = false; 
    } else {
        // Il server era caduto ed � tornato online: rinfreschiamo per Bokeh
        console.log("Riconnessione rilevata! Refresh in corso per ripristinare i grafici...");
        window.location.reload();
    }
});
// -----------------------------------------