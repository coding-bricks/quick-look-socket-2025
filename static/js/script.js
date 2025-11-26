
// script.js

// Function to clear the display if no match with the selected feed number
function clearData() {

    headerFilenameDisplay.textContent = 'N/A';
    sourceValueDisplay.textContent = 'N/A';
    raRadDisplay.textContent = 'N/A';
    decRadDisplay.textContent = 'N/A';
    loMHzDisplay.textContent = 'N/A';
    bwMHzDisplay.textContent = 'N/A';
    scanNumDisplay.textContent = 'N/A';
    subScanNumDisplay.textContent = 'N/A';
    channelsNumDisplay.textContent = 'N/A';
    feedNumDisplay.textContent = 'N/A'; // Clear this too
    bandDisplay.textContent = 'N/A';
    backendDisplay.textContent = 'N/A';
    signalValueDisplay.textContent = 'N/A';
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
        lastPopulatedBand = currentBand; // Update the last populated band
    } else {
        console.log(`Band '${currentBand}' is the same as last time. Skipping combobox repopulation.`);
    }
    // --- END NEW: Populate Feed Combobox ---
    

    // Check if the selected feed is present in the FITS header's feed array
    // Convert selectedFeed to number for strict comparison
    // This check is valid for mono-feed or dual-feed mode (nodding)
    // For multi-feed case the check fails because the string (for example K-BAND) contains always all feeds i.e. [0,1,2,3,4,5,6]
    const selectedFeedNum = parseInt(selectedFeed, 10);

    if (headerFeedsArray.length > 1) { // there is no need to treat the mono case since data will be displayed anyway!

	console.log(`Backend '${data.backend}'`);
	console.log(headerFeedsArray.length)

	// Manage the special case of SARDARA dual-feed (nodding)
	if(data.backend == 'SARDARA' && headerFeedsArray.length == 2) {

	   if (isNaN(selectedFeedNum) || !headerFeedsArray.includes(selectedFeedNum)) {
	       console.log(`Skipping file '${data.filename}': Selected feed (${selectedFeed}) does not match any feed in header (${headerFeedString}).`);
	       // Uncomment to clear the display, otherwise, leave the last data while returning
	       //clearData();
	       return; // Stop processing this event if no match
	    }

	}  

	// The feed number can be retrieved:
	// 1) from the extension .fit# for SARDARA
	// 2) from the filename FEED_#_ for SKARAB
	// Retrieve the feed number

	let extracted_feed = ""
	
	if(data.backend == 'SARDARA' && headerFeedsArray.length > 2) {
	    
	    extracted_feed = parseInt( data.filename_extension.replace('.fits', ''), 10);
	    //console.log(`Retrieved feed from extension ('${extracted_feed}').`);
	   	    
	}

	if(data.backend == 'SKARAB' ) {

	    // Use regex to extract the number between 'FEED_' and '.fits'
	    const match = data.filename.match(/FEED_(\d+)\.fits$/);

	    if (match) {
		extracted_feed =  match[1];
		console.log("Extracted number:", extracted_feed);
	    } else {
		console.log("Pattern not found.");
	    }
        }

        if(selectedFeedNum != extracted_feed ){
	    // Uncomment to clear the display, otherwise, leave the last data while returning
	    //clearData();
	    console.log(`Skipping file '${data.filename}': Selected feed ('${selectedFeed}') does not match the extracted feed from file extension ('${extracted_feed}').`);
	    return; // Stop processing this event if no match
	}
    }
    
    // --- END FEED FILTERING LOGIC ---


    // --- Update Header Info Display ---
    //headerFilenameDisplay.textContent = data.filename || 'N/A';
    sourceValueDisplay.textContent = data.header.SOURCE || 'N/A';
    raRadDisplay.textContent = data.header.RightAscension || 'N/A';
    decRadDisplay.textContent = data.header.Declination || 'N/A';
    loMHzDisplay.textContent = data.lo || 'N/A';
    bwMHzDisplay.textContent = data.bandwidth || 'N/A';
    scanNumDisplay.textContent = data.header.SCANID || 'N/A';
    subScanNumDisplay.textContent = data.header.SubScanID || 'N/A';
    channelsNumDisplay.textContent = data.bins || 'N/A';
    feedNumDisplay.textContent = data.feeds || 'N/A';
    bandDisplay.textContent = data.header['Receiver Code'] || 'N/A';
    backendDisplay.textContent = data.backend || 'N/A';
    signalValueDisplay.textContent = data.header.SIGNAL || 'N/A';

     // --- Add Bokeh plot display logic ---
    if (data.plot_url) {
        console.log('Plot URL received:', data.plot_url);
        // Clear previous plot and create a new iframe for the new plot
        fitsPlotContainer.innerHTML = ''; // Clear existing content (e.g., "Waiting for...")
        const iframe = document.createElement('iframe');
        iframe.src = data.plot_url;
        // Make iframe explicitly block to allow margin: auto to work
        iframe.style.display = 'block';
        // Set width and height
        iframe.style.width = '96%'; // Use 90% to leave space for centering
        iframe.style.height = '560px'; // Adjust height as needed
        // Remove border
        iframe.style.border = '0';
        iframe.style.borderRadius = '8px';
        iframe.setAttribute('frameborder', '0'); // Remove default iframe border
        // Explicitly center horizontally using auto margins
        iframe.style.margin = '0 auto';

        // Append the iframe. It will load asynchronously.
        fitsPlotContainer.appendChild(iframe);
        console.log('Iframe appended to container. Plot should now be loading.');

        // Optional: rudimentary load/error handling for debugging
        iframe.onload = () => console.log('Bokeh iframe loaded successfully.');
        iframe.onerror = () => console.error('Error loading Bokeh iframe:', data.plot_url);

    } else {
        fitsPlotContainer.innerHTML = '<p class="text-muted">No plot available for this FITS file.</p>';
        console.log('No plot URL provided in the received data.');
    } 

  
});

