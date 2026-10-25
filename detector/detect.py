import csv
import json
import os
import time
import cv2
import paho.mqtt.client as mqtt
from collections import Counter, deque
from ultralytics import YOLO

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "visiontrack/appollo/events"  # must match main.cpp

LINE_X_RATIO = 0.5                    # counting line position
ZONE = (0.60, 0.15, 0.98, 0.95)       # restricted zone: x1, y1, x2, y2 as fractions of the frame
ZONE_SECONDS = 3                      # seconds inside the zone before the alarm triggers

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER, PORT, 60)
client.loop_start()

model = YOLO("yolov8s.pt")
cap = cv2.VideoCapture(0)

person_history = deque(maxlen=7)
x_history = deque(maxlen=5)

prev_side = {}
count_in = 0
count_out = 0
zone_since = {}   # track id -> time it entered the zone

last_payload = None
last_sent = 0
last_logged = None
last_alarm = False

log_exists = os.path.exists("detections.csv")
log_file = open("detections.csv", "a", newline="")
log = csv.writer(log_file)
if not log_exists:
    log.writerow(["time", "persons", "in", "out"])

alarm_exists = os.path.exists("alarms.csv")
alarm_file = open("alarms.csv", "a", newline="")
alarm_log = csv.writer(alarm_file)
if not alarm_exists:
    alarm_log.writerow(["time", "event"])

while True:
    ok, frame = cap.read()
    if not ok:
        break

    h, w = frame.shape[:2]
    line_x = int(w * LINE_X_RATIO)
    zx1, zy1, zx2, zy2 = int(w * ZONE[0]), int(h * ZONE[1]), int(w * ZONE[2]), int(h * ZONE[3])
    now = time.time()

    results = model.track(frame, persist=True, tracker="bytetrack.yaml",
                          conf=0.5, imgsz=640, classes=[0, 67, 63, 41], verbose=False)
    r = results[0]
    annotated = r.plot()

    counts = Counter()
    inside_ids = set()
    if r.boxes is not None and len(r.boxes) > 0:
        classes = r.boxes.cls.int().tolist()
        xs_norm = r.boxes.xywhn[:, 0].tolist()
        boxes_px = r.boxes.xywh.tolist()  # [x_center, y_center, w, h] in pixels
        ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(classes)

        first_person_x = None
        for cls, xn, b, tid in zip(classes, xs_norm, boxes_px, ids):
            label = model.names[cls]
            counts[label] += 1
            if label != "person":
                continue
            xp, yp = b[0], b[1]
            if first_person_x is None:
                first_person_x = xn
            if tid is not None:
                # counting line
                side = 1 if xp > line_x else -1
                old = prev_side.get(tid)
                if old is not None and old != side:
                    if side == 1:
                        count_in += 1
                    else:
                        count_out += 1
                prev_side[tid] = side
                # restricted zone
                if zx1 <= xp <= zx2 and zy1 <= yp <= zy2:
                    inside_ids.add(tid)
                    zone_since.setdefault(tid, now)
        if first_person_x is not None:
            x_history.append(first_person_x)

    # forget people who left the zone, then check how long the others stayed
    for tid in list(zone_since):
        if tid not in inside_ids:
            del zone_since[tid]
    alarm = any(now - t >= ZONE_SECONDS for t in zone_since.values())

    person_history.append(counts.get("person", 0))
    stable_persons = Counter(person_history).most_common(1)[0][0]
    x_pos = round(sum(x_history) / len(x_history), 2) if x_history else 0.5

    payload = {
        "persons": stable_persons,
        "total": sum(counts.values()),
        "x": x_pos,
        "in_count": count_in,
        "out_count": count_out,
        "alarm": alarm,
    }

    if (payload != last_payload and now - last_sent > 0.3) or now - last_sent > 2:
        client.publish(TOPIC, json.dumps(payload))
        last_payload = payload
        last_sent = now

    state = (stable_persons, count_in, count_out)
    if state != last_logged:
        log.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), stable_persons, count_in, count_out])
        log_file.flush()
        last_logged = state

    if alarm != last_alarm:
        alarm_log.writerow([time.strftime("%Y-%m-%d %H:%M:%S"),
                            "ZONE ALARM STARTED" if alarm else "ZONE ALARM CLEARED"])
        alarm_file.flush()
        last_alarm = alarm

    # Drawing: counting line, zone, overlay
    cv2.line(annotated, (line_x, 0), (line_x, h), (0, 255, 255), 2)
    zone_color = (0, 0, 255) if alarm else (0, 165, 255)
    cv2.rectangle(annotated, (zx1, zy1), (zx2, zy2), zone_color, 2)
    cv2.putText(annotated, "RESTRICTED ZONE", (zx1 + 5, zy1 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, zone_color, 2)
    cv2.putText(annotated, "VisionTrack AI", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(annotated, f"IN: {count_in}   OUT: {count_out}", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(annotated, f"Persons (stable): {stable_persons}", (10, 85),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    if alarm:
        cv2.putText(annotated, "ZONE ALERT!", (10, 125),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

    cv2.imshow("VisionTrack AI", annotated)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
log_file.close()
alarm_file.close()
client.loop_stop()
client.disconnect()