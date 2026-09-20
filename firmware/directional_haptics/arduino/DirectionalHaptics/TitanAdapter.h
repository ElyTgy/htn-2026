#pragma once
#include <stdint.h>
#include <stdio.h>
#include <avr/pgmspace.h>
// Verified command parameter order: official vhterminal.js (VH 2.0 vs 2.1).
// Measured on this kit's TITAN (VH 2.0.1.0), 2026-09-20:
//  - It plays ONE effect at a time. Effects for different channels queue and
//    run in turn; nothing in the stock serial interface overlaps them.
//  - A line ending in CR alone, arriving while an effect plays, leaves that CR
//    glued to the next line's CHNL ("Unknown command \rCHNL"), so the effect
//    plays on the previously selected motor. Ending lines with CR LF avoids it.
//  - A short effect costs its duration plus about 10 ms before the next starts.
// Input arrays use ADC order BACK, LEFT, RIGHT throughout this package.
inline uint8_t titanChannel(uint8_t adc){return adc==0?3:adc==1?1:2;}
inline uint16_t titanFrequency(uint8_t adc){return adc==0?160:adc==1?95:130;}
inline int titanEffect(char*out,unsigned cap,uint8_t profile,uint8_t adc,uint16_t permille,uint16_t duration){
 if((profile!=20&&profile!=21)||adc>2||permille>1000||duration>3000)return 0;
 if(profile==20)return snprintf_P(out,cap,PSTR("CHNL %u;vibrate %u %u.%03u %u 1 0;\r\n"),titanChannel(adc),titanFrequency(adc),permille/1000,permille%1000,duration);
 return snprintf_P(out,cap,PSTR("CHNL %u;vibrate %u %u.%03u %u 0;\r\n"),titanChannel(adc),duration,permille/1000,permille%1000,titanFrequency(adc));
}
// Motors therefore share time. One finite effect is sent per slot, to the next
// channel that wants output, so several active motors pulse in rotation at
// their own levels and TITAN never falls behind. 40 ms every 50 ms kept up
// with no backlog over 90 effects; 30 ms every 33 ms did not.
static const uint16_t TITAN_EFFECT_MS=40;
static const uint32_t TITAN_SLOT_US=50000UL;
static const uint16_t TITAN_TEST_MS=1000;
static const uint16_t TITAN_SLICED_TEST_MS=2000; // TEST 4: all three in rotation
static const uint16_t TITAN_GUARD_MS=25;         // after a long effect, before the next command
// Power-on cue: left, back, right, one finite effect each, starting after the
// delay. It plays before any profile is confirmed, so an unset profile falls
// back to VH 2.0, the version this kit's TITAN reported to HDI D (2.0.1.0).
static const uint16_t STARTUP_DELAY_MS=5000;
static const uint16_t STARTUP_EFFECT_MS=3000;
static const uint8_t STARTUP_FALLBACK_PROFILE=20;
