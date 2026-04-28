#!/bin/bash

#SOURCE_DIR="/roach2_nuraghe/data/26-23/20250611/20250611-091934-26-23-W3OH" # nodding with SARDARA
#SOURCE_DIR="/home02/fabio.schirru/skarab/20241024/ps/20241024-150844-S0000-W3OH" # position switching SKARAB
SOURCE_DIR="/roach2_nuraghe/data/2-25/20250314/20250314-130043-2-25-SUN_RA_K18" # sun map
#SOURCE_DIR="/home02/fabio.schirru/data/20250722/20250722-103755-KBAND-3C84AZ" # test gain-curve with map shifts

DEST_DIR="/home02/fabio.schirru/github/quick-look_2025_socket/fits_files"

FILE_EXT="fits0"     # <-- change this value accordingly to the case


echo "Monitoring started. Copy every 5 seconds..."
  
while true; do
    for file in "$SOURCE_DIR"/*.${FILE_EXT}; do
        [ -e "$file" ] || continue   # Nessun file .fits

        basefile=$(basename "$file")

        # ? Salta i file che iniziano con 'Sum_'
        if [[ $basefile == Sum_* ]]; then
            continue
        fi

        destfile="$DEST_DIR/$basefile"

        # Perform copy ONLY if the file doe s not exist or it is newer
        if [ ! -e "$destfile" ] || [ "$file" -nt "$destfile" ]; then
            cp "$file" "$destfile"
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Copiato: $basefile"

            # Pause of 5 seconds ONLY after a copy has been performed
            sleep 5
        fi
    done
done
