import binascii,csv,json,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol import Decoder,HEADER,CHANNEL,encode_test_frame
from record import Recorder

def packet(seq=1):
    head=HEADER.pack(40,seq,1300,2700,3100,210,0,1,3,40100,52,5,0,0,20,25,15,100,100,100)
    channels=b''.join(CHANNEL.pack(20+i,19+i,21+i,320+16*i,320+16*i,336+16*i,500,450,112,110,160,480,144) for i in range(3))
    return encode_test_frame(1,head+channels)

class Tests(unittest.TestCase):
    def test_settings_and_old_version(self):
        p=encode_test_frame(3,struct.pack('<BB7H',3,15,970,1000,750,1500,160,95,130))
        d=Decoder();settings=d.feed(p)[0]
        self.assertEqual(settings['gains'],[1,.75,1.5])
        self.assertEqual(settings['full_scale'],970)
        for invalid in [(0,15,970),(3,31,970),(3,15,112)]:
            self.assertEqual(d.feed(encode_test_frame(3,struct.pack('<BB7H',*invalid,1000,1000,1000,160,95,130))),[])
        old=bytearray(packet());old[3]=0x21
        old[-2:]=binascii.crc_hqx(old[2:-2],0xffff).to_bytes(2,'little')
        self.assertEqual(len(d.feed(old+p)),1)
        self.assertGreater(d.invalid,0)
    def test_partial_crc_and_resync(self):
        d=Decoder();p=packet();self.assertFalse(d.feed(p[:17]));f=d.feed(p[17:])[0]
        self.assertEqual(f['channels'][1]['mean'],21);self.assertEqual(f['channels'][0]['desired'],11.2)
        bad=bytearray(p);bad[14]^=1
        self.assertEqual(len(d.feed(bytes(bad)+b'bad'+p)),1);self.assertGreater(d.invalid,0)
        for _ in range(100):d.feed(b'x'*512)
        self.assertLess(len(d.buffer),120)
    def test_bad_bounds(self):
        payload=bytearray(packet()[4:-2]);payload[28+3]=101 # ceiling
        self.assertEqual(Decoder().feed(encode_test_frame(1,payload)),[])
    def test_recorder_and_command_ack(self):
        with tempfile.TemporaryDirectory() as root:
            r=Recorder(root,'TEST');frame=Decoder().feed(packet())[0];r.accept(frame)
            r.send_command('MUTE');self.assertIsNotNone(r.pending)
            with self.assertRaises(ValueError):r.send_command('RESUME')
            r.accept_ack(dict(id=r.pending['id'],result='OK',message='MUTED'))
            self.assertIsNone(r.pending)
            for name,value in [('TEST',5),('CEILING',101),('MUTE',True),('BOGUS',0),('SENSITIVITY',0),('SENSITIVITY',6),('CONTRAST',31)]:
                with self.assertRaises(ValueError):r.send_command(name,value)
            first=r.session;r.stop()
            with (first/'readings.csv').open() as f: rows=list(csv.DictReader(f))
            self.assertEqual(float(rows[0]['a1_mean']),21)
            self.assertEqual(float(rows[0]['a2_sent']),11)
            settings=Decoder().feed(encode_test_frame(3,struct.pack('<BB7H',4,20,970,1000,1000,1000,160,95,130)))[0]
            r.accept_settings(settings)
            r.start();self.assertNotEqual(first,r.session)
            self.assertEqual(json.loads((r.session/'metadata.json').read_text())['settings_at_start'],settings)
            self.assertEqual(json.loads(r.events[-1]['label']),settings)
            r.send_command('SENSITIVITY',4)
            self.assertEqual(r.pending['value'],4)
            r.stop()

if __name__=='__main__':unittest.main()
