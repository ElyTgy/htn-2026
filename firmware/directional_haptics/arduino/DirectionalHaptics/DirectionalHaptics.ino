/* Directional Haptics 3.0.0 — Uno ATmega328P, three SparkFun ENVELOPE inputs.
 * A0 BACK -> TITAN M; A1 LEFT -> L; A2 RIGHT -> R. D2 RX, D3 TX.
 * Stock Vector Haptics adapter: finite effects; qualified hardware required.
 * USB is diagnostics/config only. Normal operation has no browser dependency.
 */
#include <Arduino.h>
#include <SoftwareSerial.h>
#include <EEPROM.h>
#include <avr/eeprom.h>
#include "Signal.h"
#include "Storage.h"
#include "TitanAdapter.h"
#include "Wire.h"

SoftwareSerial titan(2,3);
dh::Window window,report;
dh::Calibration calibration={};dh::Moments moments[3];dh::Envelope envelope[3];
float amplitude[3]={},peak[3]={},quietFloor[3]={},quietClose[3]={},quietSd[3]={};
uint16_t desired[3]={},sent[3]={};
uint32_t sentAt[3]={},expiresAt[3]={},riseAt[3]={};
bool calibrated=false,qualified=false,muted=false,quietReady=false,saving=false,phaseBad=false,telemetryOn=true;
uint8_t profile=0,ceiling=100,trim[3]={100,100,100},sensitivity=3,contrast=15,phase=0,testMask=0,nextChannel=0;
uint32_t windowAt=0,reportAt=0,processedAt=0,rateAt=0,previousCycle=0,rateSamples=0,seq=0,calAt=0;
uint32_t lastTxAt=0,probeUntil=0,testUntil=0,txCount=0;
uint16_t rate=0,maxGap=0,txUs=0,updateRate=0,dropped=0,commandSequence=0,maxOnsetLatency=0;
char input[48],pendingEvent[72],probeReply[48];uint8_t inputLength=0,eventLength=0,probeLength=0;
bool inputOverflow=false;uint32_t inputAt=0;
bool settingsDue=true;uint32_t settingsAt=0;
uint8_t tx[120],txLength=0,txOffset=0;
Saved saveBuffer;uint8_t saveStep=0,saveSlot=0;int8_t activeSlot=-1;uint16_t generation=0;

