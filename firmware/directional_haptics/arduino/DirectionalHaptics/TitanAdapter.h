#pragma once
#include <stdint.h>
#include <stdio.h>
#include <avr/pgmspace.h>
// Verified command parameter order: official vhterminal.js (VH 2.0 vs 2.1).
// Runtime header playback and concurrent effects must be physically qualified.
// Input arrays use ADC order BACK, LEFT, RIGHT throughout this package.
inline uint8_t titanChannel(uint8_t adc){return adc==0?3:adc==1?1:2;}
inline uint16_t titanFrequency(uint8_t adc){return adc==0?160:adc==1?95:130;}
inline int titanEffect(char*out,unsigned cap,uint8_t profile,uint8_t adc,uint16_t permille,uint16_t duration){
 if((profile!=20&&profile!=21)||adc>2||permille>1000||duration>3000)return 0;
 if(profile==20)return snprintf_P(out,cap,PSTR("CHNL %u;vibrate %u %u.%03u %u 1 0;\r"),titanChannel(adc),titanFrequency(adc),permille/1000,permille%1000,duration);
 return snprintf_P(out,cap,PSTR("CHNL %u;vibrate %u %u.%03u %u 0;\r"),titanChannel(adc),duration,permille/1000,permille%1000,titanFrequency(adc));
}
// Changed levels can be transmitted after 8 ms; unchanged levels are renewed
// every 25 ms with a finite 30 ms effect. This bounds stable UART load while
// preserving a sub-20-ms electrical-change target for a changed channel.
static const uint32_t TITAN_CHANGE_US=8000UL;
static const uint32_t TITAN_REFRESH_US=25000UL;
static const uint16_t TITAN_CHANGE_PERMILLE=10;
static const uint16_t TITAN_EFFECT_MS=30;
static const uint16_t TITAN_TEST_MS=1000;
// Power-on cue: left, back, right, one finite effect each, starting after the
// delay. It plays before any profile is confirmed, so an unset profile falls
// back to VH 2.0, the version this kit's TITAN reported to HDI D (2.0.1.0).
static const uint16_t STARTUP_DELAY_MS=5000;
static const uint16_t STARTUP_EFFECT_MS=3000;
static const uint8_t STARTUP_FALLBACK_PROFILE=20;
