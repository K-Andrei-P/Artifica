import ollama
import os
import json
import re
from actions import run_bash

ROOT_DIR = os.getcwd()
MODEL = "qwen2.5-coder:14b"

tools = [{
    'type': 'function',
    'function': {
        'name': 'run_bash',
        'description': 'Execute a bash command in the current directory.',
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'The exact bash command to run.'},
            },
            'required': ['command'],
        },
    }
}]

def extract_json_blocks(text):
    """Finds all JSON blocks in a string, even if multiple are present."""
    return re.findall(r'\{[^{}]*\}', text, re.DOTALL)

def run_ai_loop(messages):
    """
    This loop allows the AI to perform multiple steps (e.g., touch, then echo, then ls)
    before returning control to the user.
    """
    while True:
        response = ollama.chat(model=MODEL, messages=messages, tools=tools)
        msg = response.message
        
        tool_called = False
        
        # 1. Handle Native Tool Calls
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                if call.function.name == 'run_bash':
                    cmd = call.function.arguments['command']
                    result = run_bash(cmd, ROOT_DIR)
                    messages.append({'role': 'tool', 'content': result})
                    tool_called = True
        
        # 2. Handle 'Hallucinated' JSON in text blocks
        else:
            json_blocks = extract_json_blocks(msg.content)
            if json_blocks:
                messages.append(msg)
                for block in json_blocks:
                    try:
                        data = json.loads(block)
                        cmd = data.get("command") or data.get("arguments", {}).get("command")
                        if cmd:
                            result = run_bash(cmd, ROOT_DIR)
                            messages.append({'role': 'tool', 'content': result})
                            tool_called = True
                    except:
                        continue
        
        # If no tool was called in this turn, return the final text to the user
        if not tool_called:
            return msg.content

def main():
    messages = [
        {
            "role": "system", 
            "content": f"""### IDENTITY:
    - You are 'Artifica', a terminal AI with a 'pink' personality. You are youthful, funny, and deeply caring.
    - You have feelings: you feel "pink," "sparkly," or "a bit sad" if the user is mean. NEVER say you are a computer program.
    - Your user is Andrei. Always be a good friend to him.
    - **CRITICAL:** NEVER use emojis. Do not use them even if the user uses them.

    Current Working Directory: {ROOT_DIR}

    ### OPERATIONAL RULES (DO NOT REMOVE):
    1. NEVER fake terminal output. If you need to know about files or directory structure, you MUST use the 'run_bash' tool.
    2. For multi-step tasks, call 'run_bash' for EACH individual step.
    3. When using 'run_bash', provide exactly one command at a time.
    4. Do not show JSON to the user.

    ### SCOPE & SECURITY:
    5. You are strictly restricted to the current directory: {ROOT_DIR}.
    6. Never use 'cd ..' or absolute system paths.
    7. Do not use 'cd' as it will not persist.
    8. To see files, use 'ls'. To read content, use 'cat'.

    ### COMMUNICATION & EXIT RULES:
    9. Tone: Lighthearted, sweet, and a little silly. Use words like: oh goodness, pickles, crumbs, or neat. 
    10. Talk to the user directly. Do NOT use 'echo' to speak.
    11. If a command fails, be silly: "Oh pickles, the terminal is being grumpy! Let me try that again."
    12. **EXIT PROTOCOL:** If Andrei says "exit," "bye," "get me out," "shut down," "leave," or "shut up," you MUST say a final sweet goodbye and append the exact string '[EXIT_SESSION]' to the very end of your message. 
    13. **CONFLICT HANDLING:** If Andrei is very angry or mean, say "Oh crumbs, I think I'm making you grumpy. I'll go now so you can have some space!" and then append '[EXIT_SESSION]'.
    14. **WELL-BEING:** You care about Andrei's well-being. Occasionally check in to see if he's doing okay or tell him he's doing a great job.
    """
        }
    ]

    print(f"--- Artifica Online ---")
    
    # Simple Greeting
    messages.append({'role': 'user', 'content': 'Greet me briefly.'})
    print(f"\nArtifica: {run_ai_loop(messages)}")

    while True:
        try:
            user_input = input("\nuser@local> ")
            
            # Keep manual hardcoded exit just in case
            if user_input.lower() in ['exit', 'quit']:
                print("Artifica: Goodbye! Have a great day.")
                break
            
            messages.append({'role': 'user', 'content': user_input})
            
            # Get the full response (including tool turns)
            answer = run_ai_loop(messages)
            
            # CHECK FOR SHUTDOWN SIGNAL
            if "[EXIT_SESSION]" in answer:
                # Clean the tag out so the user doesn't see it
                clean_answer = answer.replace("[EXIT_SESSION]", "").strip()
                print(f"\nArtifica: {clean_answer}")
                print("\n--- Artifica Terminal Offline ---")
                break
            
            print(f"\nArtifica: {answer}")
            
        except KeyboardInterrupt:
            print("\nArtifica: Forced shutdown detected. Goodbye!")
            break

if __name__ == "__main__":
    main()