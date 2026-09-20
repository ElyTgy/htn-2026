#pragma once
#include <stdint.h>
struct __attribute__((packed)) ChannelTelemetry{
 uint16_t raw,low,high,meanQ4,amplitudeQ4,peakQ4,normalized,smoothed,desired,sent,floorQ4,referenceQ4,closeQ4;
};
struct __attribute__((packed)) Telemetry{
 uint32_t ms,sequence;
 uint16_t rate,gapUs,txUs,updateRate,dropped,flags,commandSequence,windowUs,samples,onsetLatencyUs;
 uint8_t phase,progress,profile,ceiling,testMask,trim[3];
 ChannelTelemetry channel[3];
};
static_assert(sizeof(Telemetry)==114,"wire schema mismatch");
// DH magic, length, (version=3)<<4|type, payload, CRC16(length..payload).
// Type 1 telemetry; type 2 ASCII events: '<id> OK|ERR|TITAN <message>'.

struct __attribute__((packed)) SettingsTelemetry {
 uint8_t sensitivity,contrast;uint16_t fullScale,gain[3],frequency[3];uint8_t threshold;
};
static_assert(sizeof(SettingsTelemetry)==17,"settings schema mismatch");
