#!/usr/bin/env python3
import os
import subprocess
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

def kubectl(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return f"Error: {str(e)}"

@app.event("app_mention")
def handle_mention(event, client, logger):
    text = event.get("text", "").lower()
    channel = event.get("channel")
    
    try:
        if "pods" in text:
            client.chat_postMessage(channel=channel, text="🔍 Checking pods...")
            output = kubectl("kubectl get pods -n default -o wide")
            client.chat_postMessage(channel=channel, text=f"```{output}```")
        
        elif "nodes" in text:
            client.chat_postMessage(channel=channel, text="🔍 Checking nodes...")
            output = kubectl("kubectl get nodes -o wide")
            client.chat_postMessage(channel=channel, text=f"```{output}```")
        
        elif "events" in text:
            client.chat_postMessage(channel=channel, text="🔍 Checking events...")
            output = kubectl("kubectl get events -n default --sort-by='.lastTimestamp' | tail -20")
            client.chat_postMessage(channel=channel, text=f"```{output}```")
        
        elif "help" in text:
            client.chat_postMessage(
                channel=channel,
                text="Commands:\n• @bot pods\n• @bot nodes\n• @bot events\n• @bot help"
            )
        
        else:
            client.chat_postMessage(channel=channel, text="Try: pods, nodes, events, or help")
    
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    print("✅ Bot starting...")
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()
