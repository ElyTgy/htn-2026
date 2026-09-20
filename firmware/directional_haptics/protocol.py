"""Directional Haptics DH v3: bounded CRC-protected USB frames, little endian."""
import struct
import binascii

HEADER = struct.Struct('<II10H8B')
CHANNEL = struct.Struct('<13H')
SIZE = HEADER.size + 3*CHANNEL.size
assert SIZE == 114

def decode(kind, payload):
    if kind == 3:
        if len(payload)!=16: raise ValueError('Invalid settings length')
        sensitivity,contrast,full,*values=struct.unpack('<BB7H',payload)
        if not 1<=sensitivity<=5 or not 0<=contrast<=30 or full!=970 or any(not 500<=v<=2000 for v in values[:3]) or values[3:]!=[160,95,130]:
            raise ValueError('Invalid settings')
        return dict(type='settings',sensitivity=sensitivity,contrast=contrast,full_scale=full,gains=[v/1000 for v in values[:3]],frequencies=values[3:])
    if kind == 2:
        text = payload.decode('ascii')
        parts = text.split(' ', 2)
        if len(parts) != 3 or not parts[0].isdigit() or int(parts[0]) > 65535 or parts[1] not in ('OK','ERR','TITAN'):
            raise ValueError('Invalid event')
        return dict(type='ack', id=int(parts[0]), result=parts[1], message=parts[2])
    if kind != 1 or len(payload) != SIZE:
        raise ValueError('Unsupported frame')
    (ms, seq, rate, gap, tx, updates, dropped, flags, cmdseq, window, samples, onset_latency,
     phase, progress, profile, ceiling, tests, *trims) = HEADER.unpack_from(payload)
    if phase > 2 or progress > 100 or profile not in (0,20,21) or ceiling > 100 or tests > 15 or flags > 127 or any(not 25 <= x <= 100 for x in trims) or not 1 <= samples <= 1000 or not window:
        raise ValueError('Invalid telemetry bounds')
    channels=[]
    for i in range(3):
        raw, low, high, mean, amp, peak, norm, smooth, target, sent, floor, ref, close = CHANNEL.unpack_from(payload, HEADER.size+i*CHANNEL.size)
        if not 0 <= low <= raw <= high <= 1023 or not low*16 <= mean <= high*16 or max(amp,peak,floor,ref,close)>16368 or max(norm,smooth,target,sent)>1000:
            raise ValueError('Invalid channel bounds')
        channels.append(dict(raw=raw,min=low,max=high,mean=mean/16,amplitude=amp/16,peak=peak/16,
            normalized=norm/10,smoothed=smooth/10,desired=target/10,sent=sent/10,
            floor=floor/16,reference=ref/16,close=close/16,p2p=high-low,rail=high>=1021))
    return dict(type='frame',version=3,seq=seq,device_ms=ms,window_us=window,rate=rate,gap_us=gap,
        tx_us=tx,update_rate=updates,dropped=dropped,samples=samples,flags=flags,
        calibrated=bool(flags&1),muted=bool(flags&2),qualified=bool(flags&4),saving=bool(flags&8),
        quiet_ready=bool(flags&16),probing=bool(flags&32),sensor_stale=bool(flags&64),
        phase=phase,progress=progress,profile=profile,ceiling=ceiling,test_mask=tests,trims=trims,
        command_sequence=cmdseq,onset_latency_us=onset_latency,channels=channels)

class Decoder:
    def __init__(self): self.buffer=bytearray(); self.invalid=0
    def feed(self, chunk):
        self.buffer.extend(chunk)
        messages=[]
        while len(self.buffer)>=4:
            if self.buffer[:2]!=b'DH':
                del self.buffer[0];self.invalid+=1;continue
            n,tag=self.buffer[2:4]
            if n>114 or tag not in (0x31,0x32,0x33) or (tag==0x31 and n!=114) or (tag==0x32 and n>71) or (tag==0x33 and n!=16):
                del self.buffer[0];self.invalid+=1;continue
            if len(self.buffer)<n+6: break
            packet=bytes(self.buffer[:n+6])
            crc=binascii.crc_hqx(packet[2:-2],0xffff)
            if crc != int.from_bytes(packet[-2:],'little'):
                del self.buffer[0];self.invalid+=1;continue
            del self.buffer[:n+6]
            try: messages.append(decode(tag&15,packet[4:-2]))
            except (ValueError,UnicodeError,struct.error): self.invalid+=1
        return messages

def encode_test_frame(kind,payload):
    body=bytes([len(payload),0x30|kind])+payload
    return b'DH'+body+binascii.crc_hqx(body,0xffff).to_bytes(2,'little')
