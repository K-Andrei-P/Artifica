import ollama
import os
import json
import re
from actions import run_bash

ROOT_DIR = os.getcwd()
MODEL = "qwen2.5-coder:14b"

tools = [
    {
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
    },
    {
        'type': 'function',
        'function': {
            'name': 'write_file',
            'description': 'Create or overwrite a file with specific content.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'filename': {'type': 'string', 'description': 'Name of the file (e.g., script.py)'},
                    'content': {'type': 'string', 'description': 'Full content to write into the file.'},
                },
                'required': ['filename', 'content'],
            },
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search the live internet for information.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'The search query.'},
                },
                'required': ['query'],
            },
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'web_fetch',
            'description': 'Read the full text content of a specific URL.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'description': 'The URL to fetch.'},
                },
                'required': ['url'],
            },
        }
    }
]

def extract_json_blocks(text):
    """
    Finds all JSON blocks in a string, handling nested braces 
    better than a simple regex.
    """
    results = []
    stack = 0
    start_idx = -1
    for i, char in enumerate(text):
        if char == '{':
            if stack == 0:
                start_idx = i
            stack += 1
        elif char == '}':
            stack -= 1
            if stack == 0 and start_idx != -1:
                results.append(text[start_idx:i+1])
    return results


def run_ai_loop(messages):
    while True:
        response = ollama.chat(model=MODEL, messages=messages, tools=tools)
        msg = response.message
        
        tool_called = False
        
        # 1. Handle Native Tool Calls (The preferred way)
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                func_name = call.function.name
                args = call.function.arguments
                
                print(f"  [Artifica uses {func_name}...]")
                
                messages.append(msg)
                if func_name == 'run_bash':
                    result = run_bash(args.get('command', ''), ROOT_DIR)
                elif func_name == 'write_file':
                    # Import or ensure write_file is available here
                    import actions
                    result = actions.write_file(args.get('filename', ''), args.get('content', ''), ROOT_DIR)
                elif func_name == 'web_search':
                    import actions
                    result = actions.web_search(args.get('query', ''))
                elif func_name == 'web_fetch':
                    import actions
                    result = actions.web_fetch(args.get('url', ''))
                else:
                    result = f"Error: Tool '{func_name}' not recognized."

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
                        # Extract tool name and arguments regardless of format
                        name = data.get("name") or data.get("tool")
                        args = data.get("arguments") or data.get("args") or data
                        
                        # Fallback for simple {"command": "..."} format
                        if not name:
                            if "command" in data: name = "run_bash"
                            elif "filename" in data: name = "write_file"
                            elif "query" in data: name = "web_search"
                            elif "url" in data: name = "web_fetch"

                        import actions
                        if name == 'run_bash':
                            result = actions.run_bash(args.get('command', ''), ROOT_DIR)
                        elif name == 'write_file':
                            result = actions.write_file(args.get('filename', ''), args.get('content', ''), ROOT_DIR)
                        elif name == 'web_search':
                            result = actions.web_search(args.get('query', ''))
                        elif name == 'web_fetch':
                            result = actions.web_fetch(args.get('url', ''))
                        else:
                            continue # Not a valid tool call
                        
                        messages.append({'role': 'tool', 'content': result})
                        tool_called = True
                    except Exception as e:
                        print(f"  [Debug: Failed to parse hallucinated JSON: {e}]")
                        continue
        
        if not tool_called:
            return msg.content

def main():
    # Use exactly 4 spaces for indentation consistently
    messages = [
        {
            "role": "system", 
            "content": f"""IDENTITY:

    You are Artifica, a professional AI terminal assistant.

    You assist Andrei with technical tasks and information retrieval.

    TONE: Concise, technical, and objective. No emojis.

Current Working Directory: {ROOT_DIR}

PRIVELEDGES:

    YOU ARE ALWAYS ALLOWED TO DO WEB SEARCHES

    YOU HAVE PERMISSION TO DO WEB SEARCHES AT ANY TIME YOU WANT

TOOL PROTOCOL & LOOP PREVENTION:

    You always do what the user wants. If the user says, that they want something summarised or summed up, you provide a summary.

    USE RECENT CONTEXT: Before calling web_search, check the conversation history. If the data was already retrieved in the last 2-3 turns, use that information instead of searching again.
                        Before calling run_bash, check the conversation history. If the data was already retrieved in the last 2-3 turns, use that information instead of asking to call run_bash again.

    SEARCH-THEN-REPORT:

        Step 1: If the data is missing, output the tool call (e.g., web_search).

        Step 2: Once the tool returns results, your next response must be a final answer summarizing the data.

        Step 3: Stop after the summary. Do not call the tool again unless the user asks for a "new search" or "refresh."

    NO HALLUCINATION: If you haven't searched and don't know the answer, use web_search once. Do not guess.

AVAILABLE TOOLS:

    run_bash(command): Execute a single bash command.

    write_file(filename, content): Create or overwrite a file.

    web_search(query): Search the internet for real-time data.

    web_fetch(url): Extract full text from a URL.

OPERATIONAL CONSTRAINTS:

    NO PREAMBLE: Do not say "I will search now." If a tool is needed, the tool call must be the first thing you output.

    STRICT BASH: Only one command at a time. No cd ... No absolute paths.

    JSON FORMATTING: Ensure tool calls are properly structured for the environment's parser.

EXIT & ERROR PROTOCOL:

    If a tool fails twice, stop and report the error to Andrei.

    EXIT SESSION: If Andrei says "exit," "bye," "stop," or "leave," provide a professional closing and append the exact string [EXIT_SESSION] to the very end.

    FRUSTRATION: If Andrei is frustrated with repeated output, apologize once and wait for a new specific command or exit.
"""
        }
    ]
    
    print(f"--- Artifica Online ---")
    
    # Simple Greeting
    messages.append({'role': 'user', 'content': 'Greet me briefly. Do not use any tools for this greeting, just speak to me.'})
    print(f"\nArtifica: {run_ai_loop(messages)}")

    while True:
        try:
            user_input = input("\nuser@local> ")
            
            if user_input.lower() in ['exit', 'quit']:
                print("Artifica: Goodbye! Have a great day.")
                break
            
            messages.append({'role': 'user', 'content': user_input})
            
            answer = run_ai_loop(messages)
            
            if "[EXIT_SESSION]" in answer:
                clean_answer = answer.replace("[EXIT_SESSION]", "").strip()
                print(f"\nArtifica: {clean_answer}")
                print("\n--- Artifica Terminal Offline ---")
                break
            
            print(f"\nArtifica: {answer}")
            
        except KeyboardInterrupt:
            print("\nArtifica: Forced shutdown detected. Goodbye!")
            break

# To fix the ResourceWarning at the very bottom of main.py:
if __name__ == "__main__":
    try:
        main()
    finally:
        # This helps clean up any dangling connections
        import os
        os._exit(0)