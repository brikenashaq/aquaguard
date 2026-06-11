from flask import Flask, Response, render_template_string, jsonify
from ultralytics import YOLO
from influxdb_client import InfluxDBClient
import subprocess
import cv2
import threading
import time
import numpy as np
from collections import deque
import requests
from groq import Groq
from flask import send_from_directory

app = Flask(__name__)
model = YOLO("best.onnx", task="detect")

# Global variables
current_frame = None
raw_frame = None
lock = threading.Lock()
fish_data = {}
fish_history = deque(maxlen=100)
alert_message = ""
HTML = open("template.html").read()

fish_positions = {}
frame_count = 0

def get_behavior(fish_id, cx, cy, frame_h):
    global fish_positions

    if fish_id not in fish_positions:
        fish_positions[fish_id] = deque(maxlen=20)

    fish_positions[fish_id].append((cx, cy))

    if len(fish_positions[fish_id]) < 5:
        return "Active"

    positions = list(fish_positions[fish_id])
    movements = []
    for i in range(1, len(positions)):
        dx = positions[i][0] - positions[i-1][0]
        dy = positions[i][1] - positions[i-1][1]
        movements.append((dx**2 + dy**2) ** 0.5)

    avg_movement = sum(movements) / len(movements)

    if cy < frame_h * 0.2:
        return "Feeding"
    elif avg_movement < 15:
        return "Idle"
    else:
        return "Active"

