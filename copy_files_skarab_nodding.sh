#!/bin/bash

# Destination directory
destination="/home02/fabio.schirru/github/quick-look_2025_socket/fits_files/"

# Skarab Nodding files
skarab_nodding_files=(

   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122038-S0000-W3OH_001_002_FEED_0.fits"  
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122038-S0000-W3OH_001_002_FEED_1.fits"  
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122048-S0000-W3OH_001_003_FEED_0.fits"  
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122048-S0000-W3OH_001_003_FEED_1.fits"  
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122100-S0000-W3OH_001_004_FEED_0.fits"   
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122100-S0000-W3OH_001_004_FEED_1.fits"  
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122110-S0000-W3OH_001_005_FEED_0.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122110-S0000-W3OH_001_005_FEED_1.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122123-S0000-W3OH_001_006_FEED_0.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122123-S0000-W3OH_001_006_FEED_1.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122133-S0000-W3OH_001_007_FEED_0.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122133-S0000-W3OH_001_007_FEED_1.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122144-S0000-W3OH_001_008_FEED_0.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122144-S0000-W3OH_001_008_FEED_1.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122155-S0000-W3OH_001_009_FEED_0.fits"
   "/home02/fabio.schirru/skarab/29102024/nod/20241029-122038-S0000-W3OH/20241029-122155-S0000-W3OH_001_009_FEED_1.fits"
)


for ((i=0; i<${#skarab_nodding_files[@]}; i+=2)); do
    file1="${skarab_nodding_files[$i]}"
    file2="${skarab_nodding_files[$i+1]}"

    echo $file1

    echo "Copio il primo file della coppia: $file1"
    cp "$file1" "$destination"/

    # Ritardo simulato per il secondo file
    if [[ -n "$file2" ]]; then
        echo "Attendo 0.5 secondi prima del secondo file..."
        sleep 0.5

        echo "Copio il secondo file della coppia: $file2"
        cp "$file2" "$destination"/
    fi

    # Ritardo di 30 secondi tra coppie
    if (( i + 2 < ${#skarab_nodding_files[@]} )); then
        echo "Coppia completata. Attendo 30 secondi..."
        sleep 10
    fi
done
