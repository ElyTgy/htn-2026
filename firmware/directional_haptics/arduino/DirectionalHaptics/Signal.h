#pragma once
#include <stdint.h>
#include <math.h>
#include <string.h>

namespace dh {
constexpr float FULL_SCALE_ADC = 970.0f; // ~95% of the Uno's 10-bit ADC range.
inline float clamp(float v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

struct Window {
  uint16_t n, raw[3], lo[3], hi[3];
  uint32_t sum[3];
  void clear() { n=0; for(uint8_t i=0;i<3;i++) {lo[i]=1023;hi[i]=0;sum[i]=0;} }
  void add(const uint16_t v[3]) {
    if(n>=1000) return;
    ++n;
    for(uint8_t i=0;i<3;i++) {
      raw[i]=v[i];sum[i]+=v[i];
      if(v[i]<lo[i]) lo[i]=v[i];
      if(v[i]>hi[i]) hi[i]=v[i];
    }
  }
  float mean(uint8_t i) const { return n ? float(sum[i])/n : 0; }
};
struct Moments {
  uint16_t n; float mean,m2;
  void clear() { n=0;mean=m2=0; }
  void add(float x) { ++n;float d=x-mean;mean+=d/n;m2+=d*(x-mean); }
  float sd() const { return n>1?sqrtf(m2/(n-1)):0; }
};
struct Calibration {
  float floor[3],close[3],reference[3],gain[3];
};
inline bool valid(const Calibration &c) {
  for(uint8_t i=0;i<3;i++) {
    if(!isfinite(c.floor[i]) || !isfinite(c.close[i]) || !isfinite(c.reference[i]) ||
       !isfinite(c.gain[i]) || c.close[i]<0 || c.close[i]>c.floor[i] ||
       c.reference[i]!=FULL_SCALE_ADC || c.reference[i]-c.floor[i]<100 ||
       c.gain[i]<0.5f || c.gain[i]>2.0f) return false;
  }
  return true;
}
inline float normalize(float x,float floor,float reference) {
  return reference-floor>=100 ? clamp((x-floor)/(reference-floor)) : 0;
}
// Fixed curves; no automatic gain control or normalization to recent peaks.
// Sensitivity 1..5 selects gamma .8,.6,.4,.3,.2. Full output requires x=1.
inline float shape(float x,uint8_t sensitivity) {
  if(x<=0) return 0;
  if(x>=1) return 1;
  float gamma=sensitivity==1?.8f:sensitivity==2?.6f:sensitivity==3?.4f:sensitivity==4?.3f:.2f;
  return powf(x,gamma);
}
struct Envelope {
  bool open;
  float normalized,corrected,shaped,smoothed;
  void clear() { open=false;normalized=corrected=shaped=smoothed=0; }
  // margin: loudness threshold in ADC counts above the calibrated noise floor.
  // Output is zero up to floor+margin and the range to full scale starts there.
  void measure(float x,const Calibration &c,uint8_t i,uint8_t sensitivity,float margin) {
    float opening=c.floor[i]+margin;
    if(open && x<=c.close[i]+margin) open=false;
    else if(!open && x>opening) open=true;
    normalized=open ? normalize(x,opening,c.reference[i]) : 0;
    corrected=normalized>0 ? (x-opening)*c.gain[i] : 0;
    shaped=shape(normalized,sensitivity);
  }
  void smooth(float target,uint32_t dt) {
    // Hard silence gate. Release smoothing applies while above the floor;
    // it must not leave a commanded vibration after the gate closes.
    if(normalized==0) { smoothed=0;return; }
    float tau=target>smoothed?5000.0f:50000.0f;
    smoothed+=(target-smoothed)*(float(dt)/(tau+dt));
    if(target==1 && smoothed>.999f) smoothed=1;
  }
};
inline void process(Envelope e[3],const float amplitudes[3],const Calibration &c,
                    uint32_t dt,uint8_t sensitivity,uint8_t contrastTenths,uint8_t thresholdCounts=0) {
  float loudest=0;
  for(uint8_t i=0;i<3;i++) {
    e[i].measure(amplitudes[i],c,i,sensitivity,thresholdCounts);
    if(e[i].corrected>loudest) loudest=e[i].corrected;
  }
  for(uint8_t i=0;i<3;i++) {
    float target=e[i].shaped;
    if(target>0 && loudest>0 && contrastTenths) {
      // Suppress quieter sides without boosting the loudest or activating a
      // silent mic. Fade contrast at the ADC ceiling so loud inputs reach max.
      float headroom=1-e[i].normalized;
      float exponent=.1f*contrastTenths*headroom*headroom;
      target*=powf(clamp(e[i].corrected/loudest),exponent);
    }
    e[i].smooth(clamp(target),dt);
  }
}
inline bool matchGains(Calibration &candidate,const float levels[3]) {
  float span[3];
  for(uint8_t i=0;i<3;i++) {
    span[i]=levels[i]-candidate.floor[i];
    if(!isfinite(span[i]) || span[i]<4 || levels[i]>=1021) return false;
  }
  float a=span[0],b=span[1],c=span[2];
  float median=fmaxf(fminf(a,b),fminf(fmaxf(a,b),c));
  for(uint8_t i=0;i<3;i++) {
    float g=median/span[i];
    if(g<.5f || g>2) return false;
  }
  for(uint8_t i=0;i<3;i++) candidate.gain[i]=median/span[i];
  return true;
}
inline uint16_t crc16(const uint8_t*p,uint16_t n) {
  uint16_t c=0xffff;
  while(n--) {c^=(uint16_t)*p++<<8;for(uint8_t k=0;k<8;k++)c=c&0x8000?(c<<1)^0x1021:c<<1;}
  return c;
}
}
