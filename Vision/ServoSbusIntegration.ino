#include <Servo.h>

/*
 * ServoSbusIntegration.ino
 *
 * Combined sketch for the Vision folder that integrates the ServoTest
 * serial command protocol with the Strider SBUS drive logic.
 *
 * - Serial: framed serial commands for servo control using the same packet
 *   format as ServoTest.ino.
 * - Serial1: FlySky iBUS receiver input for drive motor control.
 *
 * Supported commands on Serial:
 *   S <angle>  -> set servo angle from 0 to 180
 *   B          -> re-center servo to 90 degrees
 */

constexpr unsigned long SERIAL_BAUD = 115200;
constexpr uint8_t START_BYTE = 0x02;
constexpr uint8_t END_BYTE = 0x03;
constexpr int MY_SERIAL_BUFFER_SIZE = 32;

constexpr uint8_t SERVO_PIN = 22;
constexpr uint8_t SERVO_MIN_ANGLE = 0;
constexpr uint8_t SERVO_MAX_ANGLE = 180;
constexpr uint8_t SERVO_CENTER_ANGLE = 90;

constexpr uint32_t IBUS_BAUD = 115200;
constexpr uint8_t IBUS_FRAME_SIZE = 32;
constexpr uint8_t IBUS_LENGTH_BYTE = 0x20;
constexpr uint8_t IBUS_COMMAND_BYTE = 0x40;
constexpr uint8_t IBUS_CHANNEL_COUNT = 14;

constexpr uint8_t PIN_MOTOR_FRONT_LEFT = 3;
constexpr uint8_t PIN_MOTOR_FRONT_RIGHT = 5;
constexpr uint8_t PIN_MOTOR_BACK_LEFT = 4;
constexpr uint8_t PIN_MOTOR_BACK_RIGHT = 2;

constexpr uint8_t CH_STEERING = 1;
constexpr uint8_t CH_THROTTLE = 2;
constexpr uint8_t CH_ARM = 7;

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

Servo testServo;
Servo motorFrontLeft;
Servo motorFrontRight;
Servo motorBackLeft;
Servo motorBackRight;

bool receiving_message = false;
bool serial_connection_established = false;
int serial_index = 0;
int expected_length = -1;
byte serial_buffer[MY_SERIAL_BUFFER_SIZE];
int current_servo_angle = SERVO_CENTER_ANGLE;
unsigned long last_message_time = 0;

uint8_t ibusFrame[IBUS_FRAME_SIZE];
uint16_t channels[17];
bool frameLost = true;
unsigned long lastGoodFrameMs = 0;
unsigned long lastSerialPrintMs = 0;

void processSerialBuffer();
void processMessage(byte *data, int length);
void sendSerialFeedback(char command, uint8_t *data, size_t dataLen);
void setServoAngle(int angle);

bool readIbusFrame();
void decodeIbusFrame();
int normalizeChannel(uint16_t value);
int mixToPwm(int throttle, int steering);
int reversePwm(int pwm);
bool armSwitchIsOn();
void writeAllMotors(int frontLeft, int frontRight, int backLeft, int backRight);
void stopMotors();
void updateDrive();
void printChannels();
bool ibusChecksumIsValid(const uint8_t *frame);

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.flush();

  Serial1.begin(IBUS_BAUD, SERIAL_8N1);

  testServo.attach(SERVO_PIN);
  setServoAngle(SERVO_CENTER_ANGLE);

  motorFrontLeft.attach(PIN_MOTOR_FRONT_LEFT, PWM_MIN, PWM_MAX);
  motorFrontRight.attach(PIN_MOTOR_FRONT_RIGHT, PWM_MIN, PWM_MAX);
  motorBackLeft.attach(PIN_MOTOR_BACK_LEFT, PWM_MIN, PWM_MAX);
  motorBackRight.attach(PIN_MOTOR_BACK_RIGHT, PWM_MIN, PWM_MAX);

  stopMotors();

  Serial.println("ServoSbusIntegration ready.");
  Serial.println("Use framed serial packets <0x02, length, command, data..., 0x03>.");
}

void loop() {
  processSerialBuffer();

  if (readIbusFrame()) {
    decodeIbusFrame();
    lastGoodFrameMs = millis();
    printChannels();
  }

  updateDrive();
}

void processMessage(byte *data, int length) {
  if (length <= 0) {
    return;
  }

  const char type = static_cast<char>(data[0]);
  bool cmd_triggered = true;

  switch (type) {
    case 'S': {
      if (length < 2) {
        Serial.println("Servo command missing angle byte.");
        cmd_triggered = false;
        break;
      }

      int requested_angle = static_cast<uint8_t>(data[1]);
      if (requested_angle == 0 || requested_angle == 1) {
        requested_angle = requested_angle == 0 ? SERVO_MIN_ANGLE : SERVO_MAX_ANGLE;
      }

      setServoAngle(requested_angle);

      uint8_t reply_data[] = {static_cast<uint8_t>(current_servo_angle)};
      sendSerialFeedback('S', reply_data, 1);

      Serial.print("Servo angle set to: ");
      Serial.println(current_servo_angle);
      break;
    }

    case 'B': {
      setServoAngle(SERVO_CENTER_ANGLE);

      uint8_t reply_data[] = {static_cast<uint8_t>(current_servo_angle)};
      sendSerialFeedback('S', reply_data, 1);

      Serial.println("Servo centered to 90.");
      break;
    }

    default:
      Serial.print("Unknown message type: ");
      Serial.println(type);
      cmd_triggered = false;
      break;
  }

  if (cmd_triggered) {
    last_message_time = millis();
    if (!serial_connection_established) {
      serial_connection_established = true;
      Serial.println("Serial command stream detected.");
    }
  }
}

void setServoAngle(int angle) {
  current_servo_angle = constrain(angle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
  testServo.write(current_servo_angle);
}

void sendSerialFeedback(char command, uint8_t *data, size_t dataLen) {
  uint8_t buf[16];
  size_t idx = 0;

  buf[idx++] = START_BYTE;
  buf[idx++] = dataLen + 1;
  buf[idx++] = static_cast<uint8_t>(command);

  for (size_t i = 0; i < dataLen; i++) {
    buf[idx++] = data[i];
  }

  buf[idx++] = END_BYTE;
  Serial.write(buf, idx);
}

void processSerialBuffer() {
  while (Serial.available() > 0) {
    byte b = Serial.read();

    if (!receiving_message) {
      if (b == START_BYTE) {
        receiving_message = true;
        serial_index = 0;
        expected_length = -1;
      }
      continue;
    }

    if (expected_length == -1) {
      expected_length = b;
      if (expected_length <= 0 || expected_length > MY_SERIAL_BUFFER_SIZE) {
        receiving_message = false;
      }
      continue;
    }

    serial_buffer[serial_index++] = b;

    if (serial_index == expected_length + 1) {
      if (serial_buffer[serial_index - 1] == END_BYTE) {
        processMessage(serial_buffer, expected_length);
      } else {
        Serial.println("End byte not found.");
      }
      receiving_message = false;
    } else if (serial_index >= MY_SERIAL_BUFFER_SIZE) {
      receiving_message = false;
    }
  }
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
