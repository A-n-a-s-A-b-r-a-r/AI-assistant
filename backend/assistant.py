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
    

    
    gpt =  google.LLM(model="gemini-2.0-flash",vertexai=True)
    # gpt = openai.LLM(model="gpt-4o")
    
    # Create the function context with our weather function
    fnc_ctx = WeatherFunctions()
    

    # Since OpenAI does not support streaming TTS, we'll use it with a StreamAdapter
    # to make it compatible with the VoiceAssistant
    openai_tts = tts.StreamAdapter(
        tts=openai.TTS(voice="alloy"),
        sentence_tokenizer=tokenize.basic.SentenceTokenizer(),
    )


    assistant = VoiceAssistant(
        vad=silero.VAD.load(
            activation_threshold=0.65,
            # min_silence_duration=0.4,
            # min_speech_duration=0.2
            ),  # We'll use Silero's Voice Activity Detector (VAD)
        stt=openai.STT(detect_language=True),  # We'll use openAI's Speech To Text (STT)
        llm=gpt,
        tts=openai_tts,  # We'll use OpenAI's Text To Speech (TTS)
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

        user_msg = called_functions[0].call_info.arguments.get("user_msg")
        if user_msg:
            schedule_task(_answer(user_msg))

    assistant.start(ctx.room)

    await asyncio.sleep(1)
    await assistant.say("Hi there! How can I help?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    
    
