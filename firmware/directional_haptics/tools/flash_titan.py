#!/usr/bin/env python3
"""Back up TITAN, fetch the pinned official image, flash and verify it.

Run with the Uno->TITAN RXD wire disconnected and TITAN in ROM download mode.
Backups stay local because a complete ESP32 flash may contain device settings.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def fetch_image():
    info=json.loads((ROOT/'titan/manifest.json').read_text())
    cache=ROOT/'.cache';cache.mkdir(exist_ok=True)
    path=cache/'TITAN_CORE_DK_VH2.1.bin'
    if not path.exists():
        with urllib.request.urlopen(info['url'],timeout=30) as response:
            data=response.read(info['size']+1)
        if len(data)!=info['size'] or hashlib.sha256(data).hexdigest()!=info['sha256']:
            raise RuntimeError('Official image differs from the reviewed manifest; nothing flashed')
        path.write_bytes(data)
    data=path.read_bytes()
    if len(data)!=info['size'] or hashlib.sha256(data).hexdigest()!=info['sha256']:
        raise RuntimeError('Cached image failed verification; nothing flashed')
    return path,info

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--download-only',action='store_true')
    args=parser.parse_args()
    image,info=fetch_image()
    if args.download_only:
        print(image);return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=ROOT/'backups'/stamp;folder.mkdir(parents=True)
    base=[sys.executable,'-m','esptool','--chip','esp32','--port',args.port,'--baud','460800']
    # 'ALL' obtains the detected flash size rather than assuming a 4 MB module.
    backup=folder/'titan-before.bin'
    subprocess.run(base+['--after','no_reset','read_flash','0','ALL',str(backup)],check=True)
    if backup.stat().st_size<image.stat().st_size+4096:
        raise RuntimeError('Backup/flash size unexpectedly small; nothing flashed')
    record={'created_utc':stamp,'port':args.port,'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'vendor_image':info}
    (folder/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    subprocess.run(base+['--before','no_reset','--after','no_reset','write_flash',info['offset'],str(image)],check=True)
    subprocess.run(base+['--before','no_reset','--after','no_reset','verify_flash',info['offset'],str(image)],check=True)
    print('Verified flash. Disconnect USB power, remove the temporary IO0-to-GND wire, then power TITAN on with its mode jumper removed.')
    print('Local recovery backup:',backup)

if __name__=='__main__':main()
