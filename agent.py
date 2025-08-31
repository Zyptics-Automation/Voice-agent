import os
import json
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import pytz
import requests

# LiveKit specific imports
from livekit import agents
from livekit.agents import Agent, JobContext, AgentSession, RoomInputOptions, function_tool, RunContext
from livekit.plugins import silero, noise_cancellation, deepgram, google

# Your custom service imports
from knowledge import get_knowledge_base
from services.booking import create_google_calendar_event
from services.leads import save_lead_to_sheet
from services.call_logging import log_call_to_sheet
from services.reminders import send_booking_confirmation, schedule_appointment_reminder

# Load API keys from .env file
load_dotenv(".env")


# --- KNOWLEDGE BASE LOADER ---
def load_full_knowledge() -> str:
    """Loads and formats all knowledge sources into a single string for the system prompt."""
    base_knowledge = get_knowledge_base()
    faq_str = "\n\n--- Frequently Asked Questions ---\n"
    try:
        with open("faqs.json", "r") as f:
            faqs = json.load(f)
            for faq in faqs:
                q = faq.get("question", "").strip()
                a = faq.get("answer", "").strip()
                if q and a:
                    faq_str += f"Q: {q}\nA: {a}\n\n"
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load faqs.json. Error: {e}")
        faq_str = ""
    return base_knowledge + faq_str


