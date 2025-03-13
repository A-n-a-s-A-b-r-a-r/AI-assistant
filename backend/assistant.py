import asyncio
from typing import Annotated

from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli, tokenize, tts
from livekit.agents.llm import (
    ChatContext,
    ChatMessage,
)
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import openai, silero
from dotenv import load_dotenv
from livekit.plugins import google
from livekit.agents.llm import FunctionContext
import aiohttp
import json
from livekit.plugins import azure



load_dotenv()

def schedule_task(coro):
    loop = asyncio.get_running_loop()
    loop.create_task(coro)
    
class WeatherFunctions(FunctionContext):
    def __init__(self):
        super().__init__()
        
        # Register the weather function using the instance method
        @self.ai_callable(
            name="get_weather",
            description="Get the current weather for a specific location"
        )
        async def get_weather(location: Annotated[str, "The city and state, e.g. San Francisco, CA"]) -> str:
            """
            Get the current weather for a specific location.
            """
            # In a real implementation, you would call a weather API here
            return f"The weather in {location} is sunny with a temperature of 72°F."
        
                # Updated HSN Codes function with API call
        @self.ai_callable(
            name="hsnCodesDetails",
            description="Search for numeric HS codes for items"
        )
        async def hsn_codes_details(search: Annotated[str, "The item to search for HS code"]) -> str:
            """
            Search for HS codes based on item description.
            """
            # Step 1: Convert to JSON format
            payload = json.dumps({"search": search})
            print(f"HSN function called with JSON payload: {payload}")
            
            try:
                # Step 2: Call external API with the JSON payload
                # Replace with your actual API endpoint
                api_url = "https://finance.devapi.zipaworld.com/api/auth/masters/importDuties/manager"
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, data=payload, headers={"Content-Type": "application/json"}) as response:
                        if response.status == 200:
                            # Step 3: Get the API response as JSON
                            api_response = await response.json()
                            print(f"API Response: {json.dumps(api_response, indent=2)}")
                            
                            # Step 4: Return the JSON response as a string
                            # The LLM will process this response to generate the final answer
                            return json.dumps(api_response)
                        else:
                            error_text = await response.text()
                            print(f"API Error ({response.status}): {error_text}")
                            return f"Sorry, I couldn't retrieve the HSN code information. The API returned status code {response.status}."
            
            except Exception as e:
                print(f"Error calling HSN API: {str(e)}")
                # For testing purposes, you can return a mock response:
                mock_response = {
                    "status": "success",
                    "item": search,
                    "hsn_codes": [
                        {"code": "8414.51.10", "description": "Table, floor, wall, window, ceiling or roof fans", "duty_rate": "7.5%"},
                        {"code": "8414.51.90", "description": "Other fans", "duty_rate": "10%"}
                    ],
                    "notes": "These are approximate classifications. Please consult with a customs specialist for official classification."
                }
                return json.dumps(mock_response)
        
        
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"Room name: {ctx.room.name}")
    

    chat_context = ChatContext(
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Your name is Alloy. You are a funny, witty bot. Your interface with users will be voice."
                    "Respond with short and concise answers. Avoid using unpronouncable punctuation or emojis."
                ),
            )
        ]
    )
    

    
    gpt =  google.LLM(model="gemini-1.5-flash",vertexai=True)
    # gpt = openai.LLM(model="gpt-4o")
    
    # Create the function context with our weather function
    fnc_ctx = WeatherFunctions()
    

    # Since OpenAI does not support streaming TTS, we'll use it with a StreamAdapter
    # to make it compatible with the VoiceAssistant
    openai_tts = tts.StreamAdapter(
        tts=openai.TTS(voice="alloy"),
        sentence_tokenizer=tokenize.basic.SentenceTokenizer(),
    )
    
    def viseme_handler(event):
        """Handle viseme events from Azure TTS."""
        print(f"Viseme ID: {event.viseme_id}")
        print(f"Animation: {event.animation}")
        print(f"Audio offset: {event.audio_offset}")
        

    azure_tts = azure.TTS(
        voice="en-US-AriaNeural",  # Optional - choose your preferred voice
        on_viseme_event=viseme_handler,
    )


    assistant = VoiceAssistant(
        vad=silero.VAD.load(
            activation_threshold=0.6,
            # min_speech_duration=0.2
            ),  # We'll use Silero's Voice Activity Detector (VAD)
        stt=openai.STT(detect_language=True),  # We'll use openAI's Speech To Text (STT)
        llm=gpt,
        tts=azure_tts,  # We'll use OpenAI's Text To Speech (TTS)
        fnc_ctx=fnc_ctx,
        chat_ctx=chat_context,
    )

    chat = rtc.ChatManager(ctx.room)

    async def _answer(text: str):
        """
        Answer the user's message with the given text and optionally the latest
        image captured from the video track.
        """
        content: list[str] = [text]

        chat_context.messages.append(ChatMessage(role="user", content=content))

        stream = gpt.chat(chat_ctx=chat_context)
        await assistant.say(stream, allow_interruptions=True)

    @chat.on("message_received")
    def on_message_received(msg: rtc.ChatMessage):
        """This event triggers whenever we get a new message from the user."""

        if msg.message:
            schedule_task(_answer(msg.message))


    @assistant.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list[agents.llm.CalledFunction]):
        """This event triggers when an assistant's function call completes."""

        if len(called_functions) == 0:
            return
        
        function_call = called_functions[0]
        function_name = function_call.call_info.function_info.name
        function_result = function_call.result
        
        async def process_function_result():
            if function_name == "hsnCodesDetails":
                # Parse the JSON response
                try:
                    hsn_data = json.loads(function_result)

                     # Create a new prompt for the LLM to interpret the HSN data
                    interpret_prompt = f"""
                    The user asked about HSN codes for "{hsn_data.get('description', 'an item')}".
                    Here is the relevant HSN code information:
                    {json.dumps(hsn_data, indent=2)}
                    ### Instructions:
                    - Extract only the most relevant details that are useful for the user.
                    - Do **not** include technical jargon, unnecessary metadata, or unrelated details.
                    - Provide a **concise and clear** explanation.
                    - If there are multiple HSN codes, list only the most relevant ones.
                    - Format the response in a **user-friendly** way.

                    Return the response as a short, structured answer.
                    """


                    # Add this as a system message
                    chat_context.messages.append(ChatMessage(role="system", content=interpret_prompt))

                    # Generate a response from the LLM based on the API data
                    stream = gpt.chat(chat_ctx=chat_context)
                    await assistant.say(stream, allow_interruptions=True)

                except json.JSONDecodeError:
                    # If the result isn't valid JSON, just pass it  through
                    await assistant.say(function_result, allow_interruptions=True)
            else:
                # For other function calls, just say the result
                await assistant.say(function_result, allow_interruptions=True)

            user_msg = called_functions[0].call_info.arguments.get("user_msg")
            if user_msg:
                schedule_task(_answer(user_msg))
                
        asyncio.create_task(process_function_result())  


    assistant.start(ctx.room)

    await asyncio.sleep(1)
    await assistant.say("Hi there! How can I help?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    
    
