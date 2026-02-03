#!/bin/bash

SOURCE_DIR="/roach2_nuraghe/data/26-23/20250611/20250611-091934-26-23-W3OH" # nodding with SARDARA
#SOURCE_DIR="/home02/fabio.schirru/skarab/20241024/ps/20241024-150844-S0000-W3OH" # position switching SKARAB
DEST_DIR="/home02/fabio.schirru/github/quick-look_2025_socket/fits_files"

echo "Monitoring started. Copy every 5 seconds..."
  
while true; do
    for file in "$SOURCE_DIR"/*.fits; do
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
