#pragma once
#include "Signal.h"
#include <stddef.h>
struct __attribute__((packed)) Saved{
 uint16_t magic,generation;uint8_t version;
 dh::Calibration calibration;
 uint8_t ceiling,profile,qualified,trim[3],sensitivity,contrast;
 uint16_t crc;uint8_t committed;
};
static_assert(sizeof(Saved)<=64,"EEPROM slot overflow");
inline bool savedValid(const Saved&s){
 dh::Calibration c;memcpy(&c,(const uint8_t*)&s+offsetof(Saved,calibration),sizeof(c));
 return s.magic==0x4433&&s.version==3&&s.committed==0xa5&&s.ceiling<=100&&(s.profile==0||s.profile==20||s.profile==21)&&s.qualified<=1&&(!s.qualified||s.profile)&&s.trim[0]>=25&&s.trim[0]<=100&&s.trim[1]>=25&&s.trim[1]<=100&&s.trim[2]>=25&&s.trim[2]<=100&&s.sensitivity>=1&&s.sensitivity<=5&&s.contrast<=30&&dh::valid(c)&&s.crc==dh::crc16((const uint8_t*)&s,offsetof(Saved,crc));
}
