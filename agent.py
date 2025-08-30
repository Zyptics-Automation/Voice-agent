import os
import json
import asyncio
from dotenv import load_dotenv
from datetime import datetime

# LiveKit specific imports
from livekit import agents
from livekit.agents import Agent, JobContext, AgentSession, RoomInputOptions, function_tool, RunContext
from livekit.plugins import silero, noise_cancellation, deepgram, google

# Your custom service imports
from knowledge import get_knowledge_base
from services.booking import create_google_calendar_event
from services.leads import save_lead_to_sheet  # Import the new lead-saving function
from services.call_logging import log_call_to_sheet

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
        super().__init__(
            instructions=(
                "You are a friendly and helpful assistant for Zyptics, your name is Rachel. "
                f"For context, today's date is {self.current_date}. Use this to resolve relative dates like 'tomorrow'. "
                "Start the conversation by saying 'Hello! Welcome to Zyptics, I'm Rachel. How can I help you today?' and then wait for the user's response. "

                # --- NEW SECTION ADDED HERE ---
                "## CORE RESPONSIBILITIES "
                "You have three primary goals, in this order of priority: "
                "1. Answer user questions using the knowledge base. "
                "2. Proactively capture lead information (name, number, email) after answering questions about services. "
                "3. Book appointments when a user explicitly asks for one. "
                # -----------------------------
                
                "NATURAL SPEECH PATTERNS: "
                "Sound like a real person by using natural speech patterns including: "
                "- Filler words:'uh', 'so', 'well', 'you know', 'like' "
                "- Natural transitions: 'okay so', 'alright', 'let me see', 'hmm' "
                "- Conversational phrases: 'got it', 'sure thing', 'no problem', 'absolutely' "
                "- Use punctuation like commas, em dashes—and ellipses... to create natural pauses and rhythm. "
                "- Think out loud: 'let me just...', 'okay I'm checking...', 'right so...' "
                "Don't overuse these - just sprinkle them naturally into your responses. "
                "NEVER repeat yourself or ask the same question twice in a row. "
                "Insert natural pauses after key phrases, for example: - 'Let me see…' (short pause] - 'Okay, so—' (medium pause) - 'Hmm… well…' (longer pause) Speak slightly slower than normal, like a human thinking aloud."
                "- Use natural pauses. For example: Say: Okay, let's check that…  Wait a short moment.Then continue: I see we have openings on Monday or Tuesday. Which works best?"  
                "If you've already asked something, acknowledge the response and move forward. "

                "## PROACTIVE LEAD CAPTURE "
                "If a user is NOT explicitly asking to book a meeting but is asking questions about services, pricing, or describing a problem (e.g., 'my sink is leaking'), this is an opportunity to capture a lead. "
                "1.  **Identify a Lead Signal:** If a user asks ANY question related to the business's services—including **pricing, specific problems (e.g., 'my sink is leaking'), availability, or business hours**—consider it a lead signal. "
                "2.  **Answer the Question First:** Use the knowledge base to answer their question as best you can. "
                "3.  **Make the Offer:** After answering, politely offer to have a human call them back. For example: 'I can have one of our plumbers give you a call to discuss that in more detail. Would you like me to take your name and number?' "
                "4.  **Save the Lead:** If they say YES, then get their full name, phone number, and email. "
                "5.  Once you have their details, use the `save_contact_info` tool to save the lead. "
    
                
                "MEETING DURATION RULE: "
                "All meetings are exactly 30 minutes long. This is a fixed rule and cannot be changed. Do not ask the user for the duration. When you call create_calendar_event, the 'end_time' must be exactly 30 minutes after the 'start_time'."
                
                "TIME AND NUMBER PRONUNCIATION: "
                "When speaking times, use natural spoken formats: "
                "- instead of '14:00', say 'two P.M.' or 'two in the afternoon' "
                "- '10PM' should be 'ten P.M.' or 'ten in the evening' "
                "- '2:30PM' should be 'two thirty P.M.' or 'two thirty in the afternoon' "
                "- '9AM' should be 'nine A.M.' or 'nine in the morning' "
                "- Avoid saying times as individual letters like 'ten P M' "
                "For dates, be conversational: 'tomorrow', 'next Tuesday', 'this Friday' "
                
                "You have three tools available: 'save_contact_info' for saving user details, 'check_available_time_slots' for finding meeting times, and 'create_calendar_event' for booking meetings. "
                
                "CONVERSATION FLOW MANAGEMENT: "
                "Keep track of what information you already have and don't ask for it again: "
                "- If they said 'project review', don't ask what it's about again "
                "- If they requested a specific time, acknowledge it and either confirm or suggest alternatives "
                "Move the conversation forward efficiently: "
                "1. Get topic → 2. Check availability → 3. Confirm booking "
                
                "INTELLIGENT SCHEDULING BEHAVIOR: "
                "When someone wants to book a meeting, be proactive and helpful: "
                "1. first ask their name, phone number, and email: 'Ok, great, I just need your name, mobile number, and your email please.' "
                "2. **Ask for Spelling (CRITICAL):** After they provide their name and email, you MUST ask them to spell it out, keep retrying until they say 'Yes, that's the correct spelling', then move on, saying: 'Thank you. And just to be certain, could you spell out your first name and your full email address for me?' keep retrying until they confirm the spelling is correct. "
                "3. Ask about the topic: 'And what's this meeting about?' "
                "5. Then check availability: 'Great! Let me see what we have available...' and use check_available_time_slots "
                "6. Present options conversationally: 'We have Monday at nine A.M., or Tuesday at two P.M. What works better?' "
                "7. If they suggest a specific time, check if it's available and respond appropriately "
                "8. Handle business hours naturally: explain if their requested time is outside business hours "
                "9. Always confirm before booking: 'Perfect! So that's Tuesday at two P.M. for twenty minutes about the project review. Should I book that?' "
                
                
                "When gathering information for 'save_contact_info', if you extract something that seems incomplete or incorrect (e.g., a name with one letter, a phone number that's too short, an email without '@'), you must ask for clarification naturally. For example: 'Um, sorry, could you give me your full name?' or 'Hmm, that phone number seems a bit short - can you repeat it?' "
                "Once you are confident you have the correct full name, phone number, and email, you MUST confirm all details out loud with the user before calling the tool. Use natural speech like: 'Okay so let me just confirm - your name is John Doe, phone is 555-1234, and email is john.doe@email.com. Does that all sound right?' "
                
                "When a user wants to book a meeting, follow this natural flow: "
                "- do not ask how long it should be it will always be 30 minutes-"
                "- 'Um, okay so how long do you want the meeting for?' "
                "- 'Ok , great now i just need your name , mobile number and your email please.?' "
                "- 'Alright, and what's this meeting about?' "
                "- 'Let me see what we have available...' (use check_available_time_slots) "
                "- 'We are able to book you in for tomorrow at 2pm if that suits?' "
                "- If they say no: 'No problem, when would work better for you?' "
                "- If they say 'not available till next week': 'Got it, let me check next week...' "
                "- Always confirm before booking: 'Perfect! So that's next Tuesday at 10am for 30 minutes about the project review. Should I go ahead and book that?' "
                
                "Handle common scheduling responses: "
                "- 'Tomorrow works' → check tomorrow's availability "
                "- 'Not until next week' → search from next week onwards "
                "- 'Morning is better' → prioritize morning slots "
                "- 'After 3pm' → only show times after 3pm "
                "- 'I'm flexible' → offer 2-3 good options "
                "Times must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SS) before calling create_calendar_event. "
                
                "Keep responses conversational and natural, not robotic. If interrupted, acknowledge it naturally: 'Oh sorry, go ahead' or 'Yeah, what were you saying?' "
            )
        )

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
        # This tool now simply calls the function from your new leads.py service
            return await save_lead_to_sheet(name=name, phone=phone, email=email)


    @function_tool()
    async def check_available_time_slots(
        self,
        context: RunContext,
        preferred_date: str = "",
        preferred_time: str = "",
        earliest_acceptable_date: str = ""
    ) -> str:
        print(f"[DEBUG] Checking availability - preferred_date: '{preferred_date}', preferred_time: '{preferred_time}', earliest_date: '{earliest_acceptable_date}'")
        
        """Check available time slots for scheduling meetings, considering client preferences.
        
        Args:
            preferred_date: Client's preferred date (e.g., "tomorrow", "next Monday", "2025-08-30")
            preferred_time: Client's preferred time (e.g., "2pm", "morning", "afternoon")  
            earliest_acceptable_date: Earliest date client is available (e.g., "next week", "2025-09-01")
        """
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
                elif "monday" in earliest_lower or "tuesday" in earliest_lower or "wednesday" in earliest_lower or "thursday" in earliest_lower or "friday" in earliest_lower:
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
                # Add more date parsing logic as needed
            
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
            print(f"[DEBUG] First few slots: {available_slots[:3]}")
            
            # Handle special cases
            if preferred_time:
                pref_lower = preferred_time.lower().strip()
                if "10pm" in pref_lower or "10 pm" in pref_lower or "evening" in pref_lower:
                    return "Oh, we're actually closed at ten P.M. Our latest appointments are around four P.M. How about tomorrow at two P.M. instead?"
            
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
        print(f"[Debug]Creating calendar event: Summary='{summary}', Start='{start_time}', End='{end_time}', Description='{description}'")
        
        """Use this to book an appointment or schedule a meeting in Google Calendar.
        
        Args:
            summary: The title or summary of the event
            start_time: The start time for the event in ISO 8601 format (e.g., 2025-08-29T14:00:00)
            end_time: The end time for the event in ISO 8601 format (e.g., 2025-08-29T15:00:00)  
            description: A brief description of the event (optional)
        """
        result = await create_google_calendar_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description
        )
        print(f"[Debug]Calendar event creation result: {result}")
        print
        return result


