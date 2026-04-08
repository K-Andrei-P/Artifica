import ollama
import os
import json
import re
from actions import run_bash, write_file, web_search, web_fetch

ROOT_DIR = os.getcwd()
MODEL = "qwen2.5-coder:14b"
PROTOCOLS_DIR = "/Users/artificus/Documents/GitHubProjects/Artifica/protocols"

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
    },
    {
    'type': 'function',
    'function': {
        'name': 'edit_file',
        'description': 'Replace a specific block of text in a file with new text.',
        'parameters': {
            'type': 'object',
            'properties': {
                'filename': {'type': 'string', 'description': 'The file to edit.'},
                'old_text': {'type': 'string', 'description': 'The exact text to be replaced.'},
                'new_text': {'type': 'string', 'description': 'The new text to insert.'},
            },
            'required': ['filename', 'old_text', 'new_text'],
            },
        }
    }
    
]

class ArtificaPipeline:
    def __init__(self):
        self.base_protocols = ["base_identity.txt", "personality_social.txt", "exit_protocol.txt"]
        self.available_protocols = {
            "maid_cleanup": "maid_cleanup.txt",
            "reporting": "reporting.txt",
            "web_ops" : "system_ops.txt",
            "bash_ops" : "system_ops.txt"
        }
        # --- MEMORY STORED IN RAM ---
        self.memory_bank = [] 

    def load_protocol_text(self, filename):
        path = os.path.join(PROTOCOLS_DIR, filename)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read().replace("{ROOT_DIR}", ROOT_DIR)
        return ""
        
    def router_phase(self, user_input):
        startup_rules = self.load_protocol_text("startup.txt")
        
        # Give the router the last 2 items from memory so it has context
        context = "\n".join(self.memory_bank[-2:]) if self.memory_bank else "No previous context."
        
        messages = [
            {"role": "system", "content": startup_rules},
            {"role": "user", "content": f"Context: {context}\nMaster's Request: {user_input}\nAnalyze and return the JSON list."}
        ]
        response = ollama.chat(model=MODEL, messages=messages)
        content = response.message.content
        try:
            json_match = re.search(r'\[.*\]', content)
            selected = json.loads(json_match.group()) if json_match else []
            return selected
        except:
            return []

    def assemble_final_prompt(self, user_input, selected_protocols):
        full_prompt = "--- ARTIFICA ACTIVE PROTOCOLS ---\n"
        for p in self.base_protocols:
            full_prompt += self.load_protocol_text(p) + "\n"
        for p_key in selected_protocols:
            if p_key in self.available_protocols:
                full_prompt += self.load_protocol_text(self.available_protocols[p_key]) + "\n"
        
        # --- IMPROVED MEMORY INJECTION ---
        if self.memory_bank:
            full_prompt += "\n[HISTORICAL ARCHIVE - FOR REFERENCE ONLY]\n"
            full_prompt += "The following is a compressed log of previous turns in this session. "
            full_prompt += "Do NOT repeat this information or summarize it unless the Master explicitly asks about past events.\n"
            full_prompt += "--- START ARCHIVE ---\n"
            full_prompt += "\n".join([f"- {m}" for m in self.memory_bank]) + "\n"
            full_prompt += "--- END ARCHIVE ---\n"
        
        full_prompt += f"\n--- MASTER'S CURRENT GOAL ---\n{user_input}\n"
        full_prompt += "\nFocus exclusively on the CURRENT GOAL. Use the ARCHIVE only if context is required. Begin execution."
        return full_prompt


def extract_json_blocks(text):
    results = []
    stack = 0
    start_idx = -1
    for i, char in enumerate(text):
        if char == '{':
            if stack == 0: start_idx = i
            stack += 1
        elif char == '}':
            stack -= 1
            if stack == 0 and start_idx != -1:
                results.append(text[start_idx:i+1])
    return results

def get_compact_summary(user_msg, assistant_msg, protocol_loader):
    """Internal logic to summarize the turn using compact.txt instructions."""
    system_instruction = protocol_loader("compact.txt")
    if not system_instruction:
        return None
    
    prompt = f"User Request: {user_msg}\nAssistant Response: {assistant_msg}"
    
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {'role': 'system', 'content': system_instruction},
                {'role': 'user', 'content': prompt}
            ]
        )
        return response.message.content.strip()
    except:
        return None

