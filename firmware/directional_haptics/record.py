#!/usr/bin/env python3
"""Own the USB port once; record all accepted windows and serve that same feed.

python record.py --serial /dev/cu.usbserial-210 --port 8766
The server binds to 127.0.0.1 only. Recording starts automatically.
"""
import argparse
from collections import deque
import csv
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import threading
import time
from urllib.parse import urlparse

import serial
from protocol import Decoder

ROOT = Path(__file__).resolve().parent
NAMES = ['Back · SparkFun ENVELOPE', 'Left · SparkFun ENVELOPE', 'Right · SparkFun ENVELOPE']
CHANNEL_FIELDS = ['raw','min','max','mean','amplitude','peak','normalized','smoothed','desired','sent','floor','reference','close','p2p','rail']
CSV_FIELDS = ['host_utc', 'elapsed_s', 'seq', 'device_ms', 'window_us', 'rate',
              'gap_us','tx_us','onset_latency_us','update_rate','dropped','samples','stream_epoch','missing_windows','flags','phase','progress','profile','ceiling','command_sequence'] + [
              f'a{i}_{key}' for i in range(3) for key in CHANNEL_FIELDS]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class Recorder:
    def __init__(self, directory, serial_port):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.serial_port = serial_port
        self.lock = threading.RLock()
        self.clients = set()
        self.history = deque(maxlen=750)
        self.latest = None
        self.last_frame_at = None
        self.reconnect_requested = threading.Event()
        self.session = None
        self.files = []
        self.active = False
        self.rows = 0
        self.invalid = 0
        self.missing = 0
        self.epoch = 0
        self.previous_seq = None
        self.status = 'Opening Arduino USB'
        self.error = None
        self.events = []
        self.base = None
        self.quiet = None
        self.pending = None
        self.command_id = 0
        self.last_ack = None
        self.settings = None
        self.last_flush = time.monotonic()
        self.start()

    def info(self):
        age = None if self.last_frame_at is None else time.monotonic()-self.last_frame_at
        live = age is not None and age < 2.5
        status = self.status
        if not live and status == 'Arduino connected · live':
            status = 'Arduino data stopped · use Reconnect USB if needed'
        return dict(active=self.active, name=self.session.name if self.session else None,
                    rows=self.rows, elapsed_s=round(time.monotonic()-self.started, 3),
                    status=status, live=live, data_age_s=age,
                    error=self.error, invalid_rows=self.invalid,
                    missing_windows=self.missing, baseline=self.base,
                    quiet_progress=None if self.quiet is None else
                    min(1, (time.monotonic()-self.quiet['at'])/3),
                    events=self.events[-20:], firmware=self.latest, pending=self.pending, last_ack=self.last_ack, settings=self.settings)

    def publish(self, message):
        # Slow viewers drop display packets; disk capture is independent.
        for client in tuple(self.clients):
            try:
                client.put_nowait(message)
            except queue.Full:
                try:
                    client.get_nowait()
                    client.put_nowait(message)
                except (queue.Empty, queue.Full):
                    pass

    def event(self, kind, label):
        item = dict(type=kind, label=label, host_utc=utc_now(),
                    elapsed_s=round(time.monotonic()-self.started, 3),
                    device_ms=self.latest['device_ms'] if self.latest else None,
                    seq=self.latest['seq'] if self.latest else None)
        self.events.append(item)
        self.events = self.events[-1000:]
        if self.active:
            self.event_file.write(json.dumps(item)+'\n')
            self.event_file.flush()
        return item

    def stop(self):
        with self.lock:
            if self.active:
                self.event('stop', 'Recording stopped')
                self.active = False
                self.quiet = None
                for file in self.files:
                    file.close()
                self.files = []

    def start(self):
        with self.lock:
            self.stop()
            self.started = time.monotonic()
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.session = self.directory / ('take-'+stamp)
            self.session.mkdir()
            self.rows = 0
            self.events = []
            self.history.clear()
            self.base = None
            self.quiet = None
            self.error = None
            self.csv_file = (self.session/'readings.csv').open('w', newline='')
            self.json_file = (self.session/'readings.jsonl').open('w')
            self.raw_file = (self.session/'serial.log').open('w')
            self.event_file = (self.session/'events.jsonl').open('w')
            self.files = [self.csv_file, self.json_file, self.raw_file, self.event_file]
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDS)
            self.csv_writer.writeheader()
            self.active = True
            metadata = dict(version='3.0.0', protocol='DH v3 CRC16', started_utc=utc_now(),
                            serial_port=self.serial_port, baud=115200,
                            pins=dict(zip(['A0', 'A1', 'A2'], NAMES)),
                            sensor_profile='three-sparkfun-envelopes', amplitude_fields=['mean','mean','mean'],
                            positions={'A0':'back','A1':'left','A2':'right'},
                            motor_variants={'A0':'white HF, 160 Hz','A1':'red LF, 95 Hz','A2':'yellow MF, 130 Hz'},
                            full_scale_adc=970, telemetry_ms=40, processing_target_ms=5, adc_reference='DEFAULT, nominal 5 V',
                            adc_settling='One discarded conversion per channel switch',
                            clock='host elapsed_s is monotonic USB receipt time; device_ms is window report time',
                            units='ADC counts / Q4; normalized and motor levels in percent; not SPL',
                            actuation='A1 -> L, A2 -> R, A0 -> M. Stock VH finite effects; qualified setup required',
                            settings_at_start=self.settings,
                            recording_scope='25 Hz snapshots, not every ADC sample or every motor command; settings changes are in events.jsonl')
            (self.session/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
            self.event('start', 'New comparison take')
            if self.settings:
                self.event('settings',json.dumps(self.settings,separators=(',',':')))
            self.publish(dict(type='reset', state=self.info()))
            print(f'Recording: {self.session}', flush=True)

    def mark(self, label):
        with self.lock:
            if not self.active:
                raise ValueError('Start a take before adding an event')
            return self.event('marker', label or 'Event')

    def send_command(self, name, value=0):
        allowed = {'HELLO':{0},'QUIET':{0},'REFERENCE':{0},'SAVE':{0},'MUTE':{0},'RESUME':{0},'CANCEL':{0},
                   'SENSITIVITY':range(1,6),'CONTRAST':range(31),'PROFILE':{0,20,21},'PROBE':{0},'TEST':{1,2,3,4},'QUALIFY':{1},'CEILING':range(101),
                   'TRIM0':range(25,101),'TRIM1':range(25,101),'TRIM2':range(25,101)}
        if not isinstance(name,str) or name not in allowed or type(value) is not int or value not in allowed[name]:
            raise ValueError('Unknown command or out-of-range value')
        if not self.info()['live']:
            raise ValueError('Wait for live Rev 3 firmware')
        if self.pending:
            raise ValueError('Waiting for the previous Arduino acknowledgment')
        self.command_id = self.command_id % 65535 + 1
        self.pending = dict(id=self.command_id, name=name, value=value, sent_at=None, queued_at=time.monotonic())
        self.event('command', f'{name} {value} queued (id {self.command_id})')

    def accept_ack(self, ack):
        with self.lock:
            self.last_ack=ack
            if self.pending and (ack['id']==self.pending['id'] or ack['id']==0 and ack['result']=='ERR' and ack['message'] in ('BAD_COMMAND','INPUT_TIMEOUT','INPUT_TOO_LONG')):
                self.pending=None
            self.event('firmware', f"{ack['result']}: {ack['message']} (id {ack['id']})")
            self.publish(dict(type='status', state=self.info()))

    def accept_settings(self, settings):
        with self.lock:
            changed = settings != self.settings
            self.settings = settings
            if changed:
                self.event('settings',json.dumps(settings,separators=(',',':')))
                self.publish(dict(type='status',state=self.info()))

    def accept(self, frame):
        now = time.monotonic()
        host = utc_now()
        with self.lock:
            if self.previous_seq is not None:
                delta = (frame['seq']-self.previous_seq) & 0xffffffff
                if delta > 0x7fffffff:
                    self.epoch += 1
                    self.event('reset', 'Arduino sequence restarted')
                elif delta > 1:
                    self.missing += delta-1
            self.previous_seq = frame['seq']
            frame.update(host_utc=host, elapsed_s=round(now-self.started, 6),
                         stream_epoch=self.epoch, missing_windows=self.missing)
            self.latest = frame
            self.last_frame_at = now
            self.status = 'Arduino connected · live'
            self.error = None
            if self.active:
                flat = {key: frame[key] for key in CSV_FIELDS if not key.startswith('a')}
                for i, channel in enumerate(frame['channels']):
                    flat.update({f'a{i}_{key}': channel[key] for key in CHANNEL_FIELDS})
                self.csv_writer.writerow(flat)
                self.json_file.write(json.dumps(frame, separators=(',', ':'))+'\n')
                self.rows += 1
                if now-self.last_flush >= 1:
                    for file in self.files:
                        file.flush()
                    self.last_flush = now
            self.history.append(frame)
            self.publish(dict(type='frame', frame=frame, state=self.info()))


def serial_worker(recorder, shutdown):
    while not shutdown.is_set():
        try:
            device=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=.2,exclusive=True)
            device.port=recorder.serial_port;device.dtr=False;device.rts=False
            device.open()
            with device:
                recorder.reconnect_requested.clear()
                decoder=Decoder()
                with recorder.lock:
                    recorder.status='USB open · waiting for Rev 3 firmware'
                    recorder.pending=None
                while not shutdown.is_set():
                    if recorder.reconnect_requested.is_set():
                        # Explicit user recovery resets Uno; silent/stale telemetry never does.
                        device.dtr=False
                        if shutdown.wait(.1): return
                        device.dtr=True
                        raise serial.SerialException('Manual USB reconnect')
                    with recorder.lock:
                        pending=recorder.pending
                        if pending:
                            now=time.monotonic()
                            if now-pending['queued_at']>3:
                                recorder.event('command_timeout',f"No acknowledgment for {pending['name']}; not retried")
                                recorder.last_ack=dict(id=pending['id'],result='ERR',message='COMMAND_TIMEOUT_NOT_RETRIED')
                                recorder.pending=None
                            elif pending['sent_at'] is None:
                                device.write(f"D3 {pending['id']} {pending['name']} {pending['value']}\n".encode('ascii'))
                                pending['sent_at']=now
                    chunk=device.read(max(1,min(512,device.in_waiting)))
                    if not chunk: continue
                    with recorder.lock:
                        if recorder.active: recorder.raw_file.write(utc_now()+' '+chunk.hex()+'\n')
                    before=decoder.invalid
                    messages=decoder.feed(chunk)
                    with recorder.lock: recorder.invalid+=decoder.invalid-before
                    for msg in messages:
                        if msg['type']=='ack': recorder.accept_ack(msg)
                        elif msg['type']=='settings': recorder.accept_settings(msg)
                        else: recorder.accept(msg)
        except (serial.SerialException,OSError) as exc:
            with recorder.lock:
                recorder.status='USB unavailable · retrying';recorder.error=str(exc)
                recorder.pending=None
                recorder.event('usb_reconnect',str(exc))
                recorder.publish(dict(type='status',state=recorder.info()))
            shutdown.wait(2)
        except Exception as exc:
            with recorder.lock:
                recorder.status='Recorder error';recorder.error=str(exc)
                recorder.stop();recorder.publish(dict(type='status',state=recorder.info()))
            return


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, recorder, **kwargs):
        self.recorder = recorder
        super().__init__(*args, directory=str(ROOT/'dashboard'), **kwargs)

    def log_message(self, *args):
        pass

    def json_response(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/status':
            with self.recorder.lock:
                return self.json_response(self.recorder.info())
        if path == '/api/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            client = queue.Queue(maxsize=128)
            with self.recorder.lock:
                self.recorder.clients.add(client)
                snapshot = dict(type='snapshot', frames=list(self.recorder.history), state=self.recorder.info())
            try:
                self.wfile.write(('data: '+json.dumps(snapshot)+'\n\n').encode())
                self.wfile.flush()
                while True:
                    try:
                        message = client.get(timeout=1)
                    except queue.Empty:
                        with self.recorder.lock:
                            message = dict(type='status', state=self.recorder.info())
                    self.wfile.write(('data: '+json.dumps(message, separators=(',', ':'))+'\n\n').encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with self.recorder.lock:
                    self.recorder.clients.discard(client)
            return
        if path == '/api/download.csv':
            with self.recorder.lock:
                if self.recorder.active:
                    self.recorder.csv_file.flush()
                data = (self.recorder.session/'readings.csv').read_bytes()
                name = self.recorder.session.name+'.csv'
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.send_header('Content-Disposition', f'attachment; filename="{name}"')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def do_POST(self):
        # Local controls accept JSON only from the page's own localhost origin.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
            return self.json_response({'error': 'Origin rejected'}, 403)
        if self.headers.get('Content-Type') != 'application/json':
            return self.json_response({'error': 'JSON required'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected an object')
            path = urlparse(self.path).path
            with self.recorder.lock:
                if path == '/api/start':
                    self.recorder.start()
                elif path == '/api/stop':
                    self.recorder.stop()
                elif path == '/api/mark':
                    label = data.get('label', 'Event')
                    if not isinstance(label, str) or len(label) > 160:
                        raise ValueError('Event label must be at most 160 characters')
                    self.recorder.mark(label.strip())
                elif path == '/api/quiet':
                    self.recorder.send_command('QUIET')
                elif path == '/api/command':
                    self.recorder.send_command(data.get('name'),data.get('value',0))
                elif path == '/api/reconnect':
                    self.recorder.reconnect_requested.set()
                else:
                    return self.json_response({'error': 'Unknown command'}, 404)
                state = self.recorder.info()
                self.recorder.publish(dict(type='status', state=state))
                return self.json_response(state)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.json_response({'error': str(exc)}, 400)
        except OSError as exc:
            return self.json_response({'error': f'Could not save: {exc}'}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True, help='Arduino USB serial device')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--output', type=Path, default=ROOT/'recordings')
    args = parser.parse_args()
    recorder = Recorder(args.output, args.serial)
    shutdown = threading.Event()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, recorder=recorder))
    worker = threading.Thread(target=serial_worker, args=(recorder, shutdown), daemon=True)
    worker.start()
    print(f'Open http://127.0.0.1:{args.port}/ · Ctrl+C closes capture files', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown.set()
        worker.join(timeout=2)
        recorder.stop()
        server.server_close()


if __name__ == '__main__':
    main()
