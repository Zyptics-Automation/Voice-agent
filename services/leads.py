import os
import asyncio
import gspread
from datetime import datetime

# --- The Core Function ---
async def save_lead_to_sheet(name: str, phone: str, email: str) -> str:
    """
    Connects to Google Sheets and appends a new lead as a row.
    Returns a success or error message string.
    """
    try:
        # Authenticate with Google using the service account file
        # Make sure 'service_account.json' is in your project's root directory
        gc = gspread.service_account(filename="service_account.json")
        
        # Open the spreadsheet by its exact name
        spreadsheet = gc.open("agent")
        
        # Select the first worksheet
        worksheet = spreadsheet.sheet1
        
        # Prepare the data to be added
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = [timestamp, name, phone, email]
        
        # Append the new row to the sheet
        worksheet.append_row(new_row)
        
        print(f"✅ Successfully saved lead for {name} to Google Sheet.")
        return f"Got it, I've saved your details for {name}."
        
    except FileNotFoundError:
        error_msg = "ERROR: 'service_account.json' not found. Please ensure the file is in the correct directory."
        print(error_msg)
        return "I'm sorry, I'm having a technical issue saving your details right now."
    except gspread.exceptions.SpreadsheetNotFound:
        error_msg = "ERROR: Spreadsheet 'agent' not found. Check the sheet name and sharing settings."
        print(error_msg)
        return "I'm sorry, I'm having a technical issue saving your details right now."
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        print(error_msg)
        return "I'm sorry, an unexpected error occurred while saving your details."

# --- Test Block ---
async def main_test():
    """Defines and runs a single test case for saving a lead."""
    print("⚙️  Running a direct test of the save_lead_to_sheet function...")
    
    # Call the function with test data
    result = await save_lead_to_sheet(
        name="Test Lead",
        phone="555-123-4567",
        email="test.lead@email.com"
    )
    
    print("\n--- SCRIPT RESULT ---")
    print(result)
    print("---------------------")

if __name__ == "__main__":
    # This block runs when you execute the script directly
    asyncio.run(main_test())