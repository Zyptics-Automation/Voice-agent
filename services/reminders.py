import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from a .env file at the project root
load_dotenv()

# Get the client's (sender's) contact details from environment variables.
# Provide a default email if it's not set.
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL", "donotreply@yourcompany.com")
CLIENT_PHONE = os.getenv("CLIENT_PHONE") # This will be None if not set in .env


async def send_booking_confirmation(
    recipient_phone: str,
    recipient_email: str,
    appointment_time: datetime,
    summary: str
) -> str:
    """
    Simulates sending an immediate booking confirmation from the CLIENT_EMAIL and CLIENT_PHONE.
    """
    appointment_time_str = appointment_time.strftime("%A, %B %d at %I:%M %p")
    
    confirmation_message = f"Appointment Confirmed: '{summary}' on {appointment_time_str}."
    
    print("✅ SIMULATING SENDING BOOKING CONFIRMATION:")
    print(f"   - Email sent from: {CLIENT_EMAIL}")
    print(f"   - Email sent to:   {recipient_email}")
    
    # Only simulate SMS if a client phone number is configured
    if CLIENT_PHONE:
        print(f"   - SMS sent from:   {CLIENT_PHONE}")
        print(f"   - SMS sent to:     {recipient_phone}")
    else:
        print("   - SMS not sent: CLIENT_PHONE not set in .env file.")
        
    print(f"   - Message: {confirmation_message}")
    
    return "Okay, the booking is confirmed. I've sent a confirmation to your email and phone."


async def schedule_appointment_reminder(
    recipient_phone: str,
    recipient_email: str,
    appointment_time: datetime,
    contact_preference: str, # 'sms', 'email', or 'both'
    reminder_lead_time_hours: int = 2
) -> str:
    """
    Schedules an appointment reminder based on the user's preference.
    """
    
    reminder_time = appointment_time - timedelta(hours=reminder_lead_time_hours)
    appointment_time_str = appointment_time.strftime("%A, %B %d at %I:%M %p")
    reminder_time_str = reminder_time.strftime("%A, %B %d at %I:%M %p")
    
    print(f"✅ SIMULATING SCHEDULING REMINDER for {appointment_time_str}:")

    # Determine where to send the reminder based on preference
    scheduled = False
    if contact_preference.lower() in ['email', 'both']:
        print(f"   - An email reminder will be sent to {recipient_email} at {reminder_time_str}.")
        scheduled = True
        
    if contact_preference.lower() in ['sms', 'both']:
        if CLIENT_PHONE:
            print(f"   - An SMS reminder will be sent to {recipient_phone} at {reminder_time_str}.")
            scheduled = True
        else:
            print("   - NOTE: SMS reminder was requested, but cannot be scheduled because CLIENT_PHONE is not set in your .env file.")

    if not scheduled:
        return "I couldn't schedule a reminder because a valid preference (sms or email) was not provided."
    
    return f"Great, I've scheduled a reminder via {contact_preference} for you."


# --- Test Block ---
async def main_test():
    """Defines and runs test cases for the reminder and confirmation functions."""
    print("⚙️  Running direct tests for the reminders service...")
    
    # --- Test Data ---
    sample_appointment_time = datetime.now() + timedelta(days=2)
    sample_appointment_time = sample_appointment_time.replace(hour=14, minute=30, second=0, microsecond=0)
    sample_phone = "555-987-6543"
    sample_email = "luizohto2012@gmail.com"
    sample_summary = "Dental Check-up"

    # --- Test Case 1: Send a booking confirmation ---
    print("\n--- Testing Booking Confirmation ---")
    confirmation_result = await send_booking_confirmation(
        recipient_phone=sample_phone,
        recipient_email=sample_email,
        appointment_time=sample_appointment_time,
        summary=sample_summary
    )
    print(f"Agent receives: '{confirmation_result}'")


    # --- Test Case 2: Schedule an SMS reminder ---
    print("\n--- Testing SMS Reminder ---")
    sms_reminder_result = await schedule_appointment_reminder(
        recipient_phone=sample_phone,
        recipient_email=sample_email,
        appointment_time=sample_appointment_time,
        contact_preference='sms'
    )
    print(f"Agent receives: '{sms_reminder_result}'")
    
    # --- Test Case 3: Schedule an Email reminder ---
    print("\n--- Testing Email Reminder ---")
    email_reminder_result = await schedule_appointment_reminder(
        recipient_phone=sample_phone,
        recipient_email=sample_email,
        appointment_time=sample_appointment_time,
        contact_preference='email'
    )
    print(f"Agent receives: '{email_reminder_result}'")


if __name__ == "__main__":
    asyncio.run(main_test())

