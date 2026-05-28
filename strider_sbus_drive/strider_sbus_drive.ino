#include <Servo.h>

// FlySky iBUS input on Arduino Mega 2560 pin 19 = Serial1 RX.
// iBUS is normal, non-inverted serial: 115200 baud, 8 data bits, no parity, 1 stop bit.
constexpr uint32_t IBUS_BAUD = 115200;
constexpr uint8_t IBUS_FRAME_SIZE = 32;
constexpr uint8_t IBUS_LENGTH_BYTE = 0x20;
constexpr uint8_t IBUS_COMMAND_BYTE = 0x40;
constexpr uint8_t IBUS_CHANNEL_COUNT = 14;

constexpr uint8_t PIN_MOTOR_FRONT_LEFT = 3;
constexpr uint8_t PIN_MOTOR_FRONT_RIGHT = 5;
constexpr uint8_t PIN_MOTOR_BACK_LEFT = 4;
constexpr uint8_t PIN_MOTOR_BACK_RIGHT = 2;

constexpr uint8_t CH_STEERING = 1;  // Channel 1: left/right.
constexpr uint8_t CH_THROTTLE = 2;  // Channel 2: forward/backward.
constexpr uint8_t CH_ARM = 7;       // Channel 7: arm switch.

constexpr bool SERIAL_DEBUG = false;

constexpr int IBUS_MIN = 1000;
constexpr int IBUS_MID = 1500;
constexpr int IBUS_MAX = 2000;
constexpr int STICK_DEADBAND_US = 35;

constexpr int PWM_STOP = 1500;
constexpr int PWM_MIN = 1000;
constexpr int PWM_MAX = 2000;
constexpr int ARM_THRESHOLD = 1200;

constexpr unsigned long FAILSAFE_TIMEOUT_MS = 120;
constexpr unsigned long SERIAL_PRINT_INTERVAL_MS = 100;

Servo motorFrontLeft;
Servo motorFrontRight;
Servo motorBackLeft;
Servo motorBackRight;

uint8_t ibusFrame[IBUS_FRAME_SIZE];
uint16_t channels[17];  // 1-indexed to match transmitter channel labels.
bool frameLost = true;
unsigned long lastGoodFrameMs = 0;
unsigned long lastSerialPrintMs = 0;

int normalizeChannel(uint16_t value) {
  value = constrain(value, IBUS_MIN, IBUS_MAX);
  long normalized = map(value, IBUS_MIN, IBUS_MAX, -500, 500);

  if (abs(normalized) <= STICK_DEADBAND_US) {
    return 0;
  }

  return static_cast<int>(normalized);
}

int mixToPwm(int throttle, int steering) {
  int mixed = constrain(throttle + steering, -500, 500);
  return PWM_STOP + mixed;
}

int reversePwm(int pwm) {
  return PWM_STOP - (pwm - PWM_STOP);
}

bool armSwitchIsOn() {
  return channels[CH_ARM] > ARM_THRESHOLD;
}

void writeAllMotors(int frontLeft, int frontRight, int backLeft, int backRight) {
  motorFrontLeft.writeMicroseconds(constrain(frontLeft, PWM_MIN, PWM_MAX));
  motorFrontRight.writeMicroseconds(constrain(frontRight, PWM_MIN, PWM_MAX));
  motorBackLeft.writeMicroseconds(constrain(backLeft, PWM_MIN, PWM_MAX));
  motorBackRight.writeMicroseconds(constrain(backRight, PWM_MIN, PWM_MAX));
}

void stopMotors() {
  writeAllMotors(PWM_STOP, PWM_STOP, PWM_STOP, PWM_STOP);
}

bool ibusChecksumIsValid(const uint8_t *frame) {
  uint16_t checksum = 0xFFFF;

  for (uint8_t i = 0; i < IBUS_FRAME_SIZE - 2; i++) {
    checksum -= frame[i];
  }

  uint16_t receivedChecksum = frame[IBUS_FRAME_SIZE - 2] | (frame[IBUS_FRAME_SIZE - 1] << 8);
  return checksum == receivedChecksum;
}

bool readIbusFrame() {
  static uint8_t buffer[IBUS_FRAME_SIZE];
  static uint8_t index = 0;

  while (Serial1.available() > 0) {
    uint8_t byteIn = Serial1.read();

    if (index == 0 && byteIn != IBUS_LENGTH_BYTE) {
      continue;
    }

    if (index == 1 && byteIn != IBUS_COMMAND_BYTE) {
      index = byteIn == IBUS_LENGTH_BYTE ? 1 : 0;
      buffer[0] = byteIn;
      continue;
    }

    buffer[index++] = byteIn;

    if (index == IBUS_FRAME_SIZE) {
      memcpy(ibusFrame, buffer, IBUS_FRAME_SIZE);
      index = 0;
      return ibusChecksumIsValid(ibusFrame);
    }
  }

  return false;
}

void decodeIbusFrame() {
  for (uint8_t channel = 1; channel <= IBUS_CHANNEL_COUNT; channel++) {
    uint8_t offset = 2 + ((channel - 1) * 2);
    channels[channel] = ibusFrame[offset] | (ibusFrame[offset + 1] << 8);
  }

  for (uint8_t channel = IBUS_CHANNEL_COUNT + 1; channel <= 16; channel++) {
    channels[channel] = 0;
  }

  frameLost = false;
}

void updateDrive() {
  bool signalTimedOut = millis() - lastGoodFrameMs > FAILSAFE_TIMEOUT_MS;

  if (signalTimedOut || frameLost || !armSwitchIsOn()) {
    frameLost = signalTimedOut;
    stopMotors();
    return;
  }

  int steering = normalizeChannel(channels[CH_STEERING]);
  int throttle = normalizeChannel(channels[CH_THROTTLE]);

  int leftPwm = mixToPwm(throttle, steering);
  int rightPwm = mixToPwm(throttle, -steering);

  writeAllMotors(leftPwm, reversePwm(rightPwm), leftPwm, reversePwm(rightPwm));
}

void printChannels() {
  if (!SERIAL_DEBUG) {
    return;
  }

  if (millis() - lastSerialPrintMs < SERIAL_PRINT_INTERVAL_MS) {
    return;
  }

  lastSerialPrintMs = millis();

  Serial.print("CH:");
  for (uint8_t i = 1; i <= 16; i++) {
    Serial.print(' ');
    Serial.print(i);
    Serial.print('=');
    Serial.print(channels[i]);
  }

  Serial.print(" armed=");
  Serial.print(armSwitchIsOn() ? "yes" : "no");
  Serial.print(" lost=");
  Serial.print(frameLost ? "yes" : "no");
  Serial.print(" ageMs=");
  Serial.println(millis() - lastGoodFrameMs);
}

void setup() {
  if (SERIAL_DEBUG) {
    Serial.begin(115200);
    Serial.println("STRIDER is booting up");
  }

  Serial1.begin(IBUS_BAUD, SERIAL_8N1);

  motorFrontLeft.attach(PIN_MOTOR_FRONT_LEFT, PWM_MIN, PWM_MAX);
  motorFrontRight.attach(PIN_MOTOR_FRONT_RIGHT, PWM_MIN, PWM_MAX);
  motorBackLeft.attach(PIN_MOTOR_BACK_LEFT, PWM_MIN, PWM_MAX);
  motorBackRight.attach(PIN_MOTOR_BACK_RIGHT, PWM_MIN, PWM_MAX);

  stopMotors();
}

void loop() {
  if (readIbusFrame()) {
    decodeIbusFrame();
    lastGoodFrameMs = millis();

    printChannels();
  }

  updateDrive();
}
