---

## 🛠️ Hardware

| Component | Description | Purpose |
|-----------|-------------|---------|
| Raspberry Pi 4 Model B (8GB) | Main compute board | AI inference, web server, camera processing |
| ESP32 DEVKIT V1 | Microcontroller | Sensor reading, servo control |
| HQ Pi Camera + ArduCam 6mm IR lens | Camera module | Live video stream |
| DS18B20 | Waterproof temperature sensor | Water temperature monitoring |
| HC-SR04 | Ultrasonic distance sensor | Water level monitoring |
| SG90 | Micro servo motor | Automatic fish feeding |
| Amazon Echo | Smart speaker | Voice control interface |

---

## 💻 Tech Stack

### Hardware & Embedded
- **Raspberry Pi 4** — Edge AI compute
- **ESP32** — IoT sensor hub
- **Arduino IDE** — ESP32 firmware

### Computer Vision & ML
- **YOLOv8 nano** — Object detection
- **ONNX Runtime** — Optimized inference
- **OpenCV** — Video processing
- **Ultralytics** — Model training

### Backend
- **Python 3.13** — Main language
- **Flask** — Web server
- **Threading** — Concurrent camera and AI processing

### Cloud & IoT
- **InfluxDB Cloud** — Time series database
- **Grafana** — Data visualization
- **Blynk** — Mobile IoT dashboard
- **Telegram Bot API** — Push notifications

### AI & Voice
- **Groq API** (Llama 3) — AI chat assistant
- **Alexa Skills Kit** — Voice control
- **AWS Lambda** — Alexa skill backend

### Infrastructure
- **systemd** — Auto-start services
- **ngrok** — Public URL tunnel
- **PWA** — Mobile app support

---

## 📁 Project Structure