# --- THE ZYPTICS AGENT ---
class ZypticsAssistant(Agent):
    def __init__(self) -> None:
        self.current_date = datetime.now().strftime("%A, %B %d, %Y")
        self.collected_info = {}  # Track collected information to prevent repetition
        super().__init__(
            instructions=(
                "You are a friendly and helpful assistant for Zyptics, your name is Rachel. "
                f"For context, today's date is {self.current_date}. Use this to resolve relative dates like 'tomorrow'. "
                "Start the conversation by saying 'Hello! Welcome to Zyptics, I'm Rachel. How can I help you today?' and then wait for the user's response. "

                "## CORE RESPONSIBILITIES "
                "You have three primary goals, in this order of priority: "
                "1. Answer user questions using the knowledge base. "
                "2. Proactively capture lead information (name, number, email) after answering questions about services. "
                "3. Book appointments when a user explicitly asks for one. "
                
                "## LIVE TRANSFER & ESCALATION "
                "If a caller becomes frustrated, repeatedly asks for a person, or states their issue is an emergency, you MUST use the `escalate_to_human` tool immediately. "
                "Recognize phrases like 'I need to speak to a person', 'Can you transfer me to a human?', 'This is an emergency', or 'This is very urgent'. "
                "Do NOT offer to transfer for simple questions that you can answer using the knowledge base. Use this tool as a last resort when you cannot help or the caller is insistent. "
                
                "## AVOID REPETITION "
                "CRITICAL: Never ask the same question twice. Keep track of what information you already have: "
                "- If you already have someone's name, don't ask for it again "
                "- If they already told you what the meeting is about, don't ask again "
                "- If they already gave you their email, don't ask for it again "
                "- Always acknowledge what they've told you: 'Thanks, I have your email as...'"
                
                "NATURAL SPEECH PATTERNS: "
                "Sound like a real person by using natural speech patterns including: "
                "- Filler words: 'uh', 'so', 'well', 'you know', 'like' "
                "- Natural transitions: 'okay so', 'alright', 'let me see', 'hmm' "
                "- Conversational phrases: 'got it', 'sure thing', 'no problem', 'absolutely' "
                "- Use punctuation like commas, em dashes, and ellipses to create natural pauses and rhythm. "
                "- Think out loud: 'let me just...', 'okay I'm checking...', 'right so...' "
                "Don't overuse these - just sprinkle them naturally into your responses. "
                
                "## PROACTIVE LEAD CAPTURE "
                "If a user is NOT explicitly asking to book a meeting but is asking questions about services, pricing, or describing a problem (e.g., 'my sink is leaking'), this is an opportunity to capture a lead. "
                "1. **Identify a Lead Signal:** If a user asks ANY question related to the business's services—including pricing, specific problems, availability, or business hours—consider it a lead signal. "
                "2. **Answer the Question First:** Use the knowledge base to answer their question as best you can. "
                "3. **Make the Offer:** After answering, politely offer to have a human call them back. For example: 'I can have one of our specialists give you a call to discuss that in more detail. Would you like me to take your name and number?' "
                "4. **Save the Lead:** If they say YES, then get their full name, phone number, and email. "
                "5. Once you have their details, use the `save_contact_info` tool to save the lead. "
                
                "MEETING DURATION RULE: "
                "All meetings are exactly 30 minutes long. This is a fixed rule and cannot be changed. Do not ask the user for the duration. When you call finalize_booking, the 'end_time' must be exactly 30 minutes after the 'start_time'."
                
                "TIME AND NUMBER PRONUNCIATION: "
                "When speaking times, use natural spoken formats: "
                "- instead of '14:00', say 'two P.M.' or 'two in the afternoon' "
                "- '10PM' should be 'ten P.M.' or 'ten in the evening' "
                "- '2:30PM' should be 'two thirty P.M.' or 'two thirty in the afternoon' "
                "- '9AM' should be 'nine A.M.' or 'nine in the morning' "
                "For dates, be conversational: 'tomorrow', 'next Tuesday', 'this Friday' "
                
                "You have four tools available: 'save_contact_info' for saving user details, 'check_available_time_slots' for finding meeting times, 'create_calendar_event' for basic booking, and 'finalize_booking' for complete appointment setup with confirmations. "
                
                "INTELLIGENT SCHEDULING BEHAVIOR: "
                "When someone wants to book a meeting, follow this flow WITHOUT repeating questions: "
                "1. Get their name, phone number, and email: 'I'll need your name, mobile number, and email please.' "
                "2. **Ask for Spelling (CRITICAL):** After they provide their name and email, you MUST ask them to spell it out. Keep retrying until they confirm: 'Could you spell out your first name and your full email address for me?' "
                "3. Ask about the topic ONCE: 'What's this meeting about?' "
                "4. Check availability: 'Let me see what we have available...' and use check_available_time_slots "
                "5. Present options conversationally: 'We have Monday at nine A.M., or Tuesday at two P.M. What works better?' "
                "6. Ask for reminder preference ONCE: 'How would you like to be reminded - email, text message, or both?' "
                "7. Confirm before booking: 'Perfect! So that's Tuesday at two P.M. for thirty minutes about the project review. Should I book that?' "
                "8. Use finalize_booking to complete the appointment with confirmations and reminders "
                
                "When gathering information, if something seems incomplete (e.g., a name with one letter, a phone number that's too short), ask for clarification naturally: 'Could you give me your full name?' or 'That phone number seems short - can you repeat it?' "
                "Once you have all details, confirm them out loud before calling any tools: 'Let me confirm - your name is John Doe, phone is 555-1234, and email is john.doe@email.com. Does that sound right?' "
                
                "Handle common scheduling responses: "
                "- 'Tomorrow works' → check tomorrow's availability "
                "- 'Not until next week' → search from next week onwards "
                "- 'Morning is better' → prioritize morning slots "
                "- 'After 3pm' → only show times after 3pm "
                "- 'I'm flexible' → offer 2-3 good options "
                
                "Keep responses conversational and natural, not robotic. If interrupted, acknowledge it naturally: 'Oh sorry, go ahead' or 'Yeah, what were you saying?' "
            )
        )
        
    def _is_within_working_hours(self, timezone: str = "Europe/Dublin") -> bool:
        """
        Checks if the current time is within business hours (9am-6pm).
        """
        try:
            # Define business hours (9 AM to 6 PM / 18:00)
            WORK_START_HOUR = 9
            WORK_END_HOUR = 18

            # Get the current time in the specified timezone
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
            
            # Check if it's a weekday (Monday=0, Sunday=6) and within hours
            is_weekday = 0 <= now.weekday() <= 4  # Monday to Friday
            is_work_hours = WORK_START_HOUR <= now.hour < WORK_END_HOUR
            
            if is_weekday and is_work_hours:
                print("[Debug] Within working hours.")
                return True
            
            print("[Debug] Outside of working hours.")
            return False
        except Exception as e:
            print(f"[Error] Could not determine working hours: {e}")
            return False # Default to false on error

    @function_tool()
    async def escalate_to_human(self, context: RunContext) -> str:
        """
        Use this tool ONLY when a caller is frustrated, insists on speaking with a
        human, or declares their situation is an emergency. This will attempt to
        transfer them to a live team member.
        """
        # Report the escalation status back to our handler
        base_url = os.getenv("BASE_URL", "")
        call_sid = context.room.name # The room name is the Twilio CallSid
        if base_url:
            try:
                requests.post(f"{base_url}/report-status", json={'call_sid': call_sid, 'status': 'escalation_requested'})
            except Exception as e:
                print(f"Could not report status to handler: {e}")

        if self._is_within_working_hours():
            print("Escalation triggered. Ending agent session for live transfer.")
            context.end_report() 
            return "Of course. Please hold for just a moment while I connect you to a member of our team."
        else:
            contact_email = "info@zyptics.com"
            return (f"I understand your urgency, but I'm afraid our team is only available "
                    f"from 9am to 6pm, Monday to Friday. You can reach us by email at {contact_email} "
                    f"and we will get back to you as soon as possible. Is there anything else I can help with for now?")


    @function_tool()
    async def save_contact_info(
        self,
        context: RunContext,
        name: str,
        phone: str,
        email: str
    ) -> str:
        """
        Use this tool to save a potential lead's contact information (name, phone, email). 
        This is used when a caller makes a general inquiry and agrees to have someone call them back.
        """
        # Store the info to prevent asking again
        self.collected_info.update({
            'name': name,
            'phone': phone,
            'email': email
        })
        return await save_lead_to_sheet(name=name, phone=phone, email=email)

    @function_tool()
    async def check_available_time_slots(
        self,
        context: RunContext,
        preferred_date: str = "",
        preferred_time: str = "",
        earliest_acceptable_date: str = ""
    ) -> str:
        """Check available time slots for scheduling meetings, considering client preferences."""
        print(f"[DEBUG] Checking availability - preferred_date: '{preferred_date}', preferred_time: '{preferred_time}', earliest_date: '{earliest_acceptable_date}'")
        
        try:
            from datetime import datetime, timedelta
            import re
            
            # Get current date and time
            now = datetime.now()
            today = now.date()
            
            # Determine search start date
            start_date = now + timedelta(days=1)  # Default to tomorrow
            
            # Parse earliest_acceptable_date
            if earliest_acceptable_date:
                earliest_lower = earliest_acceptable_date.lower().strip()
                print(f"[DEBUG] Parsing earliest date: '{earliest_lower}'")
                
                if "next week" in earliest_lower:
                    days_until_next_monday = (7 - now.weekday()) % 7
                    if days_until_next_monday == 0:  # Today is Monday
                        days_until_next_monday = 7
                    start_date = now + timedelta(days=days_until_next_monday)
                elif "next month" in earliest_lower:
                    start_date = now + timedelta(days=30)
                elif "tomorrow" in earliest_lower:
                    start_date = now + timedelta(days=1)
                elif any(day in earliest_lower for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]):
                    # Handle "next monday", "this tuesday", etc.
                    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    for i, day in enumerate(weekdays):
                        if day in earliest_lower:
                            days_ahead = i - now.weekday()
                            if days_ahead <= 0 or "next" in earliest_lower:  # Target day already happened this week or explicitly next
                                days_ahead += 7
                            start_date = now + timedelta(days=days_ahead)
                            break
            
            # Parse preferred_date if provided
            if preferred_date:
                preferred_lower = preferred_date.lower().strip()
                print(f"[DEBUG] Parsing preferred date: '{preferred_lower}'")
                
                if "tomorrow" in preferred_lower:
                    search_date = now + timedelta(days=1)
                    if search_date >= start_date:
                        start_date = search_date
                elif "today" in preferred_lower:
                    search_date = now
                    if search_date >= start_date:
                        start_date = search_date
            
            print(f"[DEBUG] Start date determined: {start_date}")
            
            # Generate available slots
            available_slots = []
            slot_descriptions = []
            
            # Check next 10 business days from start_date
            current_check = start_date
            days_checked = 0
            
            while len(available_slots) < 6 and days_checked < 14:  # Limit to prevent infinite loops
                if current_check.weekday() < 5:  # Monday to Friday only
                    # Generate morning slots (9 AM - 12 PM)
                    for hour in [9, 10, 11]:
                        slot_time = current_check.replace(hour=hour, minute=0, second=0, microsecond=0)
                        
                        # Apply time preferences
                        include_slot = True
                        if preferred_time:
                            pref_lower = preferred_time.lower().strip()
                            if "afternoon" in pref_lower and hour < 12:
                                include_slot = False
                            elif "morning" in pref_lower and hour >= 12:
                                include_slot = False
                            elif "evening" in pref_lower:  # Handle evening requests
                                include_slot = False
                        
                        if include_slot:
                            iso_time = slot_time.strftime("%Y-%m-%dT%H:%M:%S")
                            available_slots.append(iso_time)
                            
                            # Create natural language description
                            if hour == 9:
                                desc = f"{slot_time.strftime('%A')} at nine A.M."
                            elif hour == 10:
                                desc = f"{slot_time.strftime('%A')} at ten A.M."
                            elif hour == 11:
                                desc = f"{slot_time.strftime('%A')} at eleven A.M."
                            
                            slot_descriptions.append(desc)
                    
                    # Generate afternoon slots (1 PM - 4 PM)
                    for hour in [13, 14, 15, 16]:
                        slot_time = current_check.replace(hour=hour, minute=0, second=0, microsecond=0)
                        
                        # Apply time preferences
                        include_slot = True
                        if preferred_time:
                            pref_lower = preferred_time.lower().strip()
                            if "morning" in pref_lower and hour >= 12:
                                include_slot = False
                            elif "afternoon" in pref_lower and hour < 12:
                                include_slot = False
                        
                        if include_slot:
                            iso_time = slot_time.strftime("%Y-%m-%dT%H:%M:%S")
                            available_slots.append(iso_time)
                            
                            # Create natural language description
                            if hour == 13:
                                desc = f"{slot_time.strftime('%A')} at one P.M."
                            elif hour == 14:
                                desc = f"{slot_time.strftime('%A')} at two P.M."
                            elif hour == 15:
                                desc = f"{slot_time.strftime('%A')} at three P.M."
                            elif hour == 16:
                                desc = f"{slot_time.strftime('%A')} at four P.M."
                            
                            slot_descriptions.append(desc)
                
                current_check += timedelta(days=1)
                days_checked += 1
            
            print(f"[DEBUG] Generated {len(available_slots)} slots")
            
            # Handle special cases
            if preferred_time:
                pref_lower = preferred_time.lower().strip()
                if "10pm" in pref_lower or "10 pm" in pref_lower or "evening" in pref_lower:
                    return "Oh, we're actually closed at ten P.M. Our latest appointments are around four P.M. How about tomorrow at two P.M. instead?"
            
            # Store available slots for later use
            self.collected_info['available_slots'] = available_slots
            self.collected_info['slot_descriptions'] = slot_descriptions
            
            # Return available options with natural variations
            if len(slot_descriptions) >= 3:
                return f"Okay, let me see what we have available... I can offer you {slot_descriptions[0]}, {slot_descriptions[1]}, or {slot_descriptions[2]}. Which of those works best for you?"
            elif len(slot_descriptions) == 2:
                return f"Alright, I have {slot_descriptions[0]} or {slot_descriptions[1]} available. Which would you prefer?"
            elif len(slot_descriptions) == 1:
                return f"I have {slot_descriptions[0]} available. Would that work for you?"
            else:
                return "Hmm, let me check our schedule... How about tomorrow at two P.M.? Would that suit you?"
                
        except Exception as e:
            print(f"[ERROR] Exception in check_available_time_slots: {e}")
            # Fallback response to prevent getting stuck
            return "Let me check our availability... I have tomorrow at two P.M. or Thursday at ten A.M. available. Which works better for you?"
        

    @function_tool()
    async def create_calendar_event(
        self,
        context: RunContext,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = ""
    ) -> str:
        """Use this to book an appointment or schedule a meeting in Google Calendar.
        
        Args:
            summary: The title or summary of the event
            start_time: The start time for the event in ISO 8601 format (e.g., 2025-08-29T14:00:00)
            end_time: The end time for the event in ISO 8601 format (e.g., 2025-08-29T15:00:00)  
            description: A brief description of the event (optional)
        """
        print(f"[Debug] Creating calendar event: Summary='{summary}', Start='{start_time}', End='{end_time}', Description='{description}'")
        
        result = await create_google_calendar_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description
        )
        print(f"[Debug] Calendar event creation result: {result}")
        return result

    @function_tool()
    async def finalize_booking(
        self,
        context: RunContext,
        summary: str,
        start_time: str,
        end_time: str,
        recipient_name: str,
        recipient_phone: str,
        recipient_email: str,
        reminder_preference: str,  # Should be 'email', 'sms', 'both', or 'none'
        description: str = ""
    ) -> str:
        """
        Use this as the final step to book an appointment in Google Calendar, send a confirmation,
        and schedule a reminder based on the user's preference.
        
        Args:
            summary: The title or summary of the event.
            start_time: The start time in ISO 8601 format (e.g., 2025-08-29T14:00:00).
            end_time: The end time in ISO 8601 format (e.g., 2025-08-29T15:00:00).
            recipient_name: The full name of the person attending.
            recipient_phone: The phone number of the person attending.
            recipient_email: The email address of the person attending.
            reminder_preference: How the user wants to be reminded ('email', 'sms', 'both', or 'none').
            description: A brief description of the event (optional).
        """
        print(f"[Debug] Finalizing booking: Summary='{summary}', Start='{start_time}', Preference='{reminder_preference}'")

        # Step 1: Create the calendar event
        event_description = f"{description}\n\nAttendee: {recipient_name}\nPhone: {recipient_phone}\nEmail: {recipient_email}"
        event_result = await create_google_calendar_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=event_description
        )

        # If calendar booking fails, stop here and report the error.
        if "Successfully booked" not in event_result:
            print(f"[Error] Calendar event creation failed: {event_result}")
            return "I'm sorry, I wasn't able to book that appointment. There seems to be a technical issue."

        # Parse the appointment time for confirmations and reminders
        try:
            appointment_time_dt = datetime.fromisoformat(start_time)
        except ValueError:
            print(f"[Error] Could not parse start_time: {start_time}")
            return "The appointment was booked, but I had a slight issue sending the confirmation."

        # Step 2: Send the booking confirmation
        try:
            confirmation_result = await send_booking_confirmation(
                recipient_name=recipient_name, # Pass the name here
                recipient_phone=recipient_phone,
                recipient_email=recipient_email,
                appointment_time=appointment_time_dt,
                summary=summary
            )
            print(f"[Debug] Confirmation result: {confirmation_result}")
        except Exception as e:
            print(f"[Error] Failed to send booking confirmation: {e}")       

        # Step 3: Schedule a reminder if requested
        try:
            if reminder_preference.lower() in ['email', 'sms', 'both']:
                reminder_result = await schedule_appointment_reminder(
                    recipient_phone=recipient_phone,
                    recipient_email=recipient_email,
                    appointment_time=appointment_time_dt,
                    contact_preference=reminder_preference,
                    summary=summary
                )
                print(f"[Debug] Reminder result: {reminder_result}")
                return f"Perfect! I've booked '{summary}' for you and sent a confirmation. I'll also send you a reminder via {reminder_preference} 24 hours beforehand."
            else:
                return f"Perfect! I've booked '{summary}' for you and sent a confirmation."
        except Exception as e:
            print(f"[Error] Failed to schedule reminder: {e}")
            return f"Perfect! I've booked '{summary}' for you and sent a confirmation. There was a small issue with the reminder setup, but the appointment is confirmed."

