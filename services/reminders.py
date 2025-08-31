import asyncio
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv
from twilio.rest import Client # Import Twilio

# --- Load Environment Variables ---
load_dotenv()

# Get Email credentials
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL")
CLIENT_EMAIL_APP_PASSWORD = os.getenv("CLIENT_EMAIL_APP_PASSWORD")

# Get Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")


async def send_booking_confirmation(
    recipient_email: str,
    recipient_name: str, # Added for staff notification
    appointment_time: datetime,
    summary: str,
    recipient_phone: str | None = None
) -> str:
    """
    Sends a booking confirmation to the client and an internal notification to the staff/owner.
    """
    appointment_time_str = appointment_time.strftime("%A, %B %d at %I:%M %p")
    
    # --- 1. Send Real Email Confirmation to Client & Staff ---
    email_status = "Email confirmation could not be sent."
    if CLIENT_EMAIL and CLIENT_EMAIL_APP_PASSWORD:
        # --- Client-facing email ---
        client_msg = EmailMessage()
        client_msg['Subject'] = f"Appointment Confirmed: {summary}"
        client_msg['From'] = CLIENT_EMAIL
        client_msg['To'] = recipient_email
        client_msg.set_content(
            f"Hello {recipient_name},\n\nThis is your confirmation for the appointment:\n\n"
            f"  Topic: {summary}\n  When: {appointment_time_str}\n\nWe look forward to speaking with you.\n"
        )
        try:
            context = ssl.create_default_context()
            print(f"📧 Sending confirmation email to {recipient_email}...")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
                smtp.login(CLIENT_EMAIL, CLIENT_EMAIL_APP_PASSWORD)
                
                # Send to client
                smtp.send_message(client_msg)
                print("   - ✅ Client email sent successfully!")
                email_status = "I've sent a confirmation to your email."

                # --- Staff notification email ---
                staff_msg = EmailMessage()
                staff_msg['Subject'] = f"New Booking: {summary} with {recipient_name}"
                staff_msg['From'] = CLIENT_EMAIL
                staff_msg['To'] = CLIENT_EMAIL  # Send to yourself/staff
                staff_msg.set_content(
                    f"A new appointment has been scheduled by the AI agent.\n\n"
                    f"--- Booking Details ---\n"
                    f"Client Name: {recipient_name}\n"
                    f"Client Email: {recipient_email}\n"
                    f"Client Phone: {recipient_phone or 'Not provided'}\n"
                    f"Topic: {summary}\n"
                    f"When: {appointment_time_str}\n"
                )
                
                # Send to staff
                smtp.send_message(staff_msg)
                print(f"   - ✅ Staff notification sent to {CLIENT_EMAIL}!")

        except Exception as e:
            print(f"   - ❌ Failed to send email: {e}")
            email_status = "I tried to send an email, but there was a connection error."
    
    # --- 2. Send Real SMS Confirmation to Client ---
    sms_status = ""
    if recipient_phone and TWILIO_ACCOUNT_SID and TWILIO_PHONE_NUMBER:
        try:
            print(f"📱 Sending SMS from {TWILIO_PHONE_NUMBER} to {recipient_phone}...")
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            message_body = f"Appointment Confirmed: '{summary}' on {appointment_time_str}."
            message = client.messages.create(
                body=message_body,
                from_=TWILIO_PHONE_NUMBER,
                to=recipient_phone
            )
            print(f"   - ✅ SMS sent successfully! SID: {message.sid}")
            sms_status = "I've also sent a confirmation to your phone."
        except Exception as e:
            print(f"   - ❌ Failed to send SMS: {e}")
            sms_status = "I tried to send a text, but the number might be invalid."
            
    return f"Okay, the booking is confirmed. {email_status} {sms_status}".strip()

    # --- 2. Send Real SMS Confirmation ---
    sms_status = ""
    if recipient_phone and TWILIO_ACCOUNT_SID and TWILIO_PHONE_NUMBER:
        try:
            print(f"📱 Sending SMS from {TWILIO_PHONE_NUMBER} to {recipient_phone}...")
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            message_body = f"Appointment Confirmed: '{summary}' on {appointment_time_str}."
            message = client.messages.create(
                body=message_body,
                from_=TWILIO_PHONE_NUMBER,
                to=recipient_phone
            )
            print(f"   - ✅ SMS sent successfully! SID: {message.sid}")
            sms_status = "I've also sent a confirmation to your phone."
        except Exception as e:
            print(f"   - ❌ Failed to send SMS: {e}")
            sms_status = "I tried to send a text, but the number might be invalid."
            
    return f"Okay, the booking is confirmed. {email_status} {sms_status}".strip()


