#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
#include "stubs/Arduino.h"
#include "stubs/EEPROM.h"
uint32_t fakeUs=0,eepromReadyAt=0;int source[3]={6,9,12};
USBMock Serial;EEPROMMock EEPROM;
#include "../arduino/DirectionalHaptics/DirectionalHaptics.ino"
void run(uint32_t us){uint32_t at=fakeUs;while(fakeUs-at<us)loop();}
void cmd(const char*s){eventLength=0;char b[48];strncpy(b,s,47);b[47]=0;executeCommand(b);}
bool response(const char*s){return strstr(pendingEvent,s)!=nullptr;}
void settle(dh::Envelope e[3],const float a[3],const dh::Calibration &c,int contrastValue=15){for(int i=0;i<200;i++)dh::process(e,a,c,5000,3,contrastValue);}
int main(int argc,char**argv){
 dh::Window w;w.clear();uint16_t sample[3]={0,100,700};for(int i=0;i<20;i++)w.add(sample);assert(w.mean(0)==0&&w.mean(1)==100&&w.mean(2)==700);
 dh::Calibration c={{10,10,10},{8,8,8},{970,970,970},{1,1,1}};assert(dh::valid(c));
 dh::Envelope e[3]={};for(auto &x:e)x.clear();
 float a[3]={10,0,9};settle(e,a,c);for(auto &x:e)assert(x.smoothed==0);
 a[0]=20;a[1]=22;a[2]=10;settle(e,a,c);assert(e[1].smoothed>e[0].smoothed&&e[2].smoothed==0);
 float enhancedDifference=e[1].smoothed-e[0].smoothed;
 settle(e,a,c,0);assert(enhancedDifference>e[1].smoothed-e[0].smoothed); // a 2-count difference becomes more apparent
 assert(e[0].smoothed<.2f&&e[1].smoothed<.2f); // quiet sound does not become maximum
 a[0]=a[1]=a[2]=970;settle(e,a,c);for(auto &x:e)assert(x.smoothed==1);
 a[0]=a[1]=a[2]=10;dh::process(e,a,c,5000,3,15);for(auto &x:e)assert(x.smoothed==0); // no release tail at floor
 float prior=-1;for(int value=0;value<=1023;value++){for(auto &x:e)x.clear();a[0]=value;a[1]=150;a[2]=30;settle(e,a,c);assert(e[0].smoothed+1e-6>=prior);prior=e[0].smoothed;assert(prior>=0&&prior<=1);}
 for(int sense=1;sense<=5;sense++){prior=0;for(int i=0;i<=1000;i++){float out=dh::shape(i/1000.f,sense);assert(out>=prior&&out>=0&&out<=1);prior=out;}assert(dh::shape(0,sense)==0&&dh::shape(1,sense)==1);}
 auto matched=c;float referenceLevels[3]={110,210,160};assert(dh::matchGains(matched,referenceLevels));assert(fabs(matched.gain[0]-1.5f)<1e-6&&fabs(matched.gain[1]-.75f)<1e-6);
 for(int i=0;i<3;i++)assert(fabs((referenceLevels[i]-10)*matched.gain[i]-150)<1e-4);
 auto unchanged=matched;float tooQuiet[3]={11,12,13};assert(!dh::matchGains(matched,tooQuiet));assert(!memcmp(&matched,&unchanged,sizeof(matched)));
 char command[48];titanEffect(command,48,20,1,125,20);assert(std::string(command)=="CHNL 1;vibrate 95 0.125 20 1 0;\r");
 titanEffect(command,48,21,0,50,1000);assert(std::string(command)=="CHNL 3;vibrate 1000 0.050 160 0;\r");assert(!titanEffect(command,48,20,3,50,8));assert(!titanEffect(command,48,20,0,50,2001));assert(titanFrequency(2)==130);
 setup();run(200000);assert(!calibrated&&titan.commands.empty());
 cmd("D3 1 PROFILE 21");assert(profile==21&&muted&&!qualified);
 cmd("D3 2 QUALIFY 1");assert(!qualified);
 for(int i=1;i<=4;i++){run(350000);char b[30];snprintf(b,30,"D3 3 TEST %d",i);cmd(b);run(1100000);assert(!sent[0]&&!sent[1]&&!sent[2]);}
 assert(testMask==15&&titan.commands.size()==6);
 cmd("D3 4 QUALIFY 1");assert(qualified);
 cmd("D3 5 QUIET 0");run(5600000);assert(quietReady&&!phase&&calibrated&&!saving);
 auto good=calibration;assert(calibration.reference[0]==970&&calibration.gain[0]==1);
 cmd("D3 6 REFERENCE 0");run(5500000);assert(calibrated);assert(response("MATCH_TOO_QUIET")||!eventLength);
 assert(!memcmp(&good,&calibration,sizeof(good)));
 source[0]=106;source[1]=159;source[2]=212;cmd("D3 7 REFERENCE 0");run(5600000);assert(calibrated&&!saving);assert(calibration.reference[0]==970);assert(calibration.gain[0]>1&&calibration.gain[2]<1);
 Saved saved;EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved));
 source[0]=source[1]=source[2]=6;run(100000);cmd("D3 8 RESUME 0");source[1]=970;size_t beforeOnset=titan.commands.size();uint32_t onsetStarted=fakeUs;
 while(titan.commands.size()==beforeOnset&&fakeUs-onsetStarted<20000)loop();
 assert(titan.commands.size()>beforeOnset&&maxOnsetLatency>0&&maxOnsetLatency<20000);
 run(300000);assert(desired[0]==0&&desired[1]==1000&&desired[2]==0);assert(titan.commands.back().find("CHNL 1;")==0);
 source[0]=970;source[1]=9;run(300000);assert(desired[0]==1000&&desired[1]==0&&desired[2]==0);assert(titan.commands.back().find("CHNL 3;")==0);
 source[0]=6;source[2]=970;run(300000);assert(desired[2]==1000&&desired[0]==0&&desired[1]==0);assert(titan.commands.back().find("CHNL 2;")==0);
 source[0]=source[1]=source[2]=1023;run(300000);assert(desired[0]==1000&&desired[1]==1000&&desired[2]==1000);
 cmd("D3 9 TRIM1 50");run(100000);assert(desired[1]==500&&desired[0]==1000&&desired[2]==1000);
 cmd("D3 10 MUTE 0");size_t count=titan.commands.size();run(300000);assert(titan.commands.size()==count&&!sent[0]&&!sent[1]&&!sent[2]);
 cmd("D3 11 CEILING 101");assert(ceiling==100);cmd("D3 65536 RESUME 0");assert(muted&&response("BAD_COMMAND"));cmd("D3 12 CEILING 25 garbage");assert(response("BAD_COMMAND"));
 good=calibration;source[0]=1023;cmd("D3 13 QUIET 0");run(5500000);assert(!memcmp(&good,&calibration,sizeof(good)));
 cmd("D3 14 SENSITIVITY 4");cmd("D3 15 CONTRAST 20");cmd("D3 16 SAVE 0");run(20000);Saved incomplete;EEPROM.get(512+saveSlot*64,incomplete);assert(!savedValid(incomplete));EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved));
 run(300000);EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved)&&saved.sensitivity==4&&saved.contrast==20);saved.ceiling^=1;assert(!savedValid(saved));
 calibrated=qualified=false;profile=0;sensitivity=1;contrast=0;loadSaved();assert(calibrated&&qualified&&profile==21&&sensitivity==4&&contrast==20&&trim[1]==50);
 cmd("D3 17 PROBE 0");run(1400000);assert(!probeUntil&&!titan.listening);
 Serial.free=0;auto oldDrop=dropped;run(200000);assert(dropped>oldDrop);Serial.free=63;run(100000);
 eventLength=0;for(char ch:std::string("D3 18 ")+std::string(70,'X')+"\n")Serial.input.push_back(ch);run(100000);assert(!inputOverflow&&!inputLength);
 fakeUs=0xfffff000;previousCycle=windowAt=reportAt=processedAt=rateAt=fakeUs;run(200000);assert(window.n<1000&&report.n<1000);
 if(argc>1){std::ofstream f(argv[1],std::ios::binary);f.write((const char*)Serial.output.data(),Serial.output.size());}
 std::cout<<"PASS: silence, monotonic own-channel response, near-rail full output, contrast, gain matching, all motor mappings/frequencies, calibration rejection, EEPROM persistence/interrupted save, framing/backpressure and rollover\n";
}
