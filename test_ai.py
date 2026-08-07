import os
from dotenv import load_dotenv
from groq import Groq

# Load .env file
load_dotenv()

# Initialize Groq Client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

print("Testing AI Connection...")

# Send a prompt to Groq (Llama 3)
chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Hello! Reply in 1 short sentence confirming you are ready to work as an autonomous AI freelancer.",
        }
    ],
    model="llama-3.3-70b-versatile",
)

print("\nAI Response:")
print(chat_completion.choices[0].message.content)