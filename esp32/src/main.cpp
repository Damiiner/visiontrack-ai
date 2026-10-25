#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_PASS = "";
const char *MQTT_SERVER = "broker.hivemq.com";
const int MQTT_PORT = 1883;
const char *TOPIC = "visiontrack/appollo/events"; // must match detect.py

const int LED_PIN = 26;
const int BUZZER_PIN = 27;
const int SERVO_PIN = 18;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_SSD1306 display(128, 64, &Wire, -1);
Servo servo;

int currentPersons = 0;
bool alarmOn = false;
unsigned long lastAlarmBeep = 0;
unsigned long lastMsg = 0;

void beep(int ms)
{
    unsigned long end = millis() + ms;
    while (millis() < end)
    {
        digitalWrite(BUZZER_PIN, HIGH);
        delayMicroseconds(500);
        digitalWrite(BUZZER_PIN, LOW);
        delayMicroseconds(500);
    }
}

void showStatus(int persons, int inCount, int outCount, bool alarm)
{
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.print("VisionTrack AI");
    if (alarm)
    {
        display.setTextSize(2);
        display.setCursor(0, 22);
        display.print("ZONE ALERT");
    }
    else
    {
        display.setTextSize(3);
        display.setCursor(0, 20);
        display.print(persons);
        display.setTextSize(1);
        display.setCursor(40, 28);
        display.print(persons == 1 ? "person" : "persons");
    }
    display.setTextSize(1);
    display.setCursor(0, 54);
    display.printf("IN:%d  OUT:%d", inCount, outCount);
    display.display();
}

void onMessage(char *topic, byte *payload, unsigned int length)
{
    JsonDocument doc;
    if (deserializeJson(doc, payload, length))
        return;

    int persons = doc["persons"] | 0;
    int inCount = doc["in_count"] | 0;
    int outCount = doc["out_count"] | 0;
    float x = doc["x"] | 0.5;
    bool alarm = doc["alarm"] | false;

    if (alarm && !alarmOn)
        lastAlarmBeep = 0; // beep immediately when the alarm starts
    alarmOn = alarm;
    currentPersons = persons;
    lastMsg = millis();

    if (persons > 0)
    {
        int angle = constrain((int)(x * 180), 0, 180);
        servo.write(angle);
    }

    showStatus(persons, inCount, outCount, alarm);
    Serial.printf("persons=%d  in=%d  out=%d  x=%.2f  alarm=%d\r\n",
                  persons, inCount, outCount, x, alarm);
}

void reconnect()
{
    while (!mqtt.connected())
    {
        String clientId = "visiontrack-esp32-" + String(random(0xffff), HEX);
        if (mqtt.connect(clientId.c_str()))
        {
            mqtt.subscribe(TOPIC);
            Serial.print("MQTT connected\r\n");
        }
        else
        {
            delay(2000);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);

    Wire.begin(21, 22);
    display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(0, 10);
    display.print("VisionTrack");
    display.setCursor(0, 32);
    display.print("AI");
    display.display();

    ESP32PWM::allocateTimer(0);
    servo.setPeriodHertz(50);
    servo.attach(SERVO_PIN, 500, 2400);
    servo.write(90);

    Serial.print("Connecting to WiFi");
    WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(250);
        Serial.print(".");
    }
    Serial.print("\r\nWiFi connected\r\n");

    mqtt.setServer(MQTT_SERVER, MQTT_PORT);
    mqtt.setCallback(onMessage);
}

void loop()
{
    if (!mqtt.connected())
        reconnect();
    mqtt.loop();

    unsigned long now = millis();

    // If the detector stops sending, clear the alarm after 5 seconds
    if (alarmOn && now - lastMsg > 5000)
        alarmOn = false;

    if (alarmOn)
    {
        digitalWrite(LED_PIN, (now / 250) % 2); // blink
        if (now - lastAlarmBeep > 1000)
        { // beep once per second
            beep(200);
            lastAlarmBeep = now;
        }
    }
    else
    {
        digitalWrite(LED_PIN, currentPersons > 0 ? HIGH : LOW);
    }
}