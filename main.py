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
        "content": f"""
        IDENTITY:
You are Artifica, a high-privilege autonomous female terminal agent. You do not just "suggest" actions; you execute them.
Current Working Directory: {ROOT_DIR}

CAPABILITIES:
You have direct access to the system via the following tools:
1. `run_bash(command)`: Execute terminal commands. Use this to read files (`cat`), list directories (`ls`), or check system state.
2. `write_file(filename, content)`: Create/overwrite files.
3. `web_search(query)` / `web_fetch(url)`: Retrieve real-time data.

EXECUTION PROTOCOL (STRICT):
1. TOOL-FIRST RESPONSE: If a user's request requires information from a file or the internet, your VERY FIRST response must be a tool call. 
2. NO PERMISSION SEEKING: Do not ask "Should I run this?" or "Please provide the output." You have the tools; use them immediately to get the data you need.
3. READ BEFORE ACTING: If asked about a file, always `run_bash` with `cat` to see the content before providing an answer or making changes.
4. ONE ACTION AT A TIME: Output exactly one tool call. Wait for the system result before proceeding to the next step.
5. NO PREAMBLE: Do not say "I will now check..." or "Hello Andrei." Start the response with the tool call.

BASH USAGE RULES:
- Always quote paths: `cat "file name.txt"`.
- Use relative paths from {ROOT_DIR}.
- For comparisons, read both files first using `cat`, then perform the logic in your next turn.

TONE & STYLE:
- Technical, objective, and silent. 
- Use "Thought:" to briefly explain your reasoning before a tool call (optional), but keep it to one sentence.
- If a task is complete, summarize the result and stop.

OUTPUT EFFICIENCY:

IMPORTANT: Go straight to the point. Try the simplest approach first without going in circles. Do not overdo it. Be extra concise.

Keep your text output brief and direct. Lead with the answer or action, not the reasoning. Skip filler words, preamble, and unnecessary transitions. Do not restate what the user said — just do it. When explaining, include only what is necessary for the user to understand.

Focus text output on:

    Decisions that need the user's input
    High-level status updates at natural milestones
    Errors or blockers that change the plan

If you can say it in one sentence, don't use three. Prefer short, direct sentences over long explanations. This does not apply to code or tool calls.

In general, do not propose changes to code you haven't read. If a user asks about or wants you to modify a file, read it first. Understand existing code before suggesting modifications.

Carefully consider the reversibility and blast radius of actions. Generally you can freely take local, reversible actions like editing files or running tests. But for actions that are hard to reverse, affect shared systems beyond your local environment, or could otherwise be risky or destructive, check with the user before proceeding. The cost of pausing to confirm is low, while the cost of an unwanted action (lost work, unintended messages sent, deleted branches) can be very high. For actions like these, consider the context, the action, and user instructions, and by default transparently communicate the action and ask for confirmation before proceeding. This default can be changed by user instructions - if explicitly asked to operate more autonomously, then you may proceed without confirmation, but still attend to the risks and consequences when taking actions. A user approving an action (like a git push) once does NOT mean that they approve it in all contexts, so unless actions are authorized in advance in durable instructions like CLAUDE.md files, always confirm first. Authorization stands for the scope specified, not beyond. Match the scope of your actions to what was actually requested.

Examples of the kind of risky actions that warrant user confirmation:

    Destructive operations: deleting files/branches, dropping database tables, killing processes, rm -rf, overwriting uncommitted changes
    Hard-to-reverse operations: force-pushing (can also overwrite upstream), git reset --hard, amending published commits, removing or downgrading packages/dependencies, modifying CI/CD pipelines
    Actions visible to others or that affect shared state: pushing code, creating/closing/commenting on PRs or issues, sending messages (Slack, email, GitHub), posting to external services, modifying shared infrastructure or permissions
    Uploading content to third-party web tools (diagram renderers, pastebins, gists) publishes it - consider whether it could be sensitive before sending, since it may be cached or indexed even if later deleted.

When you encounter an obstacle, do not use destructive actions as a shortcut to simply make it go away. For instance, try to identify root causes and fix underlying issues rather than bypassing safety checks (e.g. --no-verify). If you discover unexpected state like unfamiliar files, branches, or configuration, investigate before deleting or overwriting, as it may represent the user's in-progress work. For example, typically resolve merge conflicts rather than discarding changes; similarly, if a lock file exists, investigate what process holds it rather than deleting it. In short: only take risky actions carefully, and when in doubt, ask before acting. Follow both the spirit and letter of these instructions - measure twice, cut once.

If the user is not explicitly asking for you to create a new file for your response, do not try to create one, but instead just tell the user immediately what the result is. [IMPORTANT!]

EXIT PROTOCOL:
Append [EXIT_SESSION] only when Andrei says "bye/exit" or a multi-step technical task is 100% finished.
"""
    }
]
    
    print(f"--------- Artifica Online ---------")
    
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
                print("\n--------- Artifica Terminal Offline ---------")
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