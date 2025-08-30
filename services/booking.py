import os
import asyncio
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta

# The scope for the Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def _get_calendar_service():
    """Handles Google authentication and returns a Calendar service object."""
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

async def create_google_calendar_event(summary: str, start_time: str, end_time: str, description: str | None = None) -> str:
    """
    Creates an event on the user's primary Google Calendar.
    The Google API client is synchronous, so we run it in an executor to avoid
    blocking the main async event loop.
    """
    try:
        loop = asyncio.get_running_loop()

        def _create_event_sync():
            service = _get_calendar_service()
            event_body = {
                'summary': summary,
                'description': description or '',
                'start': {'dateTime': start_time, 'timeZone': 'UTC'},
                'end': {'dateTime': end_time, 'timeZone': 'UTC'},
            }
            event = service.events().insert(calendarId='primary', body=event_body).execute()
            return f"Successfully booked the meeting titled '{event.get('summary')}'."

        # Run the synchronous Google API call in a separate thread
        result = await loop.run_in_executor(None, _create_event_sync)
        return result
    except HttpError as error:
        return f"An error occurred while creating the calendar event: {error}"
    except Exception as e:
        # This will catch errors like a missing credentials.json file
        return f"An unexpected error occurred: {e}"
    
async def main_test():
    "for testing purposes only"
    now = datetime.utcnow()
    start_time_obj = now + timedelta(days=1)
    end_time_obj = start_time_obj + timedelta(minutes=30)
    
    start_iso = start_time_obj.isoformat() + 'Z'  # 'Z' indicates UTC time
    end_iso = end_time_obj.isoformat() + 'Z'
    
    result = await create_google_calendar_event(
        summary = "test meeting",
        start_time=start_iso,
        end_time=end_iso,
        description="This is a test meeting created via the Google Calendar API."
    )
    print("\n--- SCRIPT RESULT ---")
    print(result)
    print("---------------------")
    if "Successfully booked" in result:
        print("\n✅ Test Passed! Check your Google Calendar to confirm the event was created.")
    else:
        print("\n❌ Test Failed. Review the error message above.")

if __name__ == "__main__":
    # This block only runs when you execute the script directly (e.g., python services/booking.py)
    # It sets up and runs our async main_test function.
    try:
        asyncio.run(main_test())
    except Exception as e:
        print(f"An error occurred while running the test: {e}")