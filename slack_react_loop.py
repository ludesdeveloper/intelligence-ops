#!/usr/bin/env python3
import os
import json
import subprocess
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

def kubectl(cmd):
    """Python executes kubectl - always works"""
    log.info(f"kubectl: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    output = result.stdout if result.returncode == 0 else result.stderr
    log.info(f"output: {output[:100]}")
    return output

def ask_claude(messages):
    """Call Claude with conversation history"""
    try:
        prompt = json.dumps(messages)
        process = subprocess.Popen(
            ["claude", "--print", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=60)
        return stdout.strip() if stdout else f"Error: {stderr}"
    except Exception as e:
        return f"Error: {str(e)}"

def react_loop(user_question):
    """
    ReAct Loop:
    Claude decides what kubectl command to run
    Python executes it
    Loop until Claude has enough info to answer
    """

    SYSTEM = """You are a Kubernetes SRE assistant.
You CANNOT run commands yourself.
Instead respond with JSON to tell what kubectl command to run next.

To run a command respond with ONLY:
{"action": "kubectl", "cmd": "get pods -A"}

When you have enough info to answer respond with ONLY:
{"action": "answer", "text": "your full diagnosis here"}

No markdown. No explanation. Just JSON.
Start investigating based on the user question."""

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_question}
    ]

    log.info(f"Starting ReAct loop for: {user_question}")

    for i in range(5):  # Max 5 iterations
        log.info(f"Iteration {i+1}")

        response = ask_claude(messages)
        log.info(f"Claude said: {response[:200]}")

        # Try to parse JSON
        try:
            # Clean response - sometimes Claude adds extra text
            clean = response.strip()
            if "```" in clean:
                clean = clean.split("```")[1].replace("json", "").strip()

            decision = json.loads(clean)

            if decision["action"] == "kubectl":
                cmd = f"kubectl {decision['cmd']}"
                log.info(f"Executing: {cmd}")

                output = kubectl(cmd)

                # Add to conversation
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": f"Command output:\n{output}\n\nWhat next? Continue investigating or give final answer."
                })

            elif decision["action"] == "answer":
                log.info("Claude has final answer")
                return decision["text"]

        except json.JSONDecodeError:
            # Claude gave plain text = treat as final answer
            log.info("Claude gave plain text response")
            return response

    return "Investigation complete after 5 steps."

@app.event("app_mention")
def handle_mention(body, client):
    text = body["event"]["text"]
    channel = body["event"]["channel"]
    ts = body["event"]["ts"]

    log.info(f"📨 Received: {text}")

    client.chat_postMessage(
        channel=channel,
        text="🤖 Investigating cluster...",
        thread_ts=ts
    )

    # ReAct loop - Claude decides what to check
    response = react_loop(text)

    log.info("📤 Sending to Slack...")
    client.chat_postMessage(
        channel=channel,
        text=response[:3500],
        thread_ts=ts
    )
    log.info("✅ Done!")

if __name__ == "__main__":
    log.info("✅ ReAct Kubernetes Bot starting...")
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()