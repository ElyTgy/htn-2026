#pragma once
#include <stdint.h>
#include <stddef.h>
#include <cstring>
#include <cstdio>
#include <algorithm>
#include <deque>
#include <vector>
#include <string>
#define F(x) x
#define A0 14
#define A1 15
using std::min;
extern uint32_t fakeUs;
extern int source[3];
inline uint32_t micros(){return fakeUs;}
inline uint32_t millis(){return fakeUs/1000;}
inline int analogRead(int pin){fakeUs+=104;return source[pin-A0];}
struct USBMock {
  std::deque<char> input;std::vector<uint8_t> output;int free=63;
  void begin(long){} int available(){return input.size();}int read(){char c=input.front();input.pop_front();return c;}
  int availableForWrite(){return free;}
  size_t write(const uint8_t*p,size_t n){output.insert(output.end(),p,p+n);return n;}
};
extern USBMock Serial;
