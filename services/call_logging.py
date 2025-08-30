import asyncio
import gspread
from datetime import datetime
from gspread.exceptions import SpreadsheetNotFound, APIError

async def log_call_to_sheet(
    duration: float, 
    summary: str, 
    action_items: str, 
    transcript: str,
    name: str = "N/A",
    phone: str = "N/A",
    email: str = "N/A"
) -> None:
    """
    Connects to the 'Call Logs' Google Sheet and appends a new row with the call details,
    including the caller's name, phone, and email if provided.
    """
    try:
        gc = gspread.service_account(filename="service_account.json")
        
        # Make sure the sheet name here EXACTLY matches your Google Sheet name (it's case-sensitive)
        spreadsheet = gc.open("Call Logs") 
        
        worksheet = spreadsheet.sheet1
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration_str = f"{duration:.2f}" # Format duration to 2 decimal places
        
        # Add the new contact fields to the row
        new_row = [timestamp, name, phone, email, duration_str, summary, action_items, transcript]
        worksheet.append_row(new_row)
        
        print(f"✅ Successfully logged call to 'Call Logs' sheet.")

    except SpreadsheetNotFound:
        print("❌ ERROR: Could not log call. The 'Call Logs' spreadsheet was not found.")
        print("   Please check that:")
        print("   1. A Google Sheet with the exact name 'Call Logs' exists.")
        print("   2. You have shared that sheet with the service account email.")
    except APIError as e:
        print(f"❌ ERROR: A Google Sheets API error occurred: {e}")
        print("   This often happens if the service account does not have 'Editor' permissions on the sheet.")
    except FileNotFoundError:
        print("❌ ERROR: 'service_account.json' not found. Please ensure the file is in the root directory.")
    except Exception as e:
        print(f"❌ ERROR: An unexpected error occurred. Reason: {e}")

# --- Test Block ---
async def main_test():
    """Defines and runs a single test case for logging a call."""
    print("⚙️  Running a direct test of the log_call_to_sheet function...")
    
    # Create some sample data for the test
    sample_duration = 123.456
    sample_summary = "User called to ask about business hours and a leaky faucet."
    sample_action_items = "- Follow up with John Doe\n- Send quote for faucet repair"
    sample_transcript = ("[User] Hello, what time are you open?\n"
                       "[AI] We are open from 9 AM to 5 PM.\n"
                       "[User] Okay, my sink is also leaking, can you help with that?\n"
                       "[AI] Yes, we can. I can have a plumber call you back...")
    sample_name = "Jane Doe"
    sample_phone = "555-123-4567"
    sample_email = "jane.doe@example.com"


    # Call the function with the test data, including contact info
    await log_call_to_sheet(
        duration=sample_duration,
        summary=sample_summary,
        action_items=sample_action_items,
        transcript=sample_transcript,
        name=sample_name,
        phone=sample_phone,
        email=sample_email
    )

if __name__ == "__main__":
    # This block runs when you execute the script directly
    asyncio.run(main_test())

