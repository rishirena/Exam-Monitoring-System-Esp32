/*
 * ESP32 Exam Monitor — Combined (Serial + WiFi + Self-Test)
 * Upload with Arduino IDE → Board: "ESP32 Dev Module", Baud: 115200
 *
 * Wiring:
 *   Green LED  → GPIO 19 (220Ω)    Yellow LED → GPIO 18 (220Ω)
 *   Red LED    → GPIO 23 (220Ω)    Buzzer     → GPIO 25
 *   LCD SDA    → GPIO 21 (optional) LCD SCL   → GPIO 22 (optional)
 */

#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>

// Uncomment if you have a 16x2 I2C LCD:
// #include <LiquidCrystal_I2C.h>
// LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- CONFIGURATION ----
const bool USE_WIFI = true;  // false = USB serial, true = WiFi
const char* WIFI_SSID     = "IQOO";
const char* WIFI_PASSWORD = "12345678";

// ---- PINS ----
const int GREEN_LED_PIN  = 19;
const int YELLOW_LED_PIN = 18;
const int RED_LED_PIN    = 23;
const int BUZZER_PIN     = 15;

// ---- STATE ----
String currentStatus = "SAFE";
int    currentScore  = 0;
unsigned long lastBuzzTime = 0;
bool   buzzerOn = false;

WebServer server(80);

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  runHardwareTest();

  // lcd.init();
  // lcd.backlight();

  if (USE_WIFI) {
    startWiFiMode();
  } else {
    Serial.println("Mode: USB SERIAL");
    Serial.println("Send: SAFE,12 or ALERT,85");
  }

  updateOutputs();
}

void loop() {
  if (USE_WIFI) {
    server.handleClient();
    if (WiFi.status() != WL_CONNECTED) {
      connectToWiFi();
    }
  } else {
    if (Serial.available()) {
      String line = Serial.readStringUntil('\n');
      line.trim();
      if (line.length() > 0) {
        parseMessage(line);
        updateOutputs();
      }
    }
  }

  // Buzzer pulses during ALERT
  if (currentStatus == "ALERT") {
    unsigned long now = millis();
    if (now - lastBuzzTime > 500) {
      buzzerOn = !buzzerOn;
      digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
      lastBuzzTime = now;
    }
  }

  delay(10);
}

// ---- HARDWARE SELF-TEST (runs once on boot) ----

void runHardwareTest() {
  Serial.println("--- Hardware Self-Test ---");

  Wire.begin(21, 22);
  scanI2C();

  digitalWrite(GREEN_LED_PIN, HIGH);  delay(400);  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(YELLOW_LED_PIN, HIGH); delay(400);  digitalWrite(YELLOW_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);    delay(400);  digitalWrite(RED_LED_PIN, LOW);

  digitalWrite(BUZZER_PIN, HIGH); delay(200); digitalWrite(BUZZER_PIN, LOW);

  Serial.println("Self-test complete!\n");
}

void scanI2C() {
  Serial.println("Scanning I2C...");
  int found = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("  Found: 0x");
      if (addr < 16) Serial.print("0");
      Serial.print(addr, HEX);
      if (addr == 0x27 || addr == 0x3F) Serial.print(" (LCD)");
      Serial.println();
      found++;
    }
  }
  if (found == 0) Serial.println("  No I2C devices (normal if no LCD).");
}

// ---- WIFI MODE ----

void startWiFiMode() {
  Serial.println("Mode: WIFI");
  connectToWiFi();
  server.on("/status", HTTP_POST, handleStatusPost);
  server.on("/", HTTP_GET, handleRoot);
  server.begin();
}

void connectToWiFi() {
  Serial.print("Connecting to: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\nConnected! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi FAILED — check SSID/password.");
  }
}

void handleRoot() {
  String html = "<h1>ESP32 Exam Monitor</h1>";
  html += "<p>Status: <b>" + currentStatus + "</b></p>";
  html += "<p>Score: <b>" + String(currentScore) + "%</b></p>";
  server.send(200, "text/html", html);
}

void handleStatusPost() {
  String body = server.arg("plain");
  body.trim();
  if (body.length() == 0) { server.send(400, "text/plain", "Empty body"); return; }

  int ci = body.indexOf(',');
  if (ci < 0) { server.send(400, "text/plain", "Bad format"); return; }

  currentStatus = body.substring(0, ci);
  currentScore  = body.substring(ci + 1).toInt();
  updateOutputs();
  server.send(200, "text/plain", "OK");
}

// ---- MESSAGE PARSING (serial mode) ----

void parseMessage(String msg) {
  int ci = msg.indexOf(',');
  if (ci < 0) return;
  currentStatus = msg.substring(0, ci);
  currentScore  = msg.substring(ci + 1).toInt();
}

// ---- OUTPUT CONTROL ----

void updateOutputs() {
  digitalWrite(GREEN_LED_PIN,  currentStatus == "SAFE"    ? HIGH : LOW);
  digitalWrite(YELLOW_LED_PIN, currentStatus == "WARNING" ? HIGH : LOW);
  digitalWrite(RED_LED_PIN,    currentStatus == "ALERT"   ? HIGH : LOW);

  if (currentStatus != "ALERT") {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerOn = false;
  }

  // LCD (uncomment if you have one):
  // lcd.clear();
  // lcd.setCursor(0, 0);
  // lcd.print(currentStatus == "ALERT" ? "!! CHEATING !!" : "Status: " + currentStatus);
  // lcd.setCursor(0, 1);
  // lcd.print("Risk: " + String(currentScore) + "%");
}
