#pragma once
#include "Arduino.h"
class SoftwareSerial {
public:
  std::vector<std::string> commands;bool listening=false;std::deque<char> input;
  SoftwareSerial(int,int){}void begin(long){}void stopListening(){listening=false;}void listen(){listening=true;}
  size_t write(const uint8_t *p,size_t n){commands.emplace_back((const char*)p,n);fakeUs+=n*87;return n;}
  void print(const char *s){write((const uint8_t*)s,strlen(s));}
  int available(){return input.size();}int read(){char c=input.front();input.pop_front();return c;}
};
