import cv2
import numpy as np
import requests
import time
import threading
from datetime import datetime
from collections import deque

CAMERA_INDEX = 0
ESP32_IP = "192.168.1.100"  # Change to the IP printed by ESP32
ESP32_URL = f"http://{ESP32_IP}/status"
SEND_TO_ESP32 = True
SEND_INTERVAL = 1.0

NO_FACE_WARNING_SEC = 5
NO_FACE_ALERT_SEC = 12
MULTI_FACE_ALERT_SEC = 2

WIDTH, HEIGHT = 1360, 820
BG = (18, 22, 30)
PANEL = (29, 35, 46)
EDGE = (53, 62, 76)
WHITE = (240, 244, 250)
MUTED = (145, 157, 174)
GREEN = (75, 215, 145)
AMBER = (20, 190, 255)
RED = (75, 80, 245)
BLUE = (225, 175, 75)
DARK = (12, 15, 21)

STATUS_COLORS = {"SAFE": GREEN, "WARNING": AMBER, "ALERT": RED}
status = "SAFE"
risk_score = 0
face_count = 0
no_face_since = None
multi_face_since = None
paused = False
wifi_enabled = SEND_TO_ESP32
last_send = 0.0
server_state = "NOT CONNECTED"
server_color = MUTED
fps = 0.0
session_start = time.time()
last_frame_time = time.time()
events = deque(maxlen=6)
last_reason = None

cascade_file = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_detector = cv2.CascadeClassifier(cascade_file)
if face_detector.empty():
    raise RuntimeError("OpenCV face detector could not load. Reinstall opencv-python.")


def log_event(message):
    events.appendleft(f"{datetime.now().strftime('%H:%M:%S')}   {message}")


def draw_text(img, value, x, y, color=WHITE, scale=0.5, thickness=1):
    cv2.putText(img, str(value), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thickness, cv2.LINE_AA)


def panel(img, x, y, w, h, fill=PANEL, edge=EDGE):
    cv2.rectangle(img, (x, y), (x + w, y + h), fill, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), edge, 1)


def pill(img, label, x, y, color, width=100):
    cv2.rectangle(img, (x, y), (x + width, y + 27), color, -1)
    draw_text(img, label, x + 9, y + 18, DARK, 0.38, 1)


def detect_faces(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = face_detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(55, 55)
    )

    found = []
    for x, y, w, h in faces:
        # Haar cascade does not provide a calibrated confidence probability.
        # Show a consistent detection indicator instead of a misleading score.
        found.append((int(x), int(y), int(w), int(h), 0.0))
    return found


def annotate_camera(frame, detections):
    output = frame.copy()
    for i, (x, y, w, h, score) in enumerate(detections):
        color = GREEN if len(detections) == 1 else RED
        label = f"FACE {i + 1} | DETECTED"
        cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
        label_y = max(0, y - 29)
        label_w = min(max(165, len(label) * 9), output.shape[1] - x)
        cv2.rectangle(output, (x, label_y), (x + label_w, label_y + 26), color, -1)
        draw_text(output, label, x + 7, label_y + 18, DARK, 0.42, 1)
    return output


def update_status(count, now):
    global status, risk_score, no_face_since, multi_face_since, last_reason

    if count == 0:
        if no_face_since is None:
            no_face_since = now
        multi_face_since = None
        elapsed = now - no_face_since
        if elapsed >= NO_FACE_ALERT_SEC:
            new_status, score, reason = "ALERT", 85, "No face visible"
        elif elapsed >= NO_FACE_WARNING_SEC:
            new_status, score, reason = "WARNING", 40, "No face visible"
        else:
            new_status, score, reason = "SAFE", 10, "Searching for face"
    elif count > 1:
        no_face_since = None
        if multi_face_since is None:
            multi_face_since = now
        if now - multi_face_since >= MULTI_FACE_ALERT_SEC:
            new_status, score, reason = "ALERT", 85, "Multiple faces detected"
        else:
            new_status, score, reason = "WARNING", 45, "Multiple faces detected"
    else:
        no_face_since = None
        multi_face_since = None
        new_status, score, reason = "SAFE", 0, "Single face visible"

    if new_status != status:
        log_event(f"Status: {status} -> {new_status}")
    if reason != last_reason and reason in ("No face visible", "Multiple faces detected"):
        log_event(reason)
    last_reason = reason
    status, risk_score = new_status, score


def send_status(value, score):
    global server_state, server_color
    try:
        response = requests.post(
            ESP32_URL,
            data=f"{value},{score}",
            headers={"Content-Type": "text/plain"},
            timeout=0.7
        )
        if response.status_code == 200:
            server_state, server_color = "CONNECTED", GREEN
        else:
            server_state, server_color = f"HTTP {response.status_code}", AMBER
    except requests.RequestException:
        server_state, server_color = "OFFLINE", RED


def send_async(value, score):
    threading.Thread(target=send_status, args=(value, score), daemon=True).start()


def fit_image(frame, width, height):
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    if frame is None:
        return canvas
    fh, fw = frame.shape[:2]
    scale = min(width / fw, height / fh)
    nw, nh = int(fw * scale), int(fh * scale)
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    x, y = (width - nw) // 2, (height - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


def metric_card(img, x, y, w, h, title, value, note, color):
    panel(img, x, y, w, h)
    draw_text(img, title.upper(), x + 15, y + 25, MUTED, 0.37)
    draw_text(img, value, x + 15, y + 62, color, 0.73, 2)
    draw_text(img, note, x + 15, y + 86, MUTED, 0.35)


def draw_dashboard(frame, detections):
    canvas = np.full((HEIGHT, WIDTH, 3), BG, dtype=np.uint8)
    accent = STATUS_COLORS.get(status, MUTED)

    cv2.rectangle(canvas, (0, 0), (WIDTH, 76), PANEL, -1)
    cv2.rectangle(canvas, (22, 19), (58, 57), BLUE, -1)
    draw_text(canvas, "EM", 28, 43, DARK, 0.48, 2)
    draw_text(canvas, "EXAM SENTINEL", 74, 34, WHITE, 0.72, 2)
    draw_text(canvas, "VISION MONITORING  /  ESP32 ALERT SYSTEM", 75, 56, MUTED, 0.36)
    pill(canvas, "PAUSED" if paused else "LIVE SESSION", 1015, 23,
         AMBER if paused else GREEN, 125)
    draw_text(canvas, datetime.now().strftime("%d %b %Y  %H:%M:%S"),
              1160, 41, WHITE, 0.38)

    panel(canvas, 22, 96, 850, 500)
    draw_text(canvas, "LIVE CAMERA", 42, 126, WHITE, 0.53, 1)
    draw_text(canvas, "Face boxes show a detector-strength score", 42, 148, MUTED, 0.38)
    pill(canvas, "PAUSED" if paused else "CAMERA ACTIVE",
         710, 108, AMBER if paused else GREEN, 135)
    camera_view = fit_image(None if paused else frame, 822, 425)
    canvas[158:583, 36:858] = camera_view

    panel(canvas, 892, 96, 446, 135, edge=accent)
    draw_text(canvas, "SESSION STATUS", 914, 124, MUTED, 0.40)
    draw_text(canvas, status, 914, 166, accent, 0.95, 2)
    draw_text(canvas, "Rule-based risk indicator", 914, 194, MUTED, 0.38)
    cv2.rectangle(canvas, (914, 207), (1314, 215), DARK, -1)
    cv2.rectangle(canvas, (914, 207), (914 + int(400 * risk_score / 100), 215), accent, -1)

    metric_card(canvas, 892, 245, 214, 105, "Risk score", f"{risk_score}%", "Rule-based indicator", accent)
    metric_card(canvas, 1124, 245, 214, 105, "Faces detected", str(face_count), "Current frame", BLUE)
    metric_card(canvas, 892, 364, 214, 105, "Frame rate", f"{fps:.1f} FPS", "Approximate speed", GREEN)
    metric_card(canvas, 1124, 364, 214, 105, "Session time", f"{int(time.time() - session_start)}s", "Since last reset", WHITE)

    panel(canvas, 892, 483, 446, 113)
    draw_text(canvas, "DEVICE CONNECTIVITY", 912, 510, WHITE, 0.46)
    draw_text(canvas, "ESP32 HTTP endpoint", 912, 532, MUTED, 0.37)
    draw_text(canvas, f"{server_state}  |  {ESP32_IP}", 912, 560, server_color, 0.44)
    draw_text(canvas, "Reporting enabled" if wifi_enabled else "Reporting disabled",
              912, 582, GREEN if wifi_enabled else AMBER, 0.38)

    panel(canvas, 22, 614, 850, 174)
    draw_text(canvas, "ACTIVITY LOG", 42, 644, WHITE, 0.49)
    draw_text(canvas, "Recent system events", 42, 663, MUTED, 0.36)
    if events:
        for i, event in enumerate(list(events)[:4]):
            yy = 697 + i * 21
            cv2.circle(canvas, (47, yy - 4), 3, BLUE if i == 0 else MUTED, -1)
            draw_text(canvas, event[:88], 60, yy, WHITE if i == 0 else MUTED, 0.40)
    else:
        draw_text(canvas, "No events recorded.", 42, 706, MUTED, 0.42)

    panel(canvas, 892, 614, 446, 174)
    draw_text(canvas, "QUICK CONTROLS", 912, 644, WHITE, 0.49)
    controls = [("Q / ESC", "Exit"), ("SPACE", "Pause / resume camera"),
                ("W", "Toggle ESP32 reporting"), ("R", "Reset session")]
    for i, (key, description) in enumerate(controls):
        yy = 676 + i * 25
        pill(canvas, key, 912, yy - 17, EDGE, 78)
        draw_text(canvas, description, 1004, yy, WHITE, 0.39)

    draw_text(canvas, "Prototype only. Detector score is not cheating probability.",
              22, 810, MUTED, 0.34)
    return canvas


