# FloodSense Pro — PDF Situation Report Generator

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Color scheme
DARK_BLUE  = colors.HexColor("#1565c0")
LIGHT_BLUE = colors.HexColor("#4fc3f7")
RED        = colors.HexColor("#dc3545")
ORANGE     = colors.HexColor("#fd7e14")
YELLOW     = colors.HexColor("#ffc107")
GREEN      = colors.HexColor("#28a745")
DARK_BG    = colors.HexColor("#0d2137")
WHITE      = colors.white
GRAY       = colors.HexColor("#cccccc")

RISK_COLORS = {
    "LOW":     GREEN,
    "MEDIUM":  YELLOW,
    "HIGH":    ORANGE,
    "EXTREME": RED
}

def create_situation_report(zones_with_risk, allocation=None):
    """
    Generate a professional PDF situation report.
    Returns path to saved PDF file.
    """
    os.makedirs("reports/output", exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path   = f"reports/output/FloodSense_Report_{timestamp}.pdf"
    now_str    = datetime.now().strftime("%d %B %Y, %H:%M hrs")

    doc   = SimpleDocTemplate(pdf_path, pagesize=A4,
                               topMargin=0.5*inch, bottomMargin=0.5*inch,
                               leftMargin=0.6*inch, rightMargin=0.6*inch)
    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle("Title",
        fontSize=22, fontName="Helvetica-Bold",
        textColor=LIGHT_BLUE, alignment=TA_CENTER, spaceAfter=4)

    subtitle_style = ParagraphStyle("Subtitle",
        fontSize=11, fontName="Helvetica",
        textColor=GRAY, alignment=TA_CENTER, spaceAfter=4)

    heading_style = ParagraphStyle("Heading",
        fontSize=13, fontName="Helvetica-Bold",
        textColor=LIGHT_BLUE, spaceBefore=12, spaceAfter=6)

    body_style = ParagraphStyle("Body",
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#333333"), spaceAfter=4)

    # ── Header ──────────────────────────────────────────────
    story.append(Paragraph("🌊 FLOODSENSE PRO", title_style))
    story.append(Paragraph("AI-Driven Flood Risk Prediction & Resource Allocation System", subtitle_style))
    story.append(Paragraph("OFFICIAL SITUATION REPORT", ParagraphStyle("sub2",
        fontSize=10, fontName="Helvetica-Bold",
        textColor=RED, alignment=TA_CENTER, spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=2, color=DARK_BLUE))
    story.append(Spacer(1, 8))

    # Report metadata table
    meta_data = [
        ["Report Generated:", now_str,
         "Classification:", "FOR OFFICIAL USE"],
        ["Coverage Area:",   "Bengaluru Urban District",
         "Data Source:",     "OpenWeatherMap API + XGBoost ML"],
        ["Report Type:",     "Real-Time Risk Assessment",
         "Next Update:",     "30 minutes"],
    ]
    meta_table = Table(meta_data, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.2*inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 8),
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (2,0), (2,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",   (0,0), (0,-1), DARK_BLUE),
        ("TEXTCOLOR",   (2,0), (2,-1), DARK_BLUE),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f0f5fa"), WHITE]),
        ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#dddddd")),
        ("PADDING",     (0,0), (-1,-1), 5),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # ── Risk Summary ────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_BLUE))
    story.append(Paragraph("1. RISK SUMMARY", heading_style))

    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "EXTREME": 0}
    total_pop_at_risk = 0
    for z in zones_with_risk:
        label = z.get("risk_label", "LOW")
        risk_counts[label] = risk_counts.get(label, 0) + 1
        if z.get("risk_class", 0) >= 2:
            total_pop_at_risk += z.get("population", 0)

    summary_data = [
        ["Risk Level", "Zones", "Color Code", "Action Required"],
        ["EXTREME", str(risk_counts["EXTREME"]), "RED",    "Immediate full emergency protocol"],
        ["HIGH",    str(risk_counts["HIGH"]),    "ORANGE", "Begin evacuation of vulnerable areas"],
        ["MEDIUM",  str(risk_counts["MEDIUM"]),  "YELLOW", "Pre-position resources, issue advisory"],
        ["LOW",     str(risk_counts["LOW"]),     "GREEN",  "Monitor conditions, no action needed"],
    ]
    summary_table = Table(summary_data,
                           colWidths=[1.2*inch, 0.8*inch, 1.0*inch, 4.0*inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
        ("BACKGROUND",  (0,1), (-1,1), colors.HexColor("#fde8e8")),
        ("BACKGROUND",  (0,2), (-1,2), colors.HexColor("#fef3e2")),
        ("BACKGROUND",  (0,3), (-1,3), colors.HexColor("#fffde7")),
        ("BACKGROUND",  (0,4), (-1,4), colors.HexColor("#e8f5e9")),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN",       (1,0), (1,-1), "CENTER"),
        ("PADDING",     (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Total population at risk (HIGH + EXTREME zones): "
        f"{total_pop_at_risk:,} people</b>",
        ParagraphStyle("bold_body", fontSize=9, fontName="Helvetica-Bold",
                       textColor=RED, spaceAfter=4)
    ))

    # ── Zone Details ────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_BLUE))
    story.append(Paragraph("2. ZONE-WISE RISK ASSESSMENT", heading_style))

    zone_data = [["Zone", "Risk Level", "Population",
                  "Rainfall", "Temp", "Humidity", "AI Score", "Action"]]

    sorted_zones = sorted(zones_with_risk,
                          key=lambda z: z.get("risk_class", 0),
                          reverse=True)
    for z in sorted_zones:
        rain_1h = z.get("rain_1h", z.get("rainfall_1h", z.get("rainfall", 0)))
        temp_c = z.get("temp", z.get("temperature", 0))
        zone_data.append([
            z.get("name", ""),
            z.get("risk_label", "LOW"),
            f"{z.get('population', 0):,}",
            f"{rain_1h} mm/hr",
            f"{temp_c}°C",
            f"{z.get('humidity', 0)}%",
            f"{z.get('risk_score', 0)}%",
            z.get("action", "")[:40] + "..." if len(z.get("action","")) > 40 else z.get("action","")
        ])

    zone_table = Table(zone_data,
                        colWidths=[0.9*inch, 0.75*inch, 0.75*inch,
                                   0.75*inch, 0.55*inch, 0.65*inch,
                                   0.6*inch, 2.0*inch])
    zone_table_style = [
        ("BACKGROUND",  (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 7.5),
        ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
        ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("ALIGN",       (1,0), (-1,-1), "CENTER"),
        ("ALIGN",       (0,0), (0,-1), "LEFT"),
        ("ALIGN",       (-1,0), (-1,-1), "LEFT"),
        ("PADDING",     (0,0), (-1,-1), 5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1),
         [colors.HexColor("#f9f9f9"), WHITE]),
    ]
    # Color risk level cells
    for i, z in enumerate(sorted_zones, 1):
        label = z.get("risk_label", "LOW")
        bg = {"EXTREME": colors.HexColor("#fde8e8"),
              "HIGH":    colors.HexColor("#fef3e2"),
              "MEDIUM":  colors.HexColor("#fffde7"),
              "LOW":     colors.HexColor("#e8f5e9")}.get(label, WHITE)
        zone_table_style.append(("BACKGROUND", (1,i), (1,i), bg))

    zone_table.setStyle(TableStyle(zone_table_style))
    story.append(zone_table)

    # ── Emergency Contacts ───────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_BLUE))
    story.append(Paragraph("3. EMERGENCY CONTACTS", heading_style))

    contacts_data = [
        ["Agency", "Contact Number", "Role"],
        ["NDRF Helpline",          "011-24363260", "National Disaster Response Force"],
        ["State Disaster Helpline","1070",          "Karnataka SDRF"],
        ["BBMP Control Room",      "080-22221188",  "Bruhat Bengaluru Mahanagara Palike"],
        ["Fire & Emergency",       "101",           "Fire Brigade"],
        ["Ambulance",              "108",           "Medical Emergency"],
        ["Police",                 "100",           "Law & Order"],
    ]
    contacts_table = Table(contacts_data,
                            colWidths=[2.0*inch, 1.5*inch, 3.5*inch])
    contacts_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1),
         [colors.HexColor("#f0f5fa"), WHITE]),
        ("PADDING",     (0,0), (-1,-1), 6),
    ]))
    story.append(contacts_table)

    # ── Footer ───────────────────────────────────────────────
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_BLUE))
    story.append(Paragraph(
        f"Generated by FloodSense Pro | RVCE IDP 2025-26 | "
        f"Theme 11: Disaster & Climate Resilience | Vision 2035 | {now_str}",
        ParagraphStyle("footer", fontSize=7, fontName="Helvetica",
                       textColor=GRAY, alignment=TA_CENTER, spaceBefore=6)
    ))

    doc.build(story)
    print(f"  PDF saved → {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    print("FloodSense Pro — PDF Report Generator Test")
    print("=" * 50)

    # Test with sample data
    from api.weather import get_weather_for_zones
    from ml.predict import predict_all_zones

    zones_weather = get_weather_for_zones(
        config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY
    )
    zones_risk    = predict_all_zones(zones_weather)

    path = create_situation_report(zones_risk)
    print(f"✅ Report generated → {path}")