def get_sensor_data():
    try:
        client = InfluxDBClient(
            url="https://eu-central-1-1.aws.cloud2.influxdata.com",
            token="",
            org="Aquarium"
        )
        query_api = client.query_api()

        temp_query = '''
        from(bucket: "aquarium")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "temperature")
          |> last()
        '''
        level_query = '''
        from(bucket: "aquarium")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "water_level")
          |> last()
        '''
        feeding_query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "feeding")
          |> last()
        '''

        temp_result = query_api.query(temp_query)
        level_result = query_api.query(level_query)
        feeding_result = query_api.query(feeding_query)

        temperature = "--"
        water_level = "--"
        last_feeding = "--"

        for table in temp_result:
            for record in table.records:
                temperature = f"{record.get_value():.1f}°C"

        for table in level_result:
            for record in table.records:
                water_level = f"{record.get_value():.1f} cm"

        for table in feeding_result:
            for record in table.records:
                from datetime import timedelta
                local_time = record.get_time() + timedelta(hours=2)
                last_feeding = local_time.strftime("%H:%M")

        client.close()
        return {
            "temperature": temperature,
            "water_level": water_level,
            "last_feeding": last_feeding
        }

    except Exception as e:
        print(f"InfluxDB error: {e}")
        return {
            "temperature": "--",
            "water_level": "--",
            "last_feeding": "--"
        }

def save_behavior_to_influx(fish_count, active_count, idle_count, feeding_count):
    try:
        client = InfluxDBClient(
            url="https://eu-central-1-1.aws.cloud2.influxdata.com",
            token="",
            org="Aquarium"
        )
        write_api = client.write_api()
        data = f"fish_behavior fish_count={fish_count},active={active_count},idle={idle_count},feeding={feeding_count}"
        write_api.write(bucket="aquarium", record=data)
        client.close()
    except Exception as e:
        print(f"Behavior InfluxDB error: {e}")

def get_daily_summary():
    try:
        client = InfluxDBClient(
            url="https://eu-central-1-1.aws.cloud2.influxdata.com",
            token="",
            org="Aquarium"
        )
        query_api = client.query_api()

        # Average fish activity today
        activity_query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "fish_behavior")
          |> filter(fn: (r) => r._field == "active")
          |> mean()
        '''

        # Average temperature today
        temp_query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "temperature")
          |> mean()
        '''

        # Feeding count today
        feeding_query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "feeding")
          |> count()
        '''

        # Total fish behavior records
        total_query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "fish_behavior")
          |> filter(fn: (r) => r._field == "fish_count")
          |> count()
        '''

        activity_result = query_api.query(activity_query)
        temp_result = query_api.query(temp_query)
        feeding_result = query_api.query(feeding_query)
        total_result = query_api.query(total_query)

        avg_active = 0
        avg_temp = "--"
        feeding_count = 0
        total_records = 0

        for table in activity_result:
            for record in table.records:
                avg_active = record.get_value() or 0

        for table in temp_result:
            for record in table.records:
                avg_temp = f"{record.get_value():.1f}°C"

        for table in feeding_result:
            for record in table.records:
                feeding_count = int(record.get_value() or 0)

        for table in total_result:
            for record in table.records:
                total_records = int(record.get_value() or 1)

        # Calculate activity percentage
        activity_pct = round((avg_active / 2) * 100) if avg_active else 0
        activity_pct = min(activity_pct, 100)

        # Health score
        if activity_pct >= 60 and avg_temp != "--":
            health = "Good ✅"
            health_color = "#00ff88"
        elif activity_pct >= 30:
            health = "Warning ⚠️"
            health_color = "#ffaa00"
        else:
            health = "Critical 🚨"
            health_color = "#ff3333"

        client.close()

        return {
            "activity_pct": activity_pct,
            "avg_temp": avg_temp,
            "feeding_count": feeding_count,
            "health": health,
            "health_color": health_color
        }

    except Exception as e:
        print(f"Summary error: {e}")
        return {
            "activity_pct": 0,
            "avg_temp": "--",
            "feeding_count": 0,
            "health": "Unknown",
            "health_color": "#888"
        }

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

groq_client = Groq(api_key="")
last_alert_time = 0

def send_telegram(message):
    global last_alert_time
    now = time.time()
    # Only send once every 5 minutes
    if now - last_alert_time < 300:
        return
    last_alert_time = now
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })
        print(f"Telegram alert sent: {message}")
    except Exception as e:
        print(f"Telegram error: {e}")

def ask_gemini(question):
    try:
        with lock:
            data = fish_data.copy() if fish_data else {}

        sensor = get_sensor_data()

        context = f"""You are AquaGuard, an AI assistant for a smart aquarium monitoring system.
You are helpful, friendly and concise. Answer in 2-3 sentences maximum.

Current aquarium data:
Fish detected: {data.get('fish_count', '--')}
Active fish: {data.get('active', '--')}
Idle fish: {data.get('idle', '--')}
Feeding fish: {data.get('feeding', '--')}
Temperature: {sensor.get('temperature', '--')}
Water level: {sensor.get('water_level', '--')}
Last feeding: {sensor.get('last_feeding', '--')}
Current alerts: {data.get('alert', 'None')}

User question: {question}"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": context}
            ]
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"Error: {str(e)}"

def capture_frames():
    global raw_frame

    cmd = [
        "rpicam-vid",
        "--codec", "mjpeg",
        "--width", "1280",
        "--height", "720",
        "--framerate", "10",
        "--timeout", "0",
        "--nopreview",
        "-o", "-"
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    buffer = b""

    while True:
        chunk = process.stdout.read(4096)
        if not chunk:
            break
        buffer += chunk

        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9")

        if start != -1 and end != -1:
            jpg_data = buffer[start:end+2]
            buffer = buffer[end+2:]

            arr = np.frombuffer(jpg_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

            if frame is not None:
                with lock:
                    raw_frame = frame.copy()

def process_frames():
    global current_frame, fish_data, frame_count

    while True:
        with lock:
            if raw_frame is None:
                time.sleep(0.05)
                continue
            frame = raw_frame.copy()

        frame_count += 1
        frame_h, frame_w = frame.shape[:2]

        results = model(frame, conf=0.25, verbose=False, imgsz=640)
        annotated = results[0].plot()

        boxes = results[0].boxes
        fish_count = len(boxes)

        behaviors = []
        active_count = 0
        idle_count = 0
        feeding_count = 0

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            status = get_behavior(i, cx, cy, frame_h)
            behaviors.append({"status": status})

            if status == "Active":
                active_count += 1
            elif status == "Idle":
                idle_count += 1
            elif status == "Feeding":
                feeding_count += 1

            color = (0, 255, 136) if status == "Active" else (0, 170, 255) if status == "Feeding" else (0, 170, 255)
            cv2.putText(annotated, status, (int(x1), int(y1) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        alert = ""

        if idle_count == fish_count and fish_count > 0:
            alert = f"⚠️ All {fish_count} fish are idle — check water conditions!"
            send_telegram(f"⚠️ AquaGuard Alert!\nAll {fish_count} fish are idle.\nCheck water conditions!")
        elif feeding_count > 0:
            alert = f"🍽️ {feeding_count} fish near surface — feeding behavior detected!"

        cv2.putText(annotated, f"Fish: {fish_count}",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                   1, (0, 255, 136), 2)

        fish_history.append({
            "time": time.strftime("%H:%M:%S"),
            "count": fish_count
        })

        save_behavior_to_influx(fish_count, active_count, idle_count, feeding_count)

        with lock:
            current_frame = annotated
            fish_data = {
                "fish_count": fish_count,
                "active": active_count,
                "idle": idle_count,
                "feeding": feeding_count,
                "behaviors": behaviors,
                "alert": alert
            }

def generate_frames():
    while True:
        with lock:
            if current_frame is None:
                time.sleep(0.1)
                continue
            frame = current_frame.copy()

        _, buffer = cv2.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               frame_bytes + b"\r\n")

        time.sleep(0.05)

@app.route("/")
def index():
    with open("landing.html", "r") as f:
        html = f.read()
    return html

@app.route("/video")
def video():
    return Response(generate_frames(),
                   mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/stats")
def stats():
    with lock:
        data = fish_data.copy() if fish_data else {
            "fish_count": 0,
            "active": 0,
            "idle": 0,
            "feeding": 0,
            "behaviors": [],
            "alert": ""
        }
    return jsonify(data)

@app.route("/sensors")
def sensors():
    data = get_sensor_data()
    return jsonify(data)

@app.route("/history/temperature")
def history_temperature():
    try:
        client = InfluxDBClient(
            url="https://eu-central-1-1.aws.cloud2.influxdata.com",
            token="",
            org="Aquarium"
        )
        query_api = client.query_api()
        query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "temperature")
          |> aggregateWindow(every: 10m, fn: mean, createEmpty: false)
        '''
        result = query_api.query(query)
        labels = []
        values = []
        for table in result:
            for record in table.records:
                labels.append(record.get_time().strftime("%H:%M"))
                values.append(round(record.get_value(), 1))
        client.close()
        return jsonify({"labels": labels, "values": values})
    except Exception as e:
        return jsonify({"labels": [], "values": [], "error": str(e)})

