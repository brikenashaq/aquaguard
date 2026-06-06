#define BLYNK_TEMPLATE_ID "TMPL4G27hi3ec"
#define BLYNK_TEMPLATE_NAME "Smart Aquarium"
#define BLYNK_AUTH_TOKEN "QmtbID-9NDC9aHgZ4GzohdG-B1q_vk8Q"

#include <WiFi.h>
#include <BlynkSimpleEsp32.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <time.h>

char ssid[] = "Brikena's Network";
char pass[] = "123412345";

// InfluxDB
String influxUrl = "https://eu-central-1-1.aws.cloud2.influxdata.com/api/v2/write?org=Aquarium&bucket=aquarium&precision=s";
String influxToken = "yJZ-GtJCnbRwN_BU6Jn2chTYOh_Z3s05OHg0Cvcgm3aXM5vuKM9OBcMthLWpGsOySmeQ-OCvjt9K2c4LZn-R2w==";

// ===== TEMPERATURE =====
bool highAlertSent = false;
bool lowAlertSent = false;

#define TEMP_PIN 4
OneWire oneWire(TEMP_PIN);
DallasTemperature sensors(&oneWire);

// ===== SERVO =====
Servo feeder;
#define SERVO_PIN 19
bool isFeeding = false;

// ===== ULTRASONIC =====
#define TRIG_PIN 5
#define ECHO_PIN 18
float waterLevel = 0;
bool lowWaterAlertSent = false;

BlynkTimer timer;

// ===== TEMPERATURE =====
void sendTemperature() {
  sensors.requestTemperatures();
  float temperature = sensors.getTempCByIndex(0);

  if (temperature == DEVICE_DISCONNECTED_C) {
    Serial.println("❌ Temperature sensor disconnected!");
    return;
  }

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" °C");

  Blynk.virtualWrite(V1, temperature);

  if (WiFi.status() == WL_CONNECTED) {
    sendToInflux(temperature);
  }

  // High temp alert — resets at 26 to avoid repeated firing
  if (temperature > 28 && !highAlertSent) {
    Blynk.logEvent("high_temp", "🔥 Water too HOT!");
    highAlertSent = true;
  }
  if (temperature <= 26) highAlertSent = false;

  // Low temp alert — resets at 19 to avoid repeated firing
  if (temperature < 17 && !lowAlertSent) {
    Blynk.logEvent("low_temp", "❄️ Water too COLD!");
    lowAlertSent = true;
  }
  if (temperature >= 19) lowAlertSent = false;
}

void sendToInflux(float temp) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi not connected - skipping Influx");
    return;
  }

  HTTPClient http;
  http.setTimeout(1500);

  if (!http.begin(influxUrl)) {
    Serial.println("❌ HTTP begin failed");
    return;
  }

  http.addHeader("Authorization", "Token " + influxToken);
  http.addHeader("Content-Type", "text/plain");

  String data = "temperature value=" + String(temp);
  int httpResponseCode = http.POST(data);

  Serial.print("Influx response: ");
  Serial.println(httpResponseCode);

  http.end();
}

// ===== WATER LEVEL =====
void sendWaterLevel() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  float distance = duration * 0.034 / 2;

  if (distance <= 0 || distance >= 90) {
    Serial.println("⚠️ Invalid water level reading - skipping");
    return;
  }

  waterLevel = distance;
  Serial.print("Water distance: ");
  Serial.print(waterLevel);
  Serial.println(" cm");

  Blynk.virtualWrite(V2, waterLevel);

  if (WiFi.status() == WL_CONNECTED) {
    sendWaterLevelToInflux(waterLevel);
  }

  // Alert when distance too large = water too low
  // Resets when water level recovers
  if (waterLevel > 15 && !lowWaterAlertSent) {
    Blynk.logEvent("low_water", "💧 Water level too LOW!");
    lowWaterAlertSent = true;
  }
  if (waterLevel <= 12) lowWaterAlertSent = false;
}

void sendWaterLevelToInflux(float level) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi not connected - skipping Influx");
    return;
  }

  HTTPClient http;
  http.setTimeout(1500);

  if (!http.begin(influxUrl)) {
    Serial.println("❌ HTTP begin failed");
    return;
  }

  http.addHeader("Authorization", "Token " + influxToken);
  http.addHeader("Content-Type", "text/plain");

  String data = "water_level value=" + String(level);
  int httpResponseCode = http.POST(data);

  Serial.print("Water Level Influx: ");
  Serial.println(httpResponseCode);

  http.end();
}

// ===== FEEDING =====
void sendFeedingToInflux() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi not connected - skipping Influx");
    return;
  }

  HTTPClient http;
  http.setTimeout(2000);
  http.begin(influxUrl);
  http.addHeader("Authorization", "Token " + influxToken);
  http.addHeader("Content-Type", "text/plain");

  String data = "feeding value=1";
  int code = http.POST(data);

  Serial.print("Feeding Influx: ");
  Serial.println(code);

  http.end();
}

void sendFeedingTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Time failed");
    return;
  }

  char timeString[30];
  strftime(timeString, sizeof(timeString), "%H:%M", &timeinfo);

  Serial.print("Feeding time sent to Blynk: ");
  Serial.println(timeString);

  Blynk.virtualWrite(V3, timeString);
}

void triggerFeeding() {
  isFeeding = true;
  feeder.write(90);
  sendFeedingTime();
  sendFeedingToInflux();

  timer.setTimeout(1000L, []() {
    feeder.write(0);
    isFeeding = false;
    Serial.println("✅ Feeding complete");
  });
}

void checkFeedingTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Failed to get time");
    return;
  }

  int hour = timeinfo.tm_hour;
  int minute = timeinfo.tm_min;

  Serial.printf("Time: %02d:%02d\n", hour, minute);

  if (hour == 7 && minute == 30 && !isFeeding) {
    Serial.println("⏰ Automatic feeding!");
    triggerFeeding();
  }
}

// ===== BLYNK BUTTON =====
BLYNK_WRITE(V0) {
  int value = param.asInt();

  if (value == 1 && !isFeeding) {
    Serial.println("🐟 Manual feeding triggered!");
    triggerFeeding();
  }
}

// ===== SETUP =====
void setup() {
  Serial.begin(115200);

  sensors.begin();

  feeder.attach(SERVO_PIN);
  feeder.write(0);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  Blynk.begin(BLYNK_AUTH_TOKEN, ssid, pass);

  // UTC+2 for North Macedonia (summer/CEST)
  configTime(7200, 0, "pool.ntp.org", "time.nist.gov");

  timer.setInterval(10000L, sendTemperature);
  timer.setInterval(10000L, checkFeedingTime);
  timer.setInterval(10000L, sendWaterLevel);

  Serial.println("✅ AquaGuard ESP32 ready!");
}

// ===== LOOP =====
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi lost - reconnecting...");
    WiFi.begin(ssid, pass);
    delay(500);
  }

  if (!Blynk.connected()) {
    Blynk.connect();
  }

  Blynk.run();
  timer.run();
}