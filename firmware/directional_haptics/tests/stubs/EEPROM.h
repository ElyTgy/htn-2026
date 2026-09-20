#pragma once
#include "Arduino.h"
extern uint32_t eepromReadyAt;
struct EEPROMMock {
  uint8_t data[1024];EEPROMMock(){memset(data,255,sizeof(data));}
  template<class T> void get(int at,T&out){memcpy(&out,data+at,sizeof(T));}
  void update(int at,uint8_t v){data[at]=v;eepromReadyAt=fakeUs+3400;}
};
extern EEPROMMock EEPROM;
