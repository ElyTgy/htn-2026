/*
 * Caption Glasses two-sensor bridge, protocol S1.
 *
 *   SparkFun SEN-12642 ENVELOPE -> A0 (left)
 *   KY-038 AO                  -> A1 (right)
 *
 * The two boards do not produce comparable voltages. We therefore send a feature that
 * suits each board and let the Jetson calibrate them independently:
 *   - SEN-12642: mean envelope level over a 25 ms window
 *   - KY-038:    peak-to-peak analog waveform over the same window
 *
 * Output, 40 times/second at 115200 baud:
 *   S1,<sequence>,<millis>,<sen_mean>,<ky_peak_to_peak>
 */

const uint8_t SEN_ENVELOPE_PIN = A0;
const uint8_t KY_ANALOG_PIN = A1;
const unsigned long WINDOW_US = 25000UL;
const unsigned long BAUD = 115200UL;

uint32_t sequenceNumber = 0;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(BAUD);
  while (!Serial) {
    ;
  }
  Serial.println(F("# caption-glasses sound bridge S1"));
}

void loop() {
  const unsigned long started = micros();
  uint32_t envelopeSum = 0;
  uint16_t kyMin = 1023;
  uint16_t kyMax = 0;
  uint16_t samples = 0;

  while ((unsigned long)(micros() - started) < WINDOW_US) {
    const uint16_t envelope = analogRead(SEN_ENVELOPE_PIN);
    const uint16_t ky = analogRead(KY_ANALOG_PIN);
    envelopeSum += envelope;
    if (ky < kyMin) kyMin = ky;
    if (ky > kyMax) kyMax = ky;
    samples++;
  }

  const uint16_t envelopeMean = samples ? envelopeSum / samples : 0;
  const uint16_t kyPeakToPeak = kyMax - kyMin;

  Serial.print(F("S1,"));
  Serial.print(sequenceNumber++);
  Serial.print(',');
  Serial.print(millis());
  Serial.print(',');
  Serial.print(envelopeMean);
  Serial.print(',');
  Serial.println(kyPeakToPeak);

  // A slow heartbeat proves the firmware is alive without flickering at the sample rate.
  digitalWrite(LED_BUILTIN, (sequenceNumber / 20U) % 2U);
}
