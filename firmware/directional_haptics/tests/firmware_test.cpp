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
 for(auto &x:e)x.clear();a[0]=45;a[1]=a[2]=8;for(int i=0;i<200;i++)dh::process(e,a,c,5000,3,15,40);assert(e[0].smoothed==0); // 35 counts over the floor stays silent under a 40-count threshold
 a[0]=150;for(int i=0;i<200;i++)dh::process(e,a,c,5000,3,15,40);assert(e[0].smoothed>0&&e[1].smoothed==0);float gated=e[0].smoothed;
 for(auto &x:e)x.clear();settle(e,a,c);assert(e[0].smoothed>gated); // the same sound asks for less once the range starts at the threshold
 a[0]=970;for(int i=0;i<200;i++)dh::process(e,a,c,5000,3,15,40);assert(e[0].smoothed==1);
 float prior=-1;for(int value=0;value<=1023;value++){for(auto &x:e)x.clear();a[0]=value;a[1]=150;a[2]=30;settle(e,a,c);assert(e[0].smoothed+1e-6>=prior);prior=e[0].smoothed;assert(prior>=0&&prior<=1);}
 for(int sense=1;sense<=5;sense++){prior=0;for(int i=0;i<=1000;i++){float out=dh::shape(i/1000.f,sense);assert(out>=prior&&out>=0&&out<=1);prior=out;}assert(dh::shape(0,sense)==0&&dh::shape(1,sense)==1);}
 auto matched=c;float referenceLevels[3]={110,210,160};assert(dh::matchGains(matched,referenceLevels));assert(fabs(matched.gain[0]-1.5f)<1e-6&&fabs(matched.gain[1]-.75f)<1e-6);
 for(int i=0;i<3;i++)assert(fabs((referenceLevels[i]-10)*matched.gain[i]-150)<1e-4);
 auto unchanged=matched;float tooQuiet[3]={11,12,13};assert(!dh::matchGains(matched,tooQuiet));assert(!memcmp(&matched,&unchanged,sizeof(matched)));
 char command[48];titanEffect(command,48,20,1,125,20);assert(std::string(command)=="CHNL 1;vibrate 95 0.125 20 1 0;\r\n");
 titanEffect(command,48,21,0,50,1000);assert(std::string(command)=="CHNL 3;vibrate 1000 0.050 160 0;\r\n");assert(!titanEffect(command,48,20,3,50,8));assert(!titanEffect(command,48,20,0,50,3001));assert(titanFrequency(2)==130);
 setup();run(200000);assert(!calibrated&&titan.commands.empty());
 // Power-on cue: nothing for 5 s, then left, back, right for 3 s each, uncalibrated and unqualified.
 run(4700000);assert(titan.commands.empty());
 run(200000);assert(titan.commands.size()==1&&titan.commands[0]=="CHNL 1;vibrate 95 1.000 3000 1 0;\r\n"&&sent[1]==1000);
 cmd("D3 1 HELLO 0");assert(response("BUSY"));
 run(3000000);assert(titan.commands.size()==2&&titan.commands[1]=="CHNL 3;vibrate 160 1.000 3000 1 0;\r\n"&&!sent[1]&&sent[0]==1000);
 run(3000000);assert(titan.commands.size()==3&&titan.commands[2]=="CHNL 2;vibrate 130 1.000 3000 1 0;\r\n"&&!sent[0]&&sent[2]==1000);
 run(3200000);assert(titan.commands.size()==3&&startupStep==3&&!testUntil&&!sent[0]&&!sent[1]&&!sent[2]&&!testMask);
 cmd("D3 1 HELLO 0");assert(response("DIRECTIONAL_HAPTICS"));titan.commands.clear();
 cmd("D3 1 PROFILE 21");assert(profile==21&&muted&&!qualified);
 cmd("D3 2 QUALIFY 1");assert(!qualified);
 for(int i=1;i<=3;i++){run(350000);char b[30];snprintf(b,30,"D3 3 TEST %d",i);cmd(b);run(1100000);assert(!sent[0]&&!sent[1]&&!sent[2]);}
 assert(testMask==7&&titan.commands.size()==3);
 // TEST 4: TITAN plays one effect at a time, so the three motors share 50 ms slots in rotation at their own levels.
 run(350000);cmd("D3 3 TEST 4");run(1000000);cmd("D3 3 HELLO 0");assert(response("BUSY"));run(1300000);assert(!testUntil&&!sent[0]&&!sent[1]&&!sent[2]);
 {size_t n=titan.commands.size()-3;assert(n>=36&&n<=41);int per[4]={};
  for(size_t k=3;k<titan.commands.size();k++){const std::string&s=titan.commands[k];int ch=s[5]-'0';++per[ch];
   assert(s.find(ch==1?"vibrate 40 0.400 95 ":ch==3?"vibrate 40 0.700 160 ":"vibrate 40 1.000 130 ")==7);
   if(k>3)assert(s.substr(0,7)!=titan.commands[k-1].substr(0,7));} // never the same motor twice running
  assert(per[1]>=12&&per[2]>=12&&per[3]>=12);}
 assert(testMask==15);
 cmd("D3 4 QUALIFY 1");assert(qualified);
 cmd("D3 5 QUIET 0");run(5600000);assert(quietReady&&!phase&&calibrated&&!saving);
 auto good=calibration;assert(calibration.reference[0]==970&&calibration.gain[0]==1);
 cmd("D3 6 REFERENCE 0");run(5500000);assert(calibrated);assert(response("MATCH_TOO_QUIET")||!eventLength);
 assert(!memcmp(&good,&calibration,sizeof(good)));
 source[0]=106;source[1]=159;source[2]=212;cmd("D3 7 REFERENCE 0");run(5600000);assert(calibrated&&!saving);assert(calibration.reference[0]==970);assert(calibration.gain[0]>1&&calibration.gain[2]<1);
 Saved saved;EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved));
 source[0]=source[1]=source[2]=6;run(100000);while(fakeUs-reportAt>15000)loop(); // start just after a report: the report that carries the onset latency also clears it
 cmd("D3 8 RESUME 0");source[1]=970;size_t beforeOnset=titan.commands.size();uint32_t onsetStarted=fakeUs;
 while(titan.commands.size()==beforeOnset&&fakeUs-onsetStarted<20000)loop();
 assert(titan.commands.size()>beforeOnset&&maxOnsetLatency>0&&maxOnsetLatency<20000);
 run(300000);assert(desired[0]==0&&desired[1]==1000&&desired[2]==0);assert(titan.commands.back().find("CHNL 1;")==0);
 source[0]=970;source[1]=9;run(300000);assert(desired[0]==1000&&desired[1]==0&&desired[2]==0);assert(titan.commands.back().find("CHNL 3;")==0);
 source[0]=6;source[2]=970;run(300000);assert(desired[2]==1000&&desired[0]==0&&desired[1]==0);assert(titan.commands.back().find("CHNL 2;")==0);
 source[0]=6;source[2]=9;source[1]=45;run(300000);assert(threshold==40&&desired[0]==0&&desired[1]==0&&desired[2]==0); // room-level sound stays silent
 cmd("D3 8 THRESHOLD 201");assert(threshold==40);cmd("D3 8 THRESHOLD 0");run(300000);assert(desired[1]>0);cmd("D3 8 THRESHOLD 60");run(300000);assert(desired[1]==0);
 source[0]=source[1]=source[2]=1023;size_t count=titan.commands.size();run(300000);assert(desired[0]==1000&&desired[1]==1000&&desired[2]==1000);
 {size_t n=titan.commands.size();assert(n-count>=5&&n-count<=7); // one effect per 50 ms slot, however many motors are active
  std::string x=titan.commands[n-1].substr(0,7),y=titan.commands[n-2].substr(0,7),z=titan.commands[n-3].substr(0,7);assert(x!=y&&y!=z&&x!=z);} // all three in rotation
 cmd("D3 9 TRIM1 50");run(100000);assert(desired[1]==500&&desired[0]==1000&&desired[2]==1000);
 cmd("D3 10 MUTE 0");count=titan.commands.size();run(300000);assert(titan.commands.size()==count&&!sent[0]&&!sent[1]&&!sent[2]);
 cmd("D3 11 CEILING 101");assert(ceiling==100);cmd("D3 65536 RESUME 0");assert(muted&&response("BAD_COMMAND"));cmd("D3 12 CEILING 25 garbage");assert(response("BAD_COMMAND"));
 good=calibration;source[0]=1023;cmd("D3 13 QUIET 0");run(5500000);assert(!memcmp(&good,&calibration,sizeof(good)));
 cmd("D3 14 SENSITIVITY 4");cmd("D3 15 CONTRAST 20");cmd("D3 16 SAVE 0");run(20000);Saved incomplete;EEPROM.get(512+saveSlot*64,incomplete);assert(!savedValid(incomplete));EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved));
 run(300000);EEPROM.get(512+activeSlot*64,saved);assert(savedValid(saved)&&saved.sensitivity==4&&saved.contrast==20);saved.ceiling^=1;assert(!savedValid(saved));
 calibrated=qualified=false;profile=0;sensitivity=1;contrast=0;threshold=0;loadSaved();assert(threshold==60);EEPROM.data[THRESHOLD_AT+1]^=1;threshold=THRESHOLD_DEFAULT;loadSaved();assert(threshold==THRESHOLD_DEFAULT);EEPROM.data[THRESHOLD_AT+1]^=1;assert(calibrated&&qualified&&profile==21&&sensitivity==4&&contrast==20&&trim[1]==50);
 cmd("D3 17 PROBE 0");run(1400000);assert(!probeUntil&&!titan.listening);
 count=titan.commands.size();startupStep=0;run(100000);assert(muted&&startupStep==3&&titan.commands.size()==count); // a mute cancels a pending power-on cue
 Serial.free=0;auto oldDrop=dropped;run(200000);assert(dropped>oldDrop);Serial.free=63;run(100000);
 eventLength=0;for(char ch:std::string("D3 18 ")+std::string(70,'X')+"\n")Serial.input.push_back(ch);run(100000);assert(!inputOverflow&&!inputLength);
 fakeUs=0xfffff000;previousCycle=windowAt=reportAt=processedAt=rateAt=fakeUs;run(200000);assert(window.n<1000&&report.n<1000);
 if(argc>1){std::ofstream f(argv[1],std::ios::binary);f.write((const char*)Serial.output.data(),Serial.output.size());}
 std::cout<<"PASS: silence, monotonic own-channel response, near-rail full output, contrast, gain matching, all motor mappings/frequencies, calibration rejection, EEPROM persistence/interrupted save, framing/backpressure and rollover\n";
}