def run_ai_loop(messages, pipeline, system_prompt=None, allow_tools=True):
    # Ensure system prompt is set
    if messages and messages[0]['role'] == 'system':
        messages[0]['content'] = system_prompt
    else:
        messages.insert(0, {'role': 'system', 'content': system_prompt})

    retry_count = 0
    loop_limit = 10
    
    for _ in range(loop_limit):
        current_tools = tools if allow_tools else None
        response = ollama.chat(model=MODEL, messages=messages, tools=current_tools)
        msg = response.message
        
        # 1. Error Handling: Nudge if the AI gives up too easily
        gave_up_phrases = ["unable to access", "cannot browse", "visit the links", "external websites"]
        if any(phrase in msg.content.lower() for phrase in gave_up_phrases) and retry_count < 2:
            messages.append(msg)
            messages.append({'role': 'user', 'content': "Error: You HAVE tools. If one method fails, try another. Do not apologize, just execute."})
            retry_count += 1
            continue

        tool_called = False

        # 2. Handle Native Tool Calls
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                func_name = call.function.name
                args = call.function.arguments
                
                print(f"  [Artifica executing {func_name}...]")
                if func_name == 'run_bash': result = run_bash(args.get('command', ''), ROOT_DIR)
                elif func_name == 'write_file': result = write_file(args.get('filename', ''), args.get('content', ''), ROOT_DIR)
                elif func_name == 'edit_file': result = edit_file(args.get('filename', ''), args.get('old_text', ''), args.get('new_text', ''), ROOT_DIR)
                elif func_name == 'web_search': result = web_search(args.get('query', ''))
                elif func_name == 'web_fetch': result = web_fetch(args.get('url', ''))
                else: result = f"Error: Tool '{func_name}' not recognized."
                
                messages.append({'role': 'tool', 'content': result})
                tool_called = True
        
        # 3. Handle Hallucinated JSON
        else:
            json_blocks = extract_json_blocks(msg.content)
            if json_blocks:
                messages.append(msg)
                for block in json_blocks:
                    try:
                        data = json.loads(block)
                        name = data.get("name") or data.get("tool")
                        args = data.get("arguments") or data.get("args") or data
                        
                        if not name: 
                            if "command" in data: name = "run_bash"
                            elif "filename" in data: name = "write_file"
                            elif "old_text" in data: name = "edit_file"

                        print(f"  [Artifica executing hallucinated {name}...]")
                        if name == 'run_bash': result = run_bash(args.get('command', ''), ROOT_DIR)
                        elif name == 'write_file': result = write_file(args.get('filename', ''), args.get('content', ''), ROOT_DIR)
                        elif name == 'edit_file': result = edit_file(args.get('filename', ''), args.get('old_text', ''), args.get('new_text', ''), ROOT_DIR)
                        elif name == 'web_search': result = web_search(args.get('query', ''))
                        elif name == 'web_fetch': result = web_fetch(args.get('url', ''))
                        else: continue 
                        
                        messages.append({'role': 'tool', 'content': result})
                        tool_called = True
                    except Exception as e:
                        messages.append({'role': 'tool', 'content': f"JSON Error: {e}"})
                        tool_called = True

        if not tool_called:
            user_input = "N/A"
            for m in reversed(messages):
                if m['role'] == 'user':
                    user_input = m['content']
                    break
            
            summary = get_compact_summary(user_input, msg.content, pipeline.load_protocol_text)
            if summary:
                pipeline.memory_bank.append(summary)
            return msg.content

    return "Error: Maximum execution steps reached (Loop Protection)."

def main():
    pipeline = ArtificaPipeline()
    messages = []

    print(f"--------- Artifica Online ---------")
    
    greeting_prompt = pipeline.load_protocol_text("base_identity.txt") + \
                      pipeline.load_protocol_text("personality_social.txt")
    
    initial_msg = [{'role': 'system', 'content': greeting_prompt},
                   {'role': 'user', 'content': 'Greet me briefly and tell me you are at my service.'}]
    
    greeting = run_ai_loop(initial_msg, pipeline, greeting_prompt, allow_tools=False)
    print(f"\nArtifica: {greeting}")

    while True:
        try:
            user_input = input("\nuser@local> ")
            if user_input.lower() in ['exit', 'quit', 'bye', 'goodbye']:
                break
            
            print(f"  [Analyzing protocols...]")
            needed_protocols = pipeline.router_phase(user_input)
            print(f"  [Needed protocols: {needed_protocols}]")
            dynamic_system_prompt = pipeline.assemble_final_prompt(user_input, needed_protocols)
            
            messages.append({'role': 'user', 'content': user_input})
            answer = run_ai_loop(messages, pipeline, dynamic_system_prompt)
            
            if "[EXIT_SESSION]" in answer:
                print(f"\nArtifica: {answer.replace('[EXIT_SESSION]', '').strip()}")
                break
            else:
                print(f"\nArtifica: {answer}")
            
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()