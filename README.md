# PetProject
What it does: Ask page (the No button runs away) → pick a date and time → choose 1 of 4 plans → confirmation page.

Time slots that clash with your Google Calendar (exams, study, all-day events) are hidden.
When they hit Lock it in, you get an email with the calendar invite (date-invite.ics) and QR code (date-qr.png) attached.
The guest can enter their email to get the invite too. The confirmation page also has Add to Google Calendar, an invite download, and a QR. The invite reminds them 1 day and 1 hour before.
If the email fails, there's a Retry button and a "Notify Ryan manually" button.
Setup walkthrough (about 15 minutes, all free)
Step 1: Make a Gmail App Password (lets the app send email)
Choose the Gmail account the app will send from. Your own account works, or you can make a new one like ryans.dates.bot@gmail.com.
Turn on 2-Step Verification for it: https://myaccount.google.com/signinoptions/twosv
Go to https://myaccount.google.com/apppasswords, type a name like date app, and click Create.
Copy the 16-letter password it shows. You'll only see it once. Spaces don't matter.
Step 2: Get your calendar's secret link (lets the app see when you're busy)
Open https://calendar.google.com on a computer. Click the ⚙️ icon, then Settings.
On the left under Settings for my calendars, click your calendar (usually your name).
Scroll to Integrate calendar and copy the Secret address in iCal format (it ends in basic.ics). Keep it private, because anyone with it can see your events. The app never shows your events to guests. You can skip this step. Without it, every time slot stays open.
Step 3: Put the code on GitHub
Sign in at https://github.com, click + (top right), then New repository.
Name it date-app. Leave it Public: the free Streamlit plan needs that, and no secrets are in the code. Click Create repository.
Click uploading an existing file, drag in app.py, requirements.txt, and README.md, then click Commit changes. Never upload a real secrets.toml. Your passwords go in Streamlit in Step 5.
Step 4: Deploy on Streamlit Community Cloud
Go to https://share.streamlit.io and sign in with GitHub.
Click Create app, then Deploy a public app from GitHub.
Repository: yourname/date-app. Branch: main. Main file path: app.py.
Optional: under App URL, choose a name like ask-ryan. That gives you ask-ryan.streamlit.app.
Click Advanced settings and paste the secrets from Step 5 into the Secrets box. Then click Deploy. The first build takes 1 to 3 minutes.
Step 5: Secrets to paste (fill in your values)
GMAIL_SENDER = "the-sending-account@gmail.com"
GMAIL_APP_PASSWORD = "abcdefghijklmnop"
NOTIFY_TO = "ryandoswell123@gmail.com"
OWNER_NAME = "Ryan"
GCAL_ICS_URL = "https://calendar.google.com/calendar/ical/.../basic.ics"
CAL_TZ = "America/New_York"
To change these later, open the app on share.streamlit.io and go to ⋮ → Settings → Secrets. The app restarts by itself. CAL_TZ examples: America/Chicago, America/Denver, America/Los_Angeles, Europe/London.

Step 6: Test it yourself
Open your .streamlit.app link on your phone and tap Yes.
Pick a day when you have something on your calendar. Those times should be missing.
Choose a plan, open "Who's saying yes?", and enter a second email of yours. Then tap Lock it in.
You should see "Ryan has been notified automatically 📬", and the two emails should arrive with attachments. If you see "Auto-notify didn't go through": BadCredentials means re-check the App Password and the sender address. "not set up yet" means the secrets are missing.
Step 7: Share it
Text or DM the https://….streamlit.app link. It works on any phone or computer with no install. Free apps go to sleep after a few days with no visitors. The first person to open it then waits about 30 seconds while it wakes up.

Run it on your own computer (optional)
pip install -r requirements.txt
mkdir .streamlit && cp secrets.toml.example .streamlit/secrets.toml   # then fill it in
streamlit run app.py
Databricks Apps (alternative)
app.yaml is included. Store the App Password and calendar link as Databricks secrets, add them to the app as resources named gmail-app-password and gcal-ics-url, then deploy. Only people signed in to your Databricks workspace can open it, so use Streamlit Cloud for sharing with friends.
