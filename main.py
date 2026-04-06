import ollama
import os
import json
import re
from actions import run_bash, write_file, web_search, web_fetch

ROOT_DIR = os.getcwd()
MODEL = "qwen2.5-coder:14b"
PROTOCOLS_DIR = "protocols"

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
        messages = [
            {"role": "system", "content": startup_rules},
            {"role": "user", "content": f"Analyze this request from Master: '{user_input}'"}
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

def run_ai_loop(messages, pipeline, system_prompt=None):
    """
    Added 'pipeline' as an argument so the loop can update 
    the RAM-based memory_bank.
    """
    if messages and messages[0]['role'] == 'system':
        messages[0]['content'] = system_prompt
    else:
        messages.insert(0, {'role': 'system', 'content': system_prompt})

    while True:
        response = ollama.chat(model=MODEL, messages=messages, tools=tools)
        msg = response.message
        
        gave_up_phrases = ["unable to access", "cannot browse", "visit the links", "external websites"]
        if any(phrase in msg.content.lower() for phrase in gave_up_phrases) and retry_count < 2:
            print("  [System Nudge: Forcing Artifica to retry with a different source...]")
            messages.append(msg)
            messages.append({
                'role': 'user', 
                'content': "Error: You HAVE web tools. If one URL fails, try another one from your search results. Do not apologize, just find the data."
            })
            retry_count += 1
            continue

        tool_called = False
        # 1. Handle Native Tool Calls
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                func_name = call.function.name
                args = call.function.arguments
                
                # Validation
                if func_name == 'run_bash' and args.get('command', '').strip().startswith('echo'):
                    messages.append({'role': 'tool', 'content': "Error: Use plain text."})
                    continue

                print(f"  [Artifica executing {func_name}...]")
                if func_name == 'run_bash': result = run_bash(args.get('command', ''), ROOT_DIR)
                elif func_name == 'write_file': result = write_file(args.get('filename', ''), args.get('content', ''), ROOT_DIR)
                elif func_name == 'web_search': result = web_search(args.get('query', ''))
                elif func_name == 'web_fetch': result = web_fetch(args.get('url', ''))
                else: result = f"Error: Tool '{func_name}' not recognized."
                messages.append({'role': 'tool', 'content': result})
                tool_called = True
        
        # 2. Handle Hallucinated JSON
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
                            elif "query" in data: name = "web_search"
                            elif "url" in data: name = "web_fetch"

                        print(f"  [Artifica executing hallucinated {name}...]")
                        if name == 'run_bash': result = run_bash(args.get('command', ''), ROOT_DIR)
                        elif name == 'write_file':
                                filename = args.get('filename', '')
                                content = args.get('content', '')

                                # --- FIX: PLACEHOLDER DETECTION ---
                                placeholders = ["<tool_response>", "<tool_output>", "None", "undefined", "[RESULT]"]
                                if any(p in content.lower() for p in placeholders) or len(content.strip()) < 5:
                                    result = "Error: You attempted to write a placeholder or empty content. " \
                                            "You must wait for the web_fetch/web_search results to return " \
                                            "to you before you can write them to a file."
                                else:
                                    result = write_file(filename, content, ROOT_DIR)
                        elif name == 'web_search': result = web_search(args.get('query', ''))
                        elif name == 'web_fetch': result = web_fetch(args.get('url', ''))
                        else: continue 
                        
                        messages.append({'role': 'tool', 'content': result})
                        tool_called = True
                    except Exception as e:
                        messages.append({'role': 'tool', 'content': f"JSON Error: {e}"})
                        tool_called = True
                        continue

        # --- COMPACTION LOGIC (IF FINAL RESPONSE) ---
        if not tool_called:
            # Get the original user input from the message history
            user_input = "N/A"
            for m in reversed(messages):
                if m['role'] == 'user':
                    user_input = m['content']
                    break
            
            # Use the compaction prompt to summarize
            summary = get_compact_summary(user_input, msg.content, pipeline.load_protocol_text)
            if summary:
                pipeline.memory_bank.append(summary)
                print(pipeline.memory_bank)
                print(f"  [Memory compacted and stored in RAM]")

            return msg.content

def main():
    pipeline = ArtificaPipeline()
    messages = []

    print(f"--------- Artifica Online ---------")
    
    greeting_prompt = pipeline.load_protocol_text("base_identity.txt") + \
                      pipeline.load_protocol_text("personality_social.txt")
    
    initial_msg = [{'role': 'system', 'content': greeting_prompt},
                   {'role': 'user', 'content': 'Greet me briefly and tell me you are at my service.'}]
    
    # Note: Added pipeline to argument
    greeting = run_ai_loop(initial_msg, pipeline, greeting_prompt)
    print(f"\nArtifica: {greeting}")

    while True:
        try:
            user_input = input("\nuser@local> ")
            if user_input.lower() in ['exit', 'quit', 'bye', 'goodbye']:
                break
            
            print(f"  [Analyzing protocols...]")
            needed_protocols = pipeline.router_phase(user_input)
            dynamic_system_prompt = pipeline.assemble_final_prompt(user_input, needed_protocols)
            
            messages.append({'role': 'user', 'content': user_input})
            # Note: Added pipeline to argument
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