uint16_t bounded(uint32_t x){return x>65535UL?65535:(uint16_t)x;}
uint16_t q4(float x){return (uint16_t)(x*16+0.5f);}
void eventP(uint16_t id,PGM_P kind,PGM_P message){
 if(eventLength)return;
 int n=snprintf_P(pendingEvent,sizeof(pendingEvent),PSTR("%u "),id);
 size_t k=strlen_P(kind),m=strlen_P(message);
 if(n<0||n+k+m+1>=sizeof(pendingEvent))return;
 strcpy_P(pendingEvent+n,kind);pendingEvent[n+k]=' ';strcpy_P(pendingEvent+n+k+1,message);eventLength=n+k+m+1;
}
#define event(id,kind,message) eventP(id,PSTR(kind),PSTR(message))
void probeEvent(){
 if(probeLength){int n=snprintf_P(pendingEvent,sizeof(pendingEvent),PSTR("0 TITAN %s"),probeReply);if(n>0&&n<(int)sizeof(pendingEvent))eventLength=n;}
 else event(0,"ERR","NO_REPLY_VERSION_UNKNOWN");
}
bool queueFrame(uint8_t type,const void*data,uint8_t n){
 if(txOffset<txLength||n>114)return false;
 tx[0]='D';tx[1]='H';tx[2]=n;tx[3]=0x30|type;memcpy(tx+4,data,n);
 uint16_t crc=dh::crc16(tx+2,n+2);tx[n+4]=crc&255;tx[n+5]=crc>>8;txLength=n+6;txOffset=0;return true;
}
void drain(){
 if(txOffset>=txLength&&eventLength&&queueFrame(2,pendingEvent,eventLength))eventLength=0;
 uint8_t n=txLength-txOffset;if(n>16)n=16;int available=Serial.availableForWrite();if(n>available)n=available;
 if(n)txOffset+=Serial.write(tx+txOffset,n);
}
void clearLevels(){for(uint8_t i=0;i<3;i++){envelope[i].clear();desired[i]=0;riseAt[i]=0;}}
void loadSaved(){
 // Dedicated slots: previous Rev 1 and unshipped sensor-draft EEPROM untouched.
 Saved a,b;EEPROM.get(512,a);EEPROM.get(576,b);bool va=savedValid(a),vb=savedValid(b);if(!va&&!vb)return;
 activeSlot=vb&&(!va||(int16_t)(b.generation-a.generation)>0)?1:0;const Saved&s=activeSlot?b:a;
 calibration=s.calibration;generation=s.generation;ceiling=s.ceiling;profile=s.profile;qualified=s.qualified;
 memcpy(trim,s.trim,3);sensitivity=s.sensitivity;contrast=s.contrast;calibrated=true;settingsDue=true;
}
void beginSave(){
 memset(&saveBuffer,0,sizeof(saveBuffer));saveBuffer.magic=0x4433;saveBuffer.version=3;saveBuffer.generation=generation+1;
 saveBuffer.calibration=calibration;saveBuffer.ceiling=ceiling;saveBuffer.profile=profile;saveBuffer.qualified=qualified;memcpy(saveBuffer.trim,trim,3);saveBuffer.sensitivity=sensitivity;saveBuffer.contrast=contrast;
 saveBuffer.crc=dh::crc16((uint8_t*)&saveBuffer,offsetof(Saved,crc));saveBuffer.committed=0xa5;
 saveSlot=activeSlot==0?1:0;saveStep=0;saving=true;clearLevels();
}
void serviceSave(){
 if(!saving||!eeprom_is_ready())return;int base=512+saveSlot*64;
 if(saveStep==0)EEPROM.update(base+offsetof(Saved,committed),0);
 else if(saveStep<=offsetof(Saved,committed))EEPROM.update(base+saveStep-1,((uint8_t*)&saveBuffer)[saveStep-1]);
 else if(saveStep==offsetof(Saved,committed)+1)EEPROM.update(base+offsetof(Saved,committed),0xa5);
 else {if(eventLength)return;saving=false;activeSlot=saveSlot;generation=saveBuffer.generation;event(0,"OK","SAVED");return;}
 ++saveStep;
}
void beginCalibration(uint8_t p){
 phase=p;phaseBad=false;calAt=millis()+200;clearLevels();if(p==1)quietReady=false;
 for(uint8_t i=0;i<3;i++)moments[i].clear();
}
void calibrationWindow(uint32_t dt){
 if(!phase||(int32_t)(millis()-calAt)<0)return;
 if(dt>20000UL)phaseBad=true;
 for(uint8_t i=0;i<3;i++){moments[i].add(amplitude[i]);if(window.hi[i]>=1021)phaseBad=true;}
 if(millis()-calAt<5000||eventLength)return;
 if(phaseBad||moments[0].n<500){phase=0;event(0,"ERR","CAL_CLIPPED_OR_INTERRUPTED");return;}
 dh::Calibration candidate=calibration;
 if(phase==1){
   for(uint8_t i=0;i<3;i++){
     quietSd[i]=moments[i].sd();
     candidate.floor[i]=moments[i].mean+fmaxf(1.5f,3*quietSd[i]);
     candidate.close[i]=moments[i].mean+fmaxf(.5f,1.5f*quietSd[i]);
     candidate.reference[i]=dh::FULL_SCALE_ADC;
     candidate.gain[i]=calibrated?calibration.gain[i]:1.0f;
   }
 } else {
   float levels[3];for(uint8_t i=0;i<3;i++)levels[i]=moments[i].mean;
   if(!dh::matchGains(candidate,levels)){phase=0;event(0,"ERR","MATCH_TOO_QUIET_OR_UNBALANCED");return;}
 }
 uint8_t completed=phase;phase=0;
 if(!dh::valid(candidate)){event(0,"ERR","CAL_INVALID");return;}
 calibration=candidate;calibrated=true;quietReady=true;settingsDue=true;beginSave();
 if(completed==1)event(0,"OK","FLOOR_ACCEPTED_SAVING");else event(0,"OK","MATCH_ACCEPTED_SAVING");
}
void processWindow(uint32_t now){
 uint32_t dt=now-windowAt;if(dt<5000||window.n<3)return;
 for(uint8_t i=0;i<3;i++){amplitude[i]=window.mean(i);if(amplitude[i]>peak[i])peak[i]=amplitude[i];}
 calibrationWindow(dt);
 if(calibrated&&!phase&&!saving)dh::process(envelope,amplitude,calibration,dt,sensitivity,contrast);
 else for(uint8_t i=0;i<3;i++)envelope[i].clear();
 for(uint8_t i=0;i<3;i++){
   desired[i]=calibrated&&qualified&&!phase&&!saving&&!muted?
     (uint16_t)(envelope[i].smoothed*ceiling*trim[i]/10.0f+0.5f):0;
   if(!desired[i])riseAt[i]=0;
 }
 window.clear();windowAt=processedAt=now;
}
void sendEffect(uint8_t i,uint16_t level,uint16_t duration){
 char command[48];int n=titanEffect(command,sizeof(command),profile,i,level,duration);if(n<=0||n>=(int)sizeof(command))return;
 // SoftwareSerial is blocking, with interrupts masked within each byte.
 uint32_t start=micros();titan.write((uint8_t*)command,n);uint32_t end=micros();txUs=bounded(end-start);lastTxAt=end;
 sentAt[i]=end;expiresAt[i]=millis()+duration;sent[i]=level;++commandSequence;++txCount;
 if(riseAt[i]){uint16_t latency=bounded(end-riseAt[i]);if(latency>maxOnsetLatency)maxOnsetLatency=latency;riseAt[i]=0;}
}
void serviceMotors(){
 for(uint8_t i=0;i<3;i++)if(sent[i]&&(int32_t)(millis()-expiresAt[i])>=0)sent[i]=0;
 if(testUntil){if((int32_t)(millis()-testUntil)<0)return;testUntil=0;}
 if(!calibrated||!qualified||muted||phase||saving||probeUntil||micros()-processedAt>20000UL)return;
 // At most ONE motor command per sensing loop. Sample between channel writes.
 // Changed levels may pre-empt the stable refresh cadence. At most one write is
 // performed per sensing loop, and all effects remain finite.
 for(uint8_t k=0;k<3;k++){
   uint8_t i=nextChannel;nextChannel=(nextChannel+1)%3;
   uint32_t age=micros()-sentAt[i];uint16_t difference=desired[i]>sent[i]?desired[i]-sent[i]:sent[i]-desired[i];
   if(desired[i]&&((difference>=TITAN_CHANGE_PERMILLE&&age>=TITAN_CHANGE_US)||age>=TITAN_REFRESH_US)){
     sendEffect(i,desired[i],TITAN_EFFECT_MS);return;
   }
 }
}
void executeCommand(char*line){
 char name[16],extra;unsigned long parsedId;int value;
 if(sscanf_P(line,PSTR("D3 %5lu %15s %3d %c"),&parsedId,name,&value,&extra)!=3||!parsedId||parsedId>65535UL){event(0,"ERR","BAD_COMMAND");return;}
 uint16_t id=parsedId;
 if(!strcmp_P(name,PSTR("MUTE"))&&value==0){muted=true;clearLevels();event(id,"OK","MUTED_FINITE_EFFECTS_EXPIRING");return;}
 if(!strcmp_P(name,PSTR("CANCEL"))&&value==0){phase=0;quietReady=false;event(id,"OK","CAL_CANCELED");return;}
 if(phase||saving||probeUntil||testUntil){event(id,"ERR","BUSY");return;}
 if(!strcmp_P(name,PSTR("HELLO"))&&value==0){settingsDue=true;event(id,"OK","DIRECTIONAL_HAPTICS_3.0.0");}
 else if(!strcmp_P(name,PSTR("QUIET"))&&value==0){beginCalibration(1);event(id,"OK","QUIET_STARTED");}
 else if(!strcmp_P(name,PSTR("REFERENCE"))&&value==0){if(!calibrated)event(id,"ERR","QUIET_REQUIRED");else {beginCalibration(2);event(id,"OK","REFERENCE_STARTED");}}
 else if(!strcmp_P(name,PSTR("SAVE"))&&value==0){if(!calibrated)event(id,"ERR","CAL_REQUIRED");else {beginSave();event(id,"OK","SAVING");}}
 else if(!strcmp_P(name,PSTR("SENSITIVITY"))&&value>=1&&value<=5){sensitivity=value;settingsDue=true;event(id,"OK","SENSITIVITY_SET");}
 else if(!strcmp_P(name,PSTR("CONTRAST"))&&value>=0&&value<=30){contrast=value;settingsDue=true;event(id,"OK","CONTRAST_SET");}
 else if(!strcmp_P(name,PSTR("CEILING"))&&value>=0&&value<=100){ceiling=value;event(id,"OK","CEILING_SET");}
 else if(strlen(name)==5&&!strncmp_P(name,PSTR("TRIM"),4)&&name[4]>='0'&&name[4]<='2'&&value>=25&&value<=100){trim[name[4]-'0']=value;event(id,"OK","TRIM_SET");}
 else if(!strcmp_P(name,PSTR("RESUME"))&&value==0){muted=false;event(id,"OK","RESUMED");}
 else if(!strcmp_P(name,PSTR("TELEMETRY"))&&(value==0||value==1)){telemetryOn=value;event(id,"OK","TELEMETRY_SET");}
 else if(!strcmp_P(name,PSTR("PROFILE"))&&(value==20||value==21||value==0)){profile=value;qualified=false;testMask=0;muted=true;clearLevels();event(id,"OK","PROFILE_SET_TESTS_REQUIRED");}
 else if(!strcmp_P(name,PSTR("TEST"))&&value>=1&&value<=4){
   if(!profile)event(id,"ERR","CONFIRM_PROFILE_FIRST");
   else if(micros()-lastTxAt<300000UL)event(id,"ERR","WAIT_BETWEEN_TESTS");
   else {
     muted=true;clearLevels();
     if(value==4){sendEffect(1,400,TITAN_TEST_MS);sendEffect(0,700,TITAN_TEST_MS);sendEffect(2,1000,TITAN_TEST_MS);}
     else sendEffect(value==1?1:value==2?2:0,1000,TITAN_TEST_MS);
     testUntil=millis()+TITAN_TEST_MS+10;testMask|=1<<(value-1);event(id,"OK","TEST_SENT_OBSERVE_START_AND_STOP");
   }
 }
 else if(!strcmp_P(name,PSTR("QUALIFY"))&&value==1){if(profile&&testMask==15){qualified=true;event(id,"OK","SETUP_QUALIFIED_SAVE_TO_KEEP");}else event(id,"ERR","TEST_ALL_CHANNELS_AND_OVERLAP");}
 else if(!strcmp_P(name,PSTR("PROBE"))&&value==0){muted=true;clearLevels();probeLength=0;titan.listen();titan.print(F("HDI D;\r"));probeUntil=millis()+1200;event(id,"OK","PROBING_TITAN");}
 else event(id,"ERR","UNKNOWN_COMMAND_OR_RANGE");
}
void serviceInput(){
 if(eventLength)return;
 if((inputLength||inputOverflow)&&millis()-inputAt>500){inputLength=0;inputOverflow=false;event(0,"ERR","INPUT_TIMEOUT");return;}
 for(uint8_t n=0;n<8&&Serial.available();n++){
   char c=Serial.read();inputAt=millis();if(c=='\r')continue;
   if(c=='\n'){if(inputOverflow)event(0,"ERR","INPUT_TOO_LONG");else {input[inputLength]=0;executeCommand(input);}inputLength=0;inputOverflow=false;return;}
   if(inputLength>=sizeof(input)-1)inputOverflow=true;else if(!inputOverflow)input[inputLength++]=c;
 }
}
void serviceProbe(){
 if(!probeUntil)return;
 for(uint8_t n=0;n<8&&titan.available();n++){int c=titan.read();if(c>=32&&c<127&&probeLength<sizeof(probeReply)-1)probeReply[probeLength++]=c;}
 if((int32_t)(millis()-probeUntil)>=0&&!eventLength){probeUntil=0;titan.stopListening();probeReply[probeLength]=0;probeEvent();}
}
void emitSettings(uint32_t now){
 if(now-settingsAt>1000000UL)settingsDue=true;
 if(!settingsDue||eventLength)return;
 SettingsTelemetry c={};c.sensitivity=sensitivity;c.contrast=contrast;c.fullScale=970;
 for(uint8_t i=0;i<3;i++){c.gain[i]=(uint16_t)((calibrated?calibration.gain[i]:1)*1000+.5f);c.frequency[i]=titanFrequency(i);}
 if(queueFrame(3,&c,sizeof(c))){settingsAt=now;settingsDue=false;}
}
void emitTelemetry(uint32_t now){
 if(now-reportAt<40000UL)return;++seq;
 if(telemetryOn){
   Telemetry t={};t.ms=millis();t.sequence=seq;t.rate=rate;t.gapUs=maxGap;t.txUs=txUs;t.updateRate=updateRate;t.dropped=dropped;
   t.flags=(calibrated?1:0)|(muted?2:0)|(qualified?4:0)|(saving?8:0)|(quietReady?16:0)|(probeUntil?32:0)|((now-processedAt>20000UL)?64:0);
   t.commandSequence=commandSequence;t.onsetLatencyUs=maxOnsetLatency;t.windowUs=bounded(now-reportAt);t.samples=report.n;
   t.phase=phase;t.profile=profile;t.ceiling=ceiling;t.testMask=testMask;memcpy(t.trim,trim,3);
   if(phase&&(int32_t)(millis()-calAt)>=0)t.progress=min((uint32_t)100,(millis()-calAt)/50);
   for(uint8_t i=0;i<3;i++){
     ChannelTelemetry &c=t.channel[i];c.raw=report.raw[i];c.low=report.lo[i];c.high=report.hi[i];c.meanQ4=q4(report.mean(i));c.amplitudeQ4=q4(amplitude[i]);c.peakQ4=q4(peak[i]);
     c.normalized=(uint16_t)(envelope[i].normalized*1000+0.5f);c.smoothed=(uint16_t)(envelope[i].smoothed*1000+0.5f);c.desired=desired[i];c.sent=sent[i];
     c.floorQ4=q4(calibration.floor[i]);c.referenceQ4=q4(calibration.reference[i]);c.closeQ4=q4(calibration.close[i]);
   }
   if(eventLength||!queueFrame(1,&t,sizeof(t)))++dropped;else maxOnsetLatency=0;
 }
 report.clear();reportAt=now;if(telemetryOn)maxGap=0;for(uint8_t i=0;i<3;i++)peak[i]=0;
}
void setup(){Serial.begin(115200);titan.begin(115200);titan.stopListening();loadSaved();window.clear();report.clear();clearLevels();windowAt=reportAt=processedAt=rateAt=micros();event(0,"OK","DIRECTIONAL_HAPTICS_3.0.0");}
void loop(){
 uint32_t cycle=micros();if(previousCycle){uint16_t gap=bounded(cycle-previousCycle);if(gap>maxGap)maxGap=gap;}previousCycle=cycle;
 uint16_t a[3];for(uint8_t i=0;i<3;i++){analogRead(A0+i);a[i]=analogRead(A0+i);}
 uint32_t sampledAt=micros();
 if(calibrated&&qualified&&!muted&&!phase&&!saving&&!probeUntil&&!testUntil){
   for(uint8_t i=0;i<3;i++)if(!envelope[i].open&&!riseAt[i]&&a[i]>calibration.floor[i])riseAt[i]=sampledAt;
 }
 window.add(a);report.add(a);++rateSamples;
 processWindow(micros());serviceInput();serviceProbe();serviceSave();serviceMotors();drain();uint32_t now=micros();
 if(now-rateAt>=1000000UL){rate=bounded(rateSamples*1000UL/((now-rateAt)/1000));updateRate=bounded(txCount*1000UL/((now-rateAt)/1000));rateSamples=txCount=0;rateAt=now;}
 emitTelemetry(now);emitSettings(now);
}
