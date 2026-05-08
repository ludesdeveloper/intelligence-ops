#!/usr/bin/env python3
import os
import subprocess
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

SYSTEM_PROMPT = """You are a Kubernetes SRE assistant.
Analyze Kubernetes issues and provide solutions.
Be concise and actionable."""

def ask_claude(user_message):
    """Call Claude via CLI with user message"""
    try:
        # Use echo to pipe message to claude
        process = subprocess.Popen(
            ["claude"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}"
        stdout, stderr = process.communicate(input=prompt, timeout=30)
        
        return stdout if stdout else f"Error: {stderr}"
    except Exception as e:
        return f"Error calling Claude: {str(e)}"

@app.event("app_mention")
def handle_message(body, client):
    text = body["event"]["text"]
    channel = body["event"]["channel"]
    ts = body["event"]["ts"]
    
    # Send initial message
    client.chat_postMessage(
        channel=channel,
        text="🤖 Investigating cluster...",
        thread_ts=ts
    )
    
    # Get Claude response
    response = ask_claude(text)
    
    # Send response
    client.chat_postMessage(
        channel=channel,
        text=response[:3500],
        thread_ts=ts
    )

if __name__ == "__main__":
    print("✅ AI Kubernetes Assistant starting...")
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
