#!/usr/bin/env python3
"""Summarize a recorded take; reported UART time is NOT end-to-end latency."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def stats(values):
    values=sorted(values)
    if not values:
        return None
    return {'min':values[0],'median':statistics.median(values),
            'p95':values[round(.95*(len(values)-1))],'max':values[-1]}


def summarize(path):
    with path.open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    if not rows:
        raise ValueError('No recorded telemetry rows')
    def column(key,scale=1):
        return [float(row[key])*scale for row in rows]
    result={'file':path.name,'reports':len(rows),
            'duration_s':float(rows[-1]['elapsed_s'])-float(rows[0]['elapsed_s']),
            'samples_per_second_per_sensor':stats(column('rate')),
            'sample_cycle_gap_ms':stats(column('gap_us',.001)),
            'last_UART_write_ms':stats(column('tx_us',.001)),
            'gate_crossing_to_command_complete_ms':stats([x for x in column('onset_latency_us',.001) if x>0]),
            'commands_per_second_all_channels':stats(column('update_rate')),
            'missing_windows_counter':int(rows[-1]['missing_windows']),
            'channels':{}}
    for i,name in enumerate(['back','left','right']):
        key=f'a{i}_'
        result['channels'][name]={
            'envelope_ADC':stats(column(key+'amplitude')),
            'short_window_peak_ADC':max(column(key+'peak')),
            'requested_percent':stats(column(key+'desired')),
            'issued_percent':stats(column(key+'sent')),
            'fraction_reports_at_upper_rail':sum(float(row[key+'max'])>=1021 for row in rows)/len(rows)}
    result['limits']='25 Hz snapshots; no physical vibration measurement. The onset metric is the Uno timestamp from sampled gate crossing to completed UART write; it excludes microphone, TITAN parser and motor delays. Confirm critical latency with a logic analyzer/oscilloscope.'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(summarize(args.csv),indent=2))
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))

if __name__=='__main__':
    main()