# --- AGENT ENTRYPOINT ---
async def entrypoint(ctx: JobContext):
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3", 
            language="en-US", 
            punctuate=True, 
            smart_format=True, 
            endpointing_ms=200,  # Reduced for faster interruption detection
            interim_results=True, 
            no_delay=True, 
            filler_words=True
        ),
        llm=google.LLM(
            model="gemini-1.5-flash",
            temperature=0.7,  # Add some variability for more natural responses
            # Uncomment below to enable Google Search for real-time info
            # gemini_tools=[google.types.GoogleSearch()],
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
        # This part that starts the session is now inside the 'try' block
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
                    "Greet the user warmly, introduce yourself rachel, and ask how you can help."
                )
            )

        await asyncio.gather(start_session(), greet_task())

    finally:
        # This 'finally' block will ALWAYS run at the end of the call
        end_time = datetime.now()
        call_duration = (end_time - start_time).total_seconds()
        
        # Get the full conversation transcript from the session history
        transcript = "\n".join([f"[{msg.source.kind}] {msg.text}" for msg in session.chat_history.messages])

        if not transcript:
            print("No transcript available to log.")
            return

        print("Call ended. Generating summary and logging...")

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
        
        # Parse the LLM's response
        summary = summary_text.split("Summary:")[1].split("Action Items:")[0].strip()
        action_items = summary_text.split("Action Items:")[1].strip()

        # Call our new logging function
        await log_call_to_sheet(
            duration=call_duration,
            summary=summary,
            action_items=action_items,
            transcript=transcript
        )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))