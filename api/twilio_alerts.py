# FloodSense Pro — Twilio SMS alerts (drill + live)
import time
from datetime import datetime

import config

# Trial accounts: Twilio prepends ~35 chars + allows only 1 SMS segment.
# Keep body ASCII-only and under ~115 chars so total fits 160 GSM-7 chars.
MAX_SMS_BODY_LEN = 115


def _client():
    from twilio.rest import Client

    return Client(
        config.TWILIO_API_KEY_SID,
        config.TWILIO_API_KEY_SECRET,
        config.TWILIO_ACCOUNT_SID,
    )


def _from_number(client):
    if getattr(config, "TWILIO_FROM_NUMBER", ""):
        return config.TWILIO_FROM_NUMBER.strip()
    nums = client.incoming_phone_numbers.list(limit=1)
    return nums[0].phone_number if nums else None


def _recipients(client):
    raw = getattr(config, "TWILIO_ALERT_TO", "") or ""
    numbers = [n.strip() for n in raw.split(",") if n.strip()]
    if numbers:
        return numbers
    return [x.phone_number for x in client.outgoing_caller_ids.list(limit=10)]


def evac_time_for_risk(risk_label):
    return {
        "EXTREME": "30 min",
        "HIGH": "2 hrs",
        "MEDIUM": "4 hrs",
    }.get((risk_label or "").upper(), "6 hrs")


def build_flood_alert_message(zone_name, risk_label="HIGH", drill=False):
    """
    Short ASCII-only SMS for Twilio trial (error 30044 if too long / unicode).
    """
    evac = evac_time_for_risk(risk_label)
    risk = (risk_label or "HIGH").upper()
    prefix = "DRILL " if drill else ""
    body = (
        f"{prefix}KAVACH: {zone_name} - flood in {evac}. "
        f"GET READY TO EVACUATE. Risk {risk}. Helpline 1070."
    )
    # Strip non-ASCII (em dashes etc. force UCS-2 and shrink segment size)
    body = body.encode("ascii", "ignore").decode("ascii")
    if len(body) > MAX_SMS_BODY_LEN:
        short_zone = zone_name[:20]
        body = (
            f"{prefix}KAVACH: {short_zone} flood {evac}. EVACUATE. "
            f"Risk {risk}. 1070."
        )
        body = body.encode("ascii", "ignore").decode("ascii")[:MAX_SMS_BODY_LEN]
    return body


def _wait_for_delivery(client, sid, timeout_sec=8):
    """Poll until Twilio reports final status (trial sends fail async)."""
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        last = client.messages(sid).fetch()
        if last.status in ("delivered", "sent", "failed", "undelivered"):
            if last.status in ("delivered", "sent"):
                return last
            if last.status in ("failed", "undelivered"):
                return last
        time.sleep(1.5)
    return last


def send_zone_sms(zone_name, risk_label="HIGH", drill=False):
    """Send flood alert SMS for one zone; verify delivery status."""
    try:
        client = _client()
    except ImportError:
        return {"status": "error", "message": "Twilio SDK not installed. Run: pip install twilio"}

    from_num = _from_number(client)
    to_nums = _recipients(client)
    if not from_num:
        return {"status": "error", "message": "No Twilio sender number. Buy a number in Twilio Console."}
    if not to_nums:
        return {
            "status": "error",
            "message": "No recipients. Add TWILIO_ALERT_TO in config.py or verify a phone in Twilio trial.",
        }

    body = build_flood_alert_message(zone_name, risk_label, drill=drill)
    sent = []
    errors = []
    for to in to_nums:
        try:
            msg = client.messages.create(body=body, from_=from_num, to=to)
            final = _wait_for_delivery(client, msg.sid)
            if final and final.status in ("delivered", "sent"):
                sent.append({
                    "zone": zone_name,
                    "to": to,
                    "sid": msg.sid,
                    "status": final.status,
                    "body": body,
                })
            else:
                code = getattr(final, "error_code", None) if final else None
                err_msg = getattr(final, "error_message", None) if final else None
                hint = ""
                if code == 30044:
                    hint = " Message too long for Twilio trial account."
                elif code == 30004:
                    hint = " Blocked by carrier. Verify recipient in Twilio Console."
                errors.append({
                    "zone": zone_name,
                    "to": to,
                    "sid": msg.sid,
                    "status": final.status if final else "unknown",
                    "error_code": code,
                    "error": f"SMS {final.status if final else 'failed'} (code {code}).{hint}",
                })
        except Exception as e:
            errors.append({"zone": zone_name, "to": to, "error": str(e)})

    if sent:
        return {"status": "success", "sent": sent, "errors": errors or None}
    err = errors[0] if errors else {"error": "Send failed"}
    return {
        "status": "error",
        "message": err.get("error", "Send failed"),
        "error_code": err.get("error_code"),
        "errors": errors,
    }


def send_drill_flood_alerts(zones):
    """Send one SMS per triggered zone (drill mode)."""
    all_sent = []
    all_errors = []
    for z in zones:
        name = z.get("zone") or z.get("name") or "Unknown Zone"
        risk = z.get("risk_label") or z.get("risk") or "HIGH"
        result = send_zone_sms(name, risk, drill=True)
        if result.get("status") == "success":
            all_sent.extend(result.get("sent", []))
            if result.get("errors"):
                all_errors.extend(result["errors"])
        else:
            all_errors.append({"zone": name, "error": result.get("message", "failed")})

    if all_sent:
        return {
            "status": "success",
            "sent": all_sent,
            "zones_notified": len(zones),
            "message_count": len(all_sent),
            "errors": all_errors or None,
        }
    return {
        "status": "error",
        "message": all_errors[0]["error"] if all_errors else "No messages sent",
        "errors": all_errors,
    }