def main():
    global face_count, paused, wifi_enabled, last_send, fps, last_frame_time
    global session_start, no_face_since, multi_face_since, last_reason

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        raise RuntimeError("Webcam not found. Check camera permissions or set CAMERA_INDEX = 1.")

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    log_event("Monitoring session started")
    latest_frame = None
    detections = []

    try:
        while True:
            now = time.time()
            dt = now - last_frame_time
            if dt > 0:
                current_fps = 1.0 / dt
                fps = current_fps if fps == 0 else 0.85 * fps + 0.15 * current_fps
            last_frame_time = now

            if not paused:
                ok, frame = camera.read()
                if ok:
                    frame = cv2.flip(frame, 1)
                    detections = detect_faces(frame)
                    face_count = len(detections)
                    latest_frame = annotate_camera(frame, detections)
                    update_status(face_count, now)
                else:
                    latest_frame = None
                    detections = []
                    face_count = 0
                    log_event("Camera frame unavailable")

            if wifi_enabled and now - last_send >= SEND_INTERVAL:
                send_async(status, risk_score)
                last_send = now

            cv2.imshow("EXAM SENTINEL | ESP32 MONITOR",
                       draw_dashboard(None if paused else latest_frame, detections))
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), ord("Q"), 27):
                break
            if key == ord(" "):
                paused = not paused
                log_event("Camera paused" if paused else "Camera resumed")
            elif key in (ord("w"), ord("W")):
                wifi_enabled = not wifi_enabled
                log_event("ESP32 reporting enabled" if wifi_enabled else "ESP32 reporting disabled")
            elif key in (ord("r"), ord("R")):
                session_start = time.time()
                no_face_since = None
                multi_face_since = None
                last_reason = None
                log_event("Session reset")

    finally:
        camera.release()
        cv2.destroyAllWindows()
        if wifi_enabled:
            try:
                requests.post(ESP32_URL, data="SAFE,0",
                             headers={"Content-Type": "text/plain"}, timeout=0.5)
            except requests.RequestException:
                pass


if __name__ == "__main__":
    main()
