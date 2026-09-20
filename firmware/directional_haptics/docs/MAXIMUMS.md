# Microphone and motor maximums

“Maximum” in this firmware means the largest **commanded intensity**. It is not a measurement of motor force, acceleration, or perceived strength.

## Connected channels

| Position | Microphone | TITAN output | Motor | Resonant command frequency | Maximum command | Bench sensation note |
| --- | --- | --- | --- | ---: | ---: | --- |
| Left | A1 | L, channel 1 | Red DRAKE LF | 95 Hz | 100% (`1.000`) | Strongest of the three according to the wearer |
| Right | A2 | R, channel 2 | Yellow DRAKE MF | 130 Hz | 100% (`1.000`) | Weaker than the red LF motor |
| Back | A0 | M, channel 3 | White DRAKE HF | 160 Hz | 100% (`1.000`) | Also felt weaker than the red LF motor |

The black DRAKE LFi is currently disconnected. It has no assigned channel, frequency, or validated maximum in this revision.

All three connected motors have the same firmware limit: 100%. The code never boosts the yellow or white motors beyond `1.000`. If the red motor dominates, reduce **left trim (`TRIM1`)**; the other two cannot be increased above their 100% command limit. Trims default to 100%.

For stock Vector Haptics 2.0, the maximum two-second bench commands are:

```text
Left/red:    CHNL 1;vibrate 95 1.000 2000 1 0;
Right/yellow: CHNL 2;vibrate 130 1.000 2000 1 0;
Back/white:  CHNL 3;vibrate 160 1.000 2000 1 0;
```

Earlier direct-USB testing was reported to actuate each motor at these 100% levels. The later final left-channel check wrote the complete command but received no TITAN acknowledgment, so that later check remains inconclusive and is not additional proof of physical output.

## Microphone level that requests maximum

All three SparkFun ENVELOPE inputs use **970 ADC counts** as their full-output point:

| Position | Input | Zero-output point | Full-output point |
| --- | --- | --- | ---: |
| Back | A0 | Its separately calibrated noise-floor gate | 970 counts |
| Left | A1 | Its separately calibrated noise-floor gate | 970 counts |
| Right | A2 | Its separately calibrated noise-floor gate | 970 counts |

The Uno ADC range is 0–1023. Values at or above 970 clamp to 100% before the global ceiling and motor trim are applied. Each microphone's quiet floor is measured independently and will change with the sensor and environment; it is deliberately not a fixed number.

For microphone `i`, the basic normalized input is:

```text
normalized[i] = clamp((envelope[i] - floor[i]) / (970 - floor[i]), 0, 1)
```

Sensitivity, directional contrast, smoothing, the global ceiling, and motor trim are applied afterward. A 100% microphone-side result therefore produces less than a 100% motor command when the ceiling or that motor's trim is below 100%.

The one-second overlap qualification test is intentionally unequal—left 40%, back 70%, right 100%—so the weaker MF/HF motors are easier to distinguish. Those overlap values are test levels, not their maximums.