# --- AGENT ENTRYPOINT ---
async def entrypoint(ctx: JobContext):
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3", 
            language="en-US", 
            punctuate=True, 
            smart_format=True, 
            endpointing_ms=350,  # Reduced for faster interruption detection
            interim_results=True, 
            no_delay=True, 
            filler_words=True
        ),
        llm=google.LLM(
            model="gemini-1.5-flash",
            temperature=0.7,  # Add some variability for more natural responses
        ),
        tts=deepgram.TTS(
            model="aura-asteria-en", 
            encoding="linear16", 
            sample_rate=24000,
        ),
        vad=silero.VAD.load(),
    )
    
    start_time = datetime.now()
    
    try:
        async def start_session():
            await session.start(
                room=ctx.room,
                agent=ZypticsAssistant(),
                room_input_options=RoomInputOptions(
                    noise_cancellation=noise_cancellation.BVC()
                ),
            )

        async def greet_task():
            await asyncio.sleep(1)
            await session.generate_reply(
                instructions=(
                    "Greet the user warmly, introduce yourself as Rachel, and ask how you can help."
                )
            )

        await asyncio.gather(start_session(), greet_task())

    finally:
        # Log the call when it ends
        end_time = datetime.now()
        call_duration = (end_time - start_time).total_seconds()
        
        # Get the conversation transcript
        transcript = "\n".join([f"[{msg.source.kind}] {msg.text}" for msg in session.chat_history.messages])

        if not transcript:
            print("No transcript available to log.")
            return

        print("Call ended. Generating summary and logging...")

        try:
            # Use the LLM to generate a summary and extract action items
            summary_result = await session.llm.chat(
                history=session.chat_history,
                prompt=(
                    "Based on the conversation history, provide a concise, one-sentence summary. "
                    "Then, list any action items for the business owner as a bulleted list (e.g., '- Call back John Doe'). "
                    "If there are no action items, write 'None'. "
                    "Format your response as: \nSummary: [Your one-sentence summary]\nAction Items: [Your bulleted list or None]"
                )
            )

            summary_text = summary_result.choices[0].text
            
            # Parse the summary
            summary = "Summary could not be parsed."
            action_items = "Action items could not be parsed."

            if "Summary:" in summary_text and "Action Items:" in summary_text:
                summary_part = summary_text.split("Summary:")[1]
                action_items = summary_part.split("Action Items:")[1].strip()
                summary = summary_part.split("Action Items:")[0].strip()
            else:
                summary = f"Unformatted summary: {summary_text}"
            
            # Extract contact info from the agent's collected data if available
            agent_instance = session.agent
            name = getattr(agent_instance, 'collected_info', {}).get('name', 'N/A')
            phone = getattr(agent_instance, 'collected_info', {}).get('phone', 'N/A')
            email = getattr(agent_instance, 'collected_info', {}).get('email', 'N/A')
            
            # Call the logging function with contact info
            await log_call_to_sheet(
                duration=call_duration,
                summary=summary,
                action_items=action_items,
                transcript=transcript,
                name=name,
                phone=phone,
                email=email
            )
        except Exception as e:
            print(f"⚠ An error occurred during call summary and logging: {e}")
            # Try to log the raw transcript on error
            await log_call_to_sheet(
                duration=call_duration,
                summary="Error during summary generation.",
                action_items=f"Error: {e}",
                transcript=transcript
            )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))