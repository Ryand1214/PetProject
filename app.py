"""Will you go out with me? — Streamlit booking flow.

ask (dodging No) -> date + time -> pick 1 of 4 plans -> confirmation.
When a date is locked in, the app emails the owner via Gmail SMTP with two
attachments: an .ics calendar invite and the QR code PNG.
"""

import calendar
import os
import re
import smtplib
import ssl
import urllib.request
import uuid
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO
from urllib.parse import quote, urlencode

import qrcode
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Will you go out with me?", page_icon="💘", layout="centered")


def secret(key, default=""):
    """Env vars first (Databricks Apps, Docker), then st.secrets (local / Streamlit Cloud)."""
    if os.environ.get(key):
        return os.environ[key]
    try:
        return st.secrets.get(key, default)
    except Exception:  # no secrets file at all
        return default


OWNER = secret("OWNER_NAME", "Ryan")
NOTIFY_TO = secret("NOTIFY_TO", "ryandoswell123@gmail.com")
SENDER = secret("GMAIL_SENDER")
APP_PW = str(secret("GMAIL_APP_PASSWORD")).replace(" ", "")

CAL_ICS_URL = secret("GCAL_ICS_URL")  # Google Calendar "secret address in iCal format"
CAL_TZ = secret("CAL_TZ", "America/New_York")

TIMES = ["12:00 PM", "3:00 PM", "6:00 PM", "7:30 PM", "9:00 PM"]
PLANS = {
    "Dinner date": ("🍝", "A cozy table for two"),
    "Movie night": ("🎬", "Popcorn and a good film"),
    "Coffee & walk": ("☕", "Lattes and a long stroll"),
    "Picnic": ("🧺", "Blanket, snacks, sunshine"),
}
DURATION_H = 2

# ---------- styling ----------
st.markdown(
    """
<style>
.stApp {background: linear-gradient(160deg,#ffe3ec 0%,#fff6f9 60%,#ffeef3 100%);}
h1, h2, h3 {color:#d6336c !important; text-align:center;}
.center {text-align:center;}
.card {background:#fff;border-radius:18px;padding:18px 20px;box-shadow:0 6px 22px rgba(214,51,108,.12);margin-bottom:12px;}
.big {font-size:64px;text-align:center;margin:0;}
div.stButton > button {border-radius:999px;font-weight:600;}
</style>
""",
    unsafe_allow_html=True,
)

ss = st.session_state
ss.setdefault("step", "ask")
ss.setdefault("no_count", 0)
ss.setdefault("sent", None)  # None = not tried, True = sent, str = error


def go(step):
    ss.step = step
    st.rerun()


# ---------- calendar busy times ----------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_calendar(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read()


def busy_slots(day):
    """Return (blocked time labels, error) for `day`, from the owner's Google Calendar."""
    if not CAL_ICS_URL:
        return set(), None
    try:
        tz = ZoneInfo(CAL_TZ)
        cal = icalendar.Calendar.from_ical(fetch_calendar(CAL_ICS_URL))
        events = recurring_ical_events.of(cal).at(day)  # expands repeating events too
    except Exception as e:
        return set(), f"Couldn't read the calendar ({type(e).__name__})."
    blocked = set()
    for ev in events:
        if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT":  # marked "Free"
            continue
        s = ev["DTSTART"].dt
        e = ev["DTEND"].dt if ev.get("DTEND") else None
        if not isinstance(s, datetime):  # all-day event (exam day, trip...) blocks everything
            return set(TIMES), None
        s = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
        e = (e.astimezone(tz) if e.tzinfo else e.replace(tzinfo=tz)) if e else s + timedelta(hours=1)
        for t in TIMES:
            slot_s = datetime.combine(day, datetime.strptime(t, "%I:%M %p").time(), tz)
            if slot_s < e and s < slot_s + timedelta(hours=DURATION_H):
                blocked.add(t)
    return blocked, None


# ---------- helpers ----------
def start_dt():
    t = datetime.strptime(ss.time, "%I:%M %p").time()
    return datetime.combine(ss.date, t)


def gcal_link():
    s = start_dt()
    e = s + timedelta(hours=DURATION_H)
    fmt = "%Y%m%dT%H%M%S"
    params = {
        "action": "TEMPLATE",
        "text": f"{ss.plan} with {OWNER} 💘",
        "dates": f"{s.strftime(fmt)}/{e.strftime(fmt)}",
        "details": f"{PLANS[ss.plan][1]}. It's a date!",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params, quote_via=quote)


def qr_png(data):
    buf = BytesIO()
    qrcode.make(data, box_size=8, border=2).save(buf, format="PNG")
    return buf.getvalue()


def ics_bytes():
    s = start_dt()
    e = s + timedelta(hours=DURATION_H)
    fmt = "%Y%m%dT%H%M%S"  # floating local time: shows at the chosen clock time
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//date-app//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@date-app",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{s.strftime(fmt)}",
        f"DTEND:{e.strftime(fmt)}",
        f"SUMMARY:{ss.plan} with {OWNER}",
        f"DESCRIPTION:{PLANS[ss.plan][1]}. Booked by {ss.get('guest') or 'your date'}.",
        "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY",
        "DESCRIPTION:Date tomorrow!", "END:VALARM",
        "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY",
        "DESCRIPTION:Date in 1 hour!", "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


def summary_text():
    who = ss.get("guest") or "Someone"
    return (
        f"{who} said YES! 💘\n\n"
        f"Date: {ss.date.strftime('%A, %B %d, %Y')}\n"
        f"Time: {ss.time}\n"
        f"Plan: {PLANS[ss.plan][0]} {ss.plan}\n"
        + (f"Their email: {ss.guest_email}\n" if ss.get("guest_email") else "")
        + (f"Their phone: {ss.contact}\n" if ss.get("contact") else "")
        + f"\nAttached: calendar invite (.ics) and QR code.\nGoogle Calendar: {gcal_link()}\n"
    )


def _smtp_send(to, subject, body, attach_qr):
    if not (SENDER and APP_PW):
        return "Auto-notify isn't set up yet (no GMAIL_SENDER / GMAIL_APP_PASSWORD in secrets)."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = to
    msg.set_content(body)
    msg.add_attachment(ics_bytes(), maintype="text", subtype="calendar",
                       filename="date-invite.ics", params={"method": "PUBLISH"})
    if attach_qr:
        msg.add_attachment(qr_png(gcal_link()), maintype="image", subtype="png",
                           filename="date-qr.png")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20) as s:
            s.login(SENDER, APP_PW)
            s.send_message(msg)
        return True
    except Exception as e:  # show the reason, offer retry + manual fallback
        return f"{type(e).__name__}: {e}"


def send_email():
    """Email the owner with the .ics invite and QR code attached."""
    subject = f"It's a date! {ss.plan} on {ss.date.strftime('%b %d')} at {ss.time}"
    return _smtp_send(NOTIFY_TO, subject, summary_text(), attach_qr=True)


def valid_email(addr):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr or ""))


def send_guest_email():
    """Email the guest their own invite (.ics with reminders) if they gave an address."""
    if not valid_email(ss.get("guest_email")):
        return None
    body = (
        f"You're going on a date with {OWNER}! 💘\n\n"
        f"{PLANS[ss.plan][0]} {ss.plan}\n"
        f"{ss.date.strftime('%A, %B %d, %Y')} at {ss.time}\n\n"
        "Open the attached invite to add it to your calendar (reminders included),\n"
        f"or use Google Calendar: {gcal_link()}\n"
    )
    return _smtp_send(ss.guest_email.strip(), f"Your date with {OWNER} 💘", body, attach_qr=False)


# ---------- pages ----------
if ss.step == "ask":
    st.markdown('<p class="big">🥺👉👈</p>', unsafe_allow_html=True)
    st.title("Will you go out with me?")
    pleas = ["", "Are you sure? 🥺", "Really sure??", "Think again 😢", "Pretty please?", "I'll bring snacks 🍫"]
    if ss.no_count:
        st.markdown(f'<p class="center">{pleas[min(ss.no_count, len(pleas) - 1)]}</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Yes 💖", use_container_width=True, type="primary"):
            go("when")
    with c2:
        if st.button("No", key="no_btn", use_container_width=True):
            ss.no_count += 1  # fallback for phones where hover-dodge can't fire
            st.rerun()
    # Make "No" run away from the cursor/finger (Streamlit component iframe is same-origin).
    components.html(
        """
<script>
const doc = window.parent.document;
function arm(){
  const btn = [...doc.querySelectorAll('button')].find(b => b.innerText.trim() === 'No');
  if(!btn){ return setTimeout(arm, 200); }
  if(btn.dataset.armed) return; btn.dataset.armed = 1;
  btn.style.transition = 'transform .15s ease';
  const dodge = e => {
    e.preventDefault();
    const dx = (Math.random()*2-1) * Math.min(260, window.parent.innerWidth/2.5);
    const dy = (Math.random()*2-1) * 160;
    btn.style.transform = `translate(${dx}px, ${dy}px)`;
  };
  btn.addEventListener('mouseenter', dodge);
  btn.addEventListener('touchstart', dodge, {passive:false});
}
arm();
</script>""",
        height=0,
    )

elif ss.step == "when":
    st.title("Yay! 🎉 Pick a day")
    today = date.today()
    ss.date = st.date_input("Date", value=ss.get("date", today + timedelta(days=1)),
                            min_value=today, max_value=today + timedelta(days=180))
    st.markdown(f'<p class="center">{calendar.day_name[ss.date.weekday()]} it is!</p>', unsafe_allow_html=True)
    blocked, cal_err = busy_slots(ss.date)
    if cal_err:
        st.caption(cal_err)
    open_times = [t for t in TIMES if t not in blocked]
    if blocked:
        st.caption("Already busy: " + ", ".join(t for t in TIMES if t in blocked))
    if open_times:
        prev = ss.get("time", "7:30 PM")
        ss.time = st.radio("Time", open_times, horizontal=True,
                           index=open_times.index(prev) if prev in open_times else 0)
    else:
        ss.pop("time", None)
        st.info(f"{OWNER} is busy all day then 😅 Try another date.")
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        go("ask")
    if c2.button("Next →", use_container_width=True, type="primary", disabled=not open_times):
        go("what")

elif ss.step == "what":
    st.title("What should we do?")
    cols = st.columns(2)
    for i, (name, (emoji, blurb)) in enumerate(PLANS.items()):
        with cols[i % 2]:
            picked = ss.get("plan") == name
            st.markdown(
                f'<div class="card" style="border:3px solid {"#d6336c" if picked else "transparent"}">'
                f'<p class="big" style="font-size:44px">{emoji}</p>'
                f'<h3>{name}</h3><p class="center">{blurb}</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Selected ✓" if picked else f"Choose {name}", key=f"p{i}", use_container_width=True):
                ss.plan = name
                st.rerun()
    with st.expander("Who's saying yes? (optional)"):
        ss.guest = st.text_input("Your name", value=ss.get("guest", ""))
        ss.guest_email = st.text_input("Your email (we'll send you the calendar invite)",
                                       value=ss.get("guest_email", ""))
        ss.contact = st.text_input("Phone number (optional)", value=ss.get("contact", ""))
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        go("when")
    if c2.button("Lock it in 🔒", use_container_width=True, type="primary", disabled="plan" not in ss):
        ss.sent = send_email()  # schedule is booked -> email with attachments
        ss.guest_sent = send_guest_email()
        go("done")

elif ss.step == "done":
    st.balloons() if ss.get("_celebrated") is None else None
    ss._celebrated = True
    st.title("It's a date! 💘")
    st.markdown(
        f'<div class="card"><p class="center" style="font-size:18px">'
        f'<b>{PLANS[ss.plan][0]} {ss.plan}</b><br>'
        f'{ss.date.strftime("%A, %B %d, %Y")} at <b>{ss.time}</b></p></div>',
        unsafe_allow_html=True,
    )
    link = gcal_link()
    st.image(qr_png(link), caption="Scan to add it to your calendar", width=240)
    c1, c2 = st.columns(2)
    c1.link_button("Add to Google Calendar", link, use_container_width=True)
    c2.download_button("Download invite (.ics)", ics_bytes(), "date-invite.ics",
                       "text/calendar", use_container_width=True)

    st.caption("Add it to your calendar to get a reminder the day before and 1 hour before.")
    if ss.get("guest_sent") is True:
        st.success(f"Invite sent to {ss.guest_email} 📅")
    elif isinstance(ss.get("guest_sent"), str):
        st.warning("Couldn't email your invite. Use the buttons above instead.")
    if ss.sent is True:
        st.success(f"{OWNER} has been notified automatically 📬")
    else:
        st.warning(f"Auto-notify didn't go through. {ss.sent or ''}")
        if st.button("Retry sending"):
            ss.sent = send_email()
            st.rerun()

    mailto = f"mailto:{NOTIFY_TO}?" + urlencode(
        {"subject": "It's a date!", "body": summary_text()}, quote_via=quote)
    st.link_button(f"Notify {OWNER} manually ✉️", mailto, use_container_width=True)

    if st.button("Start over"):
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()
