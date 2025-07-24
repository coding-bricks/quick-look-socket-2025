#!/bin/bash

# Test File Description
# Project ID: ?, Band: KKG, Feed: MONO[ps], Type: SPECTRA, Backend: SKARAB, Test: PASSED
# Project ID: KBAND/20250611/20250611-194346-KBAND-SKYDIP_KBAND, Band: KKG, Feed: MULTI, Type: STOKES, Backend: SARDARA, Test: PASSED
# Project ID: KBAND/20250303/20250303-164424-KBAND-SKYDIP_KBAND, Band: KKG, Feed: MULTI, Type: SPECTRA, Backend: SARDARA, Test: PASSED
# Project ID: 26-23/20250611/20250611-091934-26-23-W3OH, Band: KKG, Feed: DUAL, Type: SPECTRA, Backend: SARDARA, Test: PASSED
# Project ID: CHBAND/20250421/20250421-000454-CHBAND-3C295_CH, Band CCB, Feed: MONO, Type: SPECTRA, Backend: SARDARA, Test: PASSED
# Project ID: 10-25/20250715/20250715-123304-10-25-3C84_SPIDER, Band: CCG, Feed: MONO, Type: STOKES, Backend: SARDARA, Test: PASSED  
# Project ID: 8-25/20250422/20250422-070756-8-25-3C84_CS, Band: KKG, Feed: MULTI, Type: STOKES, Backend: SARDARA, Test: PASSED
# Project ID: ?, Band: KKG, Feed: DUAL[nod], Type: SPECTRA, Backend: SKARAB, Test: PASSED
# TotalPower Test (local folder: /home02/fabio.schirru/data/32-24/20250207)[no access to TotalPower data disk]
# Project ID: 32-24/20250207-091145-32-24-3C286_Clow, Band: CCG, Feed: MONO, Type: SIMPLE, Test: PASSED
# Project ID: ?, Band: KKG, Feed: DUAL[nod], Type: SPECTRA, Backend: SKARAB, Test: PASSED

# List of source file paths
files=(
    "/home02/fabio.schirru/skarab/20241024/ps/20241024-150844-S0000-W3OH/20241024-150917-S0000-W3OH_001_005_FEED_0.fits"
    "/roach2_nuraghe/data/KBAND/20250611/20250611-194346-KBAND-SKYDIP_KBAND/20250611-194420-KBAND-SKYDIP_KBAND_001_006.fits0"
    "/roach2_nuraghe/data/KBAND/20250303/20250303-164424-KBAND-SKYDIP_KBAND/20250303-164519-KBAND-SKYDIP_KBAND_001_007.fits0"
    "/roach2_nuraghe/data/26-23/20250611/20250611-091934-26-23-W3OH/20250611-092210-26-23-W3OH_001_016.fits"
    "/roach2_nuraghe/data/CHBAND/20250421/20250421-000454-CHBAND-3C295_CH/20250421-000644-CHBAND-3C295_CH_006_007.fits"
    "/roach2_nuraghe/data/10-25/20250715/20250715-123304-10-25-3C84_SPIDER/20250715-123304-10-25-3C84_SPIDER_001_001.fits"
    "/roach2_nuraghe/data/8-25/20250422/20250422-070756-8-25-3C84_CS/20250422-071026-8-25-3C84_CS_061_011.fits0"
    "/home02/fabio.schirru/skarab/20241024/nod/20241024-152511-S0000-W3OH/20241024-152607-S0000-W3OH_001_007_FEED_0.fits"
    "/home02/fabio.schirru/data/32-24/20250207/20250207-091145-32-24-3C286_Clow/20250207-091508-32-24-3C286_Clow_002_011.fits"
    "/home02/fabio.schirru/skarab/20241024/nod/20241024-152511-S0000-W3OH/20241024-152607-S0000-W3OH_001_007_FEED_0.fits"
    )

# Destination directory
destination="/home02/fabio.schirru/github/quick-look_2025_socket/fits_files/"

# Copy each file every 10 seconds
for file in "${files[@]}"; do
  echo "Copying $file to $destination"
  cp "$file" "$destination"
  echo "Waiting 8 seconds before next copy..."
  sleep 8
done

echo "All files copied."