@app.route("/history/water_level")
def history_water_level():
    try:
        client = InfluxDBClient(
            url="https://eu-central-1-1.aws.cloud2.influxdata.com",
            token="",
            org="Aquarium"
        )
        query_api = client.query_api()
        query = '''
        from(bucket: "aquarium")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "water_level")
          |> aggregateWindow(every: 10m, fn: mean, createEmpty: false)
        '''
        result = query_api.query(query)
        labels = []
        values = []
        for table in result:
            for record in table.records:
                labels.append(record.get_time().strftime("%H:%M"))
                values.append(round(record.get_value(), 1))
        client.close()
        return jsonify({"labels": labels, "values": values})
    except Exception as e:
        return jsonify({"labels": [], "values": [], "error": str(e)})

@app.route("/history/activity")
def history_activity():
    with lock:
        data = list(fish_history)
    labels = [d["time"] for d in data]
    values = [d["count"] for d in data]
    return jsonify({"labels": labels, "values": values})

@app.route("/test_telegram")
def test_telegram():
    send_telegram("🐟 AquaGuard is working!\nTelegram notifications are active.")
    return jsonify({"status": "sent"})

@app.route("/chat", methods=["POST"])
def chat():
    from flask import request
    question = request.json.get("question", "")
    answer = ask_gemini(question)
    return jsonify({"answer": answer})

@app.route("/summary")
def summary():
    data = get_daily_summary()
    return jsonify(data)

@app.route("/feed", methods=["POST"])
def feed_fish():
    try:
        token = ""
        r = requests.get(f"https://blynk.cloud/external/api/update?token={token}&v0=1")
        if r.status_code == 200:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/raw_video")
def raw_video():
    def generate_raw():
        last_frame_time = 0
        while True:
            now = time.time()
            if now - last_frame_time < 0.05:
                time.sleep(0.01)
                continue
            with lock:
                if raw_frame is None:
                    time.sleep(0.05)
                    continue
                frame = raw_frame.copy()
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            last_frame_time = now
    return Response(generate_raw(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/landing")
def landing():
    with open("landing.html", "r") as f:
        html = f.read()
    return html

@app.route("/dashboard")
def dashboard():
    with open("template.html", "r") as f:
        html = f.read()
    return html

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

if __name__ == "__main__":
    t1 = threading.Thread(target=capture_frames, daemon=True)
    t2 = threading.Thread(target=process_frames, daemon=True)
    t1.start()
    t2.start()
    print("Starting AquaGuard...")
    print("Open http://brikena-pi.local:5000 on your laptop!")
    app.run(host="0.0.0.0", port=5000, debug=False)
