#include <Servo.h>

/*
 * ServoTest.ino
 *
 * Servo-only test sketch derived from the serial command structure used by
 * system_control.ino. This keeps the same framed serial protocol so the GUI
 * bridge can send `S` commands exactly the same way it does for the full robot.
 *
 * Supported commands:
 *   S <angle>  -> set servo angle from 0 to 180
 *   B          -> re-center servo to 90 degrees
 *
 * Serial packet format:
 *   <0x02, length, command, data..., 0x03>
 */

constexpr unsigned long SERIAL_BAUD = 115200;
constexpr uint8_t START_BYTE = 0x02;
constexpr uint8_t END_BYTE = 0x03;
constexpr int MY_SERIAL_BUFFER_SIZE = 32;

constexpr uint8_t SERVO_PIN = 22;
constexpr uint8_t SERVO_MIN_ANGLE = 0;
constexpr uint8_t SERVO_MAX_ANGLE = 180;
constexpr uint8_t SERVO_CENTER_ANGLE = 90;

Servo testServo;

bool receiving_message = false;
bool serial_connection_established = false;
int serial_index = 0;
int expected_length = -1;
byte serial_buffer[MY_SERIAL_BUFFER_SIZE];
int current_servo_angle = SERVO_CENTER_ANGLE;
unsigned long last_message_time = 0;

void processSerialBuffer();
void processMessage(byte *data, int length);
void sendSerialFeedback(char command, uint8_t *data, size_t dataLen);
void setServoAngle(int angle);

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.flush();

  testServo.attach(SERVO_PIN);
  setServoAngle(SERVO_CENTER_ANGLE);

  Serial.println("ServoTest ready.");
  Serial.println("Use framed serial packets like <0x02, 0x02, 'S', angle, 0x03>.");
}

void loop() {
  processSerialBuffer();
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

      // Keep compatibility with older 0/1 latch-style servo tests while also
      // supporting the full 0-180 angle values sent by the current GUI bridge.
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
