# VisionTrack AI

A real-time object detection and tracking system with an IoT back end. A laptop camera feeds a YOLOv8 detector, a tracker gives each object a persistent ID, and the results are sent over MQTT to a simulated ESP32 that reacts with an LED, a buzzer, an OLED display, and a servo.

VisionTrack AI works as a small **smart occupancy and intrusion monitor**: it counts people entering and leaving, and raises a physical alarm when someone lingers in a restricted zone.

## Features

- **Real-time detection** of persons, cell phones, laptops, and cups (COCO classes) using YOLOv8
- **Multi-object tracking** with persistent IDs (ByteTrack)
- **IN / OUT counting** with a virtual line across the frame
- **Restricted zone alarm**: triggers when a person stays inside a defined area for 3 seconds
- **Flicker smoothing**: majority vote over recent frames and averaged position, so the hardware does not twitch
- **IoT output** over MQTT to an ESP32 (simulated in Wokwi):
  - LED: on when a person is in view, blinking during an alarm
  - Buzzer: beeps during an alarm
  - OLED: live person count, IN/OUT totals, and a "ZONE ALERT" warning
  - Servo: turns toward the horizontal position of the detected person
- **CSV logging** of detections (`detections.csv`) and alarm events (`alarms.csv`)

## Architecture

```
Webcam
  |
  v
Python (OpenCV + YOLOv8 + ByteTrack)     <- runs on the laptop
  |   counting line, zone logic, smoothing, CSV logs
  |
  |  MQTT (JSON)  ->  public broker (HiveMQ)
  v
ESP32 (simulated in Wokwi, built with PlatformIO)
  |-- LED
  |-- Buzzer
  |-- SSD1306 OLED
  '-- Servo
```

The laptop plays the role of an edge device such as a Raspberry Pi. The ESP32 is simulated in Wokwi, because Wokwi cannot run a Linux Raspberry Pi or a camera pipeline.

## Tech stack

| Part       | Tools                                                                            |
| ---------- | -------------------------------------------------------------------------------- |
| Detection  | Python, OpenCV, Ultralytics YOLOv8 (PyTorch), COCO-pretrained weights            |
| Tracking   | ByteTrack (via Ultralytics)                                                      |
| Messaging  | MQTT (paho-mqtt, PubSubClient), HiveMQ public broker                             |
| Firmware   | ESP32 (Arduino framework), PlatformIO, ArduinoJson, Adafruit SSD1306, ESP32Servo |
| Simulation | Wokwi for VS Code                                                                |

## Project structure

```
visiontrack-ai/
├── detector/
│   ├── detect.py          # detection, tracking, counting, zone alarm, MQTT publishing
│   ├── detections.csv     # created at runtime
│   └── alarms.csv         # created at runtime
└── esp32/
    ├── platformio.ini
    ├── wokwi.toml
    ├── diagram.json       # Wokwi circuit
    └── src/main.cpp       # firmware
```

## Setup

### 1. Detector (Python)

```bash
cd detector
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

python -m pip install ultralytics opencv-python paho-mqtt
python detect.py
```

Press `q` in the camera window to quit. The YOLO weights download automatically on the first run.

### 2. ESP32 (PlatformIO + Wokwi)

1. Open the `esp32` folder in VS Code with the PlatformIO and Wokwi extensions installed.
2. Build the firmware (PlatformIO: Build, the checkmark in the bottom bar).
3. Run **Wokwi: Start Simulator** (a free license is requested on first use).
4. The serial monitor should show `WiFi connected` and `MQTT connected`.

The MQTT topic must match in both files:

- `TOPIC` in `detector/detect.py`
- `TOPIC` in `esp32/src/main.cpp`

The default is `visiontrack/appollo/events`. Because the broker is public, change `appollo` to something unique to you.

## MQTT message format

Published by the detector a few times per second (only on change, plus a 2-second heartbeat):

```json
{
  "persons": 1,
  "total": 2,
  "x": 0.63,
  "in_count": 4,
  "out_count": 3,
  "alarm": false
}
```

| Field                    | Meaning                                                           |
| ------------------------ | ----------------------------------------------------------------- |
| `persons`                | Stable person count (majority over recent frames)                 |
| `total`                  | All tracked objects in view                                       |
| `x`                      | Horizontal position of the first person, 0 (left) to 1 (right)    |
| `in_count` / `out_count` | People who crossed the line left-to-right / right-to-left         |
| `alarm`                  | True when someone has stayed in the restricted zone for 3 seconds |

## Configuration

In `detector/detect.py`:

| Setting                   | Purpose                                              |
| ------------------------- | ---------------------------------------------------- |
| `YOLO("yolov8s.pt")`      | Model size: `n` is fastest, `s` or `m` more accurate |
| `conf=0.5`                | Minimum detection confidence                         |
| `classes=[0, 67, 63, 41]` | Detected classes: person, cell phone, laptop, cup    |
| `LINE_X_RATIO`            | Position of the counting line (0 to 1)               |
| `ZONE`                    | Restricted zone rectangle as fractions of the frame  |
| `ZONE_SECONDS`            | Time inside the zone before the alarm triggers       |

## Limitations

- Uses a general COCO-pretrained model, so similar objects (phone and laptop at odd angles, for example) can still be confused, and the model has no class for things like fingers
- Tracking IDs can change if a person leaves the frame or is occluded, which can cause a missed crossing
- Performance depends on the laptop CPU, and larger models give lower FPS
- The ESP32 is simulated, and the public MQTT broker can occasionally drop connections (the firmware reconnects automatically)
- The counting line is vertical, and the zone is a fixed rectangle

## Future work

- Deploy on a real Raspberry Pi with a camera and a real ESP32
- Fine-tune the model on a custom dataset for specific objects
- Live dashboard (Streamlit) built from the CSV logs
- Telegram alerts with a snapshot when the zone alarm triggers
- Authenticated, private MQTT broker

## Author

Damiiner ([github.com/Damiiner](https://github.com/Damiiner))
