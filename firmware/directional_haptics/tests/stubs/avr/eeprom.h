#pragma once
#include <stdint.h>
extern uint32_t fakeUs,eepromReadyAt;
inline bool eeprom_is_ready(){return (int32_t)(fakeUs-eepromReadyAt)>=0;}