async def schedule_appointment_reminder(
    summary: str,
    recipient_email: str,
    appointment_time: datetime,
    contact_preference: str,
    recipient_phone: str | None = None,
    reminder_lead_time_hours: int = 24
) -> str:
    """
    Sends a real reminder email and/or SMS based on user preference.
    """
    appointment_time_str = appointment_time.strftime("%A, %B %d at %I:%M %p")

    # --- 1. Handle Email Reminder ---
    email_scheduled = False
    if contact_preference.lower() in ['email', 'both'] and CLIENT_EMAIL:
        msg = EmailMessage()
        msg['Subject'] = f"Reminder: Your Appointment for '{summary}' is tomorrow"
        msg['From'] = CLIENT_EMAIL
        msg['To'] = recipient_email
        msg.set_content(
            f"Hello,\n\nThis is a friendly reminder for your appointment:\n\n"
            f"  Topic: {summary}\n  When: {appointment_time_str}\n\nSee you soon!\n"
        )
        try:
            context = ssl.create_default_context()
            print(f"📧 Sending reminder email to {recipient_email}...")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
                smtp.login(CLIENT_EMAIL, CLIENT_EMAIL_APP_PASSWORD)
                smtp.send_message(msg)
            print("   - ✅ Reminder email sent successfully!")
            email_scheduled = True
        except Exception as e:
            print(f"   - ❌ Failed to send reminder email: {e}")

    # --- 2. Handle SMS Reminder ---
    sms_scheduled = False
    if contact_preference.lower() in ['sms', 'both']:
        if recipient_phone and TWILIO_ACCOUNT_SID and TWILIO_PHONE_NUMBER:
            try:
                print(f"📱 Sending SMS reminder from {TWILIO_PHONE_NUMBER} to {recipient_phone}...")
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                message_body = f"Reminder: Your appointment for '{summary}' is tomorrow at {appointment_time.strftime('%I:%M %p')}."
                message = client.messages.create(
                    body=message_body,
                    from_=TWILIO_PHONE_NUMBER,
                    to=recipient_phone
                )
                print(f"   - ✅ SMS reminder sent! SID: {message.sid}")
                sms_scheduled = True
            except Exception as e:
                print(f"   - ❌ Failed to send SMS reminder: {e}")
        else:
            print("   - NOTE: SMS reminder requested but could not be sent (missing config or recipient number).")

    if not email_scheduled and not sms_scheduled:
        return "I couldn't schedule a reminder due to a configuration issue or invalid preference."
    
    return f"Great, I've scheduled a reminder via {contact_preference} for you."


# --- Test Block ---
async def main_test():
    """
    Defines and runs test cases.
    WARNING: This will send REAL communications.
    """
    print("⚙️  Running direct tests for the reminders service...")
    
    # --- Test Data ---
    sample_appointment_time = datetime.now() + timedelta(days=1, hours=3)
    sample_appointment_time = sample_appointment_time.replace(minute=0, second=0, microsecond=0)
    
    # ⚠️ IMPORTANT: Change these to your real, verified test numbers and emails.
    sample_phone = "+18777804236" # Must be a real, Twilio-verified number in E.164 format.
    sample_email = "luizohto2012@gmail.com"
    sample_summary = "Final Project Review"

    print(f"\n--- ⚠️  WARNING: Tests will send a REAL email to {sample_email} and a REAL SMS to {sample_phone} ---")

    # --- Test Case 1: Send a booking confirmation (Email + SMS) ---
    # --- Test Case 1: Send a booking confirmation (Email + SMS) ---
    print("\n--- Testing Booking Confirmation (Email + SMS) ---")
    confirmation_result = await send_booking_confirmation(
        recipient_name="Test User", # Add a name for the test
        recipient_phone=sample_phone,
        recipient_email=sample_email,
        appointment_time=sample_appointment_time,
        summary=sample_summary
    )
    print(f"Agent receives: '{confirmation_result}'")
    
    # --- Test Case 2: Schedule an SMS-only reminder ---
    print("\n--- Testing SMS Reminder ---")
    sms_reminder_result = await schedule_appointment_reminder(
        summary=sample_summary,
        recipient_phone=sample_phone,
        recipient_email=sample_email, # Email is still needed for the function signature
        appointment_time=sample_appointment_time,
        contact_preference='sms'
    )
    print(f"Agent receives: '{sms_reminder_result}'")


if __name__ == "__main__":
    input("Press Enter to run the test and send real communications...")
    asyncio.run(main_test())