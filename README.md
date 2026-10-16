# Exam-Monitoring-System-Esp32

A Python + OpenCV desktop prototype that displays a live webcam feed, detects visible faces, shows monitoring status, logs events, and can send status updates to an ESP32 over Wi-Fi.

## Features

- Live webcam preview with face-detection boxes
- SAFE, WARNING, and ALERT status indicators
- Rule-based risk score and face count
- FPS and session timer
- Activity log and keyboard shortcuts
- Optional HTTP status reporting to an ESP32
- OpenCV-only face detection; MediaPipe is not required

## Requirements

- Python 3.9 or newer
- A working webcam
- An ESP32 running the matching HTTP server firmware
- Computer and ESP32 connected to the same reachable Wi-Fi network for device reporting

## Installation

Open PowerShell in the project folder and install dependencies:

```powershell
python -m pip install opencv-python numpy requests
```

## Configuration

Open `exam_sentinel_opencv_fixed.py` and set the ESP32 address to the IP printed in the ESP32 Serial Monitor:

```python
ESP32_IP = "192.168.1.100"
```

Replace the example address with your actual ESP32 IP. If you want to use only the camera and dashboard, set:

```python
SEND_TO_ESP32 = False
```

## Run

```powershell
python exam_sentinel_opencv_fixed.py
```

If the default webcam does not open, try changing `CAMERA_INDEX = 0` to `CAMERA_INDEX = 1`.

## Keyboard controls

| Key | Action |
|---|---|
| `Q` or `Esc` | Close the application |
| `Space` | Pause or resume the camera |
| `W` | Enable or disable ESP32 reporting |
| `R` | Reset the monitoring session timer and timers |

## ESP32 communication

The Python program sends an HTTP `POST` request to:

```text
http://<ESP32_IP>/status
```

The request body is plain text in this format:

```text
SAFE,0
WARNING,40
ALERT,85
```

The ESP32 firmware must expose a `POST /status` route and accept the status and score in the request body. The ESP32 code should map `SAFE` to the green LED, `WARNING` to the yellow LED, and `ALERT` to the red LED and buzzer.

## Status logic

This is a demonstration prototype, not a validated cheating-detection system.

- **SAFE:** one face is visible, or the initial no-face delay has not elapsed.
- **WARNING:** no face is detected for the configured warning period, or multiple faces are detected briefly.
- **ALERT:** no face is detected for the configured alert period, or multiple faces persist beyond the configured delay.

The score is a rule-based indicator. It is not the probability that a student is cheating.

## Limitations

- Haar-cascade face detection may miss faces or produce false detections depending on lighting, camera angle, distance, and occlusion.
- This detector does not provide a calibrated face-confidence probability. The application therefore labels detections rather than presenting an invented confidence percentage.
- A face count or absence of a face cannot establish misconduct.
- This prototype should not be used to make disciplinary decisions without human review and proper validation.
- ESP32 reporting requires the correct IP address, compatible firmware, and network connectivity.

## Troubleshooting

### `ModuleNotFoundError`

Install the dependencies using the same Python executable that runs the script:

```powershell
python -m pip install opencv-python numpy requests
```

### Webcam not found

- Close other applications using the camera.
- Check Windows camera permissions.
- Try `CAMERA_INDEX = 1`.

### ESP32 shows `OFFLINE`

- Confirm the ESP32 is connected to Wi-Fi.
- Copy the current IP address from the ESP32 Serial Monitor.
- Update `ESP32_IP` in the Python file.
- Confirm the PC and ESP32 can communicate over the same network.
- Verify that the ESP32 firmware provides `POST /status`.

## Project files

```text
exam_monitor_esp32/
├── exam_sentinel_opencv_fixed.py
└── README.md
```

## License

Add a license file if you intend to distribute this project publicly.

# Exam-Monitoring-System-Esp32
