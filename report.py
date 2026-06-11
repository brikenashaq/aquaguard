import schedule
import time
import yagmail
import requests
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient

INFLUX_URL = "https://eu-central-1-1.aws.cloud2.influxdata.com"
INFLUX_TOKEN = "yJZ-GtJCnbRwN_BU6Jn2chTYOh_Z3s05OHg0Cvcgm3aXM5vuKM9OBcMthLWpGsOySmeQ-OCvjt9K2c4LZn-R2w=="
INFLUX_ORG = "Aquarium"
AQUAGUARD_URL = "http://localhost:5000"

# Email settings — change these
EMAIL_SENDER = "your.email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECEIVER = "your.email@gmail.com"

def get_weekly_data():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()

    temp_query = '''
    from(bucket: "aquarium")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "temperature")
      |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
    '''

    feeding_query = '''
    from(bucket: "aquarium")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "feeding")
      |> count()
    '''

    water_query = '''
    from(bucket: "aquarium")
      |> range(start: -7d)
      |> filter(fn: (r) => r._measurement == "water_level")
      |> mean()
    '''

    temp_result = query_api.query(temp_query)
    feeding_result = query_api.query(feeding_query)
    water_result = query_api.query(water_query)

    temperatures = []
    for table in temp_result:
        for record in table.records:
            temperatures.append(round(record.get_value(), 1))

    feeding_count = 0
    for table in feeding_result:
        for record in table.records:
            feeding_count = int(record.get_value() or 0)

    avg_water = 0
    for table in water_result:
        for record in table.records:
            avg_water = round(record.get_value(), 1)

    client.close()

    avg_temp = round(sum(temperatures) / len(temperatures), 1) if temperatures else 0
    min_temp = min(temperatures) if temperatures else 0
    max_temp = max(temperatures) if temperatures else 0

    return {
        "avg_temp": avg_temp,
        "min_temp": min_temp,
        "max_temp": max_temp,
        "feeding_count": feeding_count,
        "avg_water": avg_water,
        "temperatures": temperatures
    }

def get_live_data():
    try:
        stats = requests.get(f"{AQUAGUARD_URL}/stats", timeout=5).json()
        sensors = requests.get(f"{AQUAGUARD_URL}/sensors", timeout=5).json()
        summary = requests.get(f"{AQUAGUARD_URL}/summary", timeout=5).json()
        return stats, sensors, summary
    except:
        return {}, {}, {}

def generate_pdf():
    filename = f"/home/brikena/yolo/AquaGuard_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4,
                           rightMargin=40, leftMargin=40,
                           topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()
    story = []

    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontSize=28,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#00d4aa'),
        alignment=TA_CENTER,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        fontName='Helvetica',
        textColor=colors.HexColor('#94a3b8'),
        alignment=TA_CENTER,
        spaceAfter=20
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#e2e8f0'),
        spaceBefore=16,
        spaceAfter=8
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica',
        textColor=colors.HexColor('#94a3b8'),
        spaceAfter=6
    )

    # Header
    story.append(Paragraph("🐟 AquaGuard", title_style))
    story.append(Paragraph("Smart Aquarium Intelligence — Weekly Report", subtitle_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%A, %B %d, %Y at %H:%M')}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0d1b2e')))
    story.append(Spacer(1, 16))

    # Get data
    weekly = get_weekly_data()
    stats, sensors, summary = get_live_data()

    # Current status
    story.append(Paragraph("Current Status", heading_style))
    current_data = [
        ['Metric', 'Value', 'Status'],
        ['Fish Detected', str(stats.get('fish_count', '--')), 'Live'],
        ['Temperature', sensors.get('temperature', '--'), 'Normal' if weekly['avg_temp'] < 28 else 'Warning'],
        ['Water Level', sensors.get('water_level', '--'), 'Normal'],
        ['Last Feeding', sensors.get('last_feeding', '--'), 'Today'],
        ['Health Score', str(summary.get('health', '--')).replace('✅','').replace('⚠️','').strip(), 'Calculated'],
    ]

    current_table = Table(current_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    current_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d1b2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00d4aa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#070b14')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1e3a5f')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#0d1b2e'), colors.HexColor('#070b14')]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(current_table)
    story.append(Spacer(1, 16))

    # Weekly summary
    story.append(Paragraph("Weekly Summary (Last 7 Days)", heading_style))
    weekly_data = [
        ['Metric', 'Value'],
        ['Average Temperature', f"{weekly['avg_temp']}°C"],
        ['Minimum Temperature', f"{weekly['min_temp']}°C"],
        ['Maximum Temperature', f"{weekly['max_temp']}°C"],
        ['Average Water Level', f"{weekly['avg_water']} cm"],
        ['Total Feedings', str(weekly['feeding_count'])],
        ['Activity Today', f"{summary.get('activity_pct', '--')}%"],
    ]

    weekly_table = Table(weekly_data, colWidths=[3*inch, 3*inch])
    weekly_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d1b2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00d4aa')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#070b14')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1e3a5f')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#0d1b2e'), colors.HexColor('#070b14')]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(weekly_table)
    story.append(Spacer(1, 16))

    # Temperature analysis
    story.append(Paragraph("Temperature Analysis", heading_style))
    if weekly['avg_temp'] > 0:
        if weekly['avg_temp'] < 18:
            temp_status = "WARNING: Average temperature is too cold for goldfish. Recommended range is 18-24°C."
        elif weekly['avg_temp'] > 26:
            temp_status = "WARNING: Average temperature is too warm. Consider improving water circulation."
        else:
            temp_status = "Temperature has been within the safe range for goldfish this week. Good job!"
        story.append(Paragraph(temp_status, normal_style))

    # Footer
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0d1b2e')))
    story.append(Spacer(1, 8))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica',
        textColor=colors.HexColor('#475569'),
        alignment=TA_CENTER
    )
    story.append(Paragraph("AquaGuard — Smart Aquarium Intelligence · South East European University · 2026", footer_style))

    doc.build(story)
    print(f"Report generated: {filename}")
    return filename

def send_report():
    print("Generating weekly report...")
    try:
        filename = generate_pdf()
        yag = yagmail.SMTP(EMAIL_SENDER, EMAIL_PASSWORD)
        yag.send(
            to=EMAIL_RECEIVER,
            subject=f"AquaGuard Weekly Report — {datetime.now().strftime('%B %d, %Y')}",
            contents=f"""
Hello,

Your AquaGuard weekly report is ready!

This report includes:
Current aquarium status
7-day temperature analysis
Feeding history
Water level summary
Health score

AquaGuard — Smart Aquarium Intelligence
            """,
            attachments=filename
        )
        print("Report sent successfully!")
    except Exception as e:
        print(f"Error sending report: {e}")

def test_report():
    print("Generating test report...")
    filename = generate_pdf()
    print(f"Test report saved to: {filename}")
    return filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_report()
    else:
        print("AquaGuard Report Scheduler starting...")
        schedule.every().monday.at("08:00").do(send_report)
        print("Scheduled: Every Monday at 08:00")
        while True:
            schedule.run_pending()
            time.sleep(60)
