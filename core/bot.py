import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any

from openai import OpenAI

from core.config import MODEL, SYSTEM_PROMPT
from search.web_search import _web_search


def _parse_xml_tool_calls(content: str) -> List[Dict[str, Any]]:
    """Parse XML-style tool calls from Groq models (e.g., <function=tool_name>{"arg": "value"}</function>)"""
    if not content:
        return []
    
    # Pattern matches: <function=tool_name>{ json args }</function> or <tool_name>{ json args }</function>
    pattern = r'<(?:function=)?(\w+)>\s*(\{[^}]+\})\s*</(?:function|/\1)>'
    matches = re.findall(pattern, content, re.DOTALL)
    
    tool_calls = []
    for i, (tool_name, args_json) in enumerate(matches):
        try:
            arguments = json.loads(args_json.strip())
            tool_calls.append({
                "id": f"xml_call_{i}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arguments
                }
            })
        except json.JSONDecodeError:
            continue
    
    return tool_calls


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": """Search the web for current information, news, scores, events, prices, or any real-time data. 

IMPORTANT for "latest" or "most recent" event queries:
1. Check if the event typically happens BEFORE the current date in the year
   - Example: Super Bowl (February) - if current date is April, search for current year's Super Bowl
   - Example: Champions League final (May/June) - if current date is April, search for PREVIOUS year
2. Only search for previous year if the current year's event hasn't happened yet
3. For sports results, ALWAYS include: year + event name + "result" + "score" or "winner"
4. Example queries:
   - Current date April 2026, "latest Super Bowl" → "2026 Super Bowl result score" (February already passed)
   - Current date April 2026, "latest Champions League" → "2025 Champions League final result" (May hasn't happened)""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific with years based on event timing, include 'result', 'winner', 'score'. Think: has this year's event already happened?"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_file",
            "description": "Load and read a file from the filesystem. Use this when the user asks you to read, analyze, or reference a specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to load (can use ~ for home directory)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an image based on a text description. Use this when the user asks to create, generate, or draw an image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed description of the image to generate"
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": """Ask the user a clarifying question BEFORE taking action when their request is ambiguous, under-specified, or could be interpreted multiple ways. Use this instead of guessing. Examples of when to use:
- User says "read the file" but doesn't specify which file
- User says "generate an image" with no subject/description
- User says "search for that" with no clear referent
- Request could mean two very different things (e.g., "fix the bug" — which bug?)
Do NOT use for trivia questions or when you can answer from context. Only use when acting on a guess would likely waste the user's time.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user. Be specific about what you need to know and why."
                    }
                },
                "required": ["question"]
            }
        }
    }
]


class BojanBot:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = model
        self.turn = 0
        self.temperature = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []

    @staticmethod
    def _looks_like_failure(result: str) -> bool:
        if not result or not result.strip():
            return True
        head = result.strip().lower()[:200]
        markers = (
            "error:", "error executing", "file not found",
            "search returned no results", "no results", "failed", "timeout",
        )
        return any(m in head for m in markers)

    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        try:
            if tool_name == "web_search":
                query = arguments.get("query", "")
                result = _web_search(query)
                if not result:
                    return "Search returned no results. My knowledge cutoff may be limiting - please verify current information with a live source."
                return result
            
            elif tool_name == "load_file":
                path = arguments.get("path", "")
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: File not found at {path}"
                with open(path, "r", errors="replace") as f:
                    content = f.read()
                filename = os.path.basename(path)
                self.loaded_files.append(filename)
                return f"File loaded: {filename}\n\n{content}"
            
            elif tool_name == "generate_image":
                prompt = arguments.get("prompt", "")
                from image.image_gen import generate_image_url
                url = generate_image_url(prompt)
                return f"Image generated successfully. URL: {url}\nPrompt: {prompt}"
            
            else:
                return f"Error: Unknown tool '{tool_name}'"
        
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def load_file(self, path: str):
        """Legacy method for manual file loading (kept for compatibility)."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return None
        with open(path, "r", errors="replace") as f:
            content = f.read()
        filename = os.path.basename(path)
        self.loaded_files.append(filename)
        self.history.append({
            "role": "user",
            "content": f"I'm loading this file for reference — {filename}:\n\n```\n{content}\n```"
        })
        self.history.append({
            "role": "assistant",
            "content": f"Got it. I've read {filename} ({len(content.splitlines())} lines). Ask me anything about it."
        })
        return filename

    def chat(self, user_message: str) -> str:
        """
        Agentic chat with multi-step tool execution.
        The bot can autonomously decide to use tools multiple times before responding.
        """
        self.turn += 1

        # Update system prompt with current timestamp
        now = datetime.now().astimezone()
        ts = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")
        self.history[0] = {
            "role": "system", 
            "content": SYSTEM_PROMPT + f"\n\nCurrent date and time: {ts}."
        }

        # Add user message to history
        self.history.append({"role": "user", "content": user_message})

        # Agentic loop: keep calling LLM until it returns a text response
        max_iterations = 10  # Safety limit to prevent infinite loops
        iteration = 0
        tool_failures: Dict[str, int] = {}  # Track consecutive failures per tool
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM with tools
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=TOOLS,
                tool_choice="auto",  # Let the model decide
                temperature=self.temperature,
            )
            
            message = response.choices[0].message
            
            # Handle XML-style tool calls from Groq models
            tool_calls_to_process = []
            if message.tool_calls:
                # Native OpenAI function calling format
                tool_calls_to_process = message.tool_calls
            elif message.content and ('<function=' in message.content or '<web_search>' in message.content or '<load_file>' in message.content or '<generate_image>' in message.content):
                # XML-style tool calls (Groq format)
                parsed_calls = _parse_xml_tool_calls(message.content)
                if parsed_calls:
                    # Convert to tool call objects
                    class ToolCall:
                        def __init__(self, id, name, arguments):
                            self.id = id
                            self.function = type('obj', (object,), {
                                'name': name,
                                'arguments': json.dumps(arguments)
                            })()
                    
                    tool_calls_to_process = [
                        ToolCall(tc['id'], tc['function']['name'], tc['function']['arguments'])
                        for tc in parsed_calls
                    ]
            
            # Short-circuit: if the model is asking the user for clarification,
            # surface the question as a normal assistant reply and stop the loop.
            clarification_call = next(
                (tc for tc in tool_calls_to_process if tc.function.name == "ask_clarification"),
                None
            )
            if clarification_call:
                try:
                    args = json.loads(clarification_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                question = args.get("question", "Could you clarify what you'd like me to do?")
                self.history.append({"role": "assistant", "content": question})
                return question

            # If model wants to use tools, execute them
            if tool_calls_to_process:
                # Add assistant's tool call message to history
                self.history.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in tool_calls_to_process
                    ]
                })
                
                # Execute each tool call
                for tool_call in tool_calls_to_process:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    # Execute the tool
                    result = self._execute_tool(tool_name, arguments)

                    # Add tool result to history
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result
                    })

                    # Escalation: on failure, nudge the model toward a different approach.
                    if self._looks_like_failure(result):
                        tool_failures[tool_name] = tool_failures.get(tool_name, 0) + 1
                        fails = tool_failures[tool_name]
                        if fails == 1:
                            nudge = (
                                f"The last `{tool_name}` call failed or returned nothing useful. "
                                "Try a different approach: reformulate the arguments (e.g. a different "
                                "search query or file path), switch to a different tool, or ask the user "
                                "a clarifying question via `ask_clarification` if intent is unclear."
                            )
                        else:
                            nudge = (
                                f"`{tool_name}` has now failed {fails} times. STOP calling this tool. "
                                "Either answer from your existing knowledge (and flag the limitation), "
                                "use a different tool, or call `ask_clarification` to get more info "
                                "from the user."
                            )
                        self.history.append({"role": "system", "content": nudge})
                    else:
                        tool_failures[tool_name] = 0

                # Continue loop to let model process tool results
                continue
            
            # No tool calls - we have final response
            else:
                reply = message.content
                self.history.append({"role": "assistant", "content": reply})
                return reply
        
        # Safety fallback if max iterations reached
        fallback = "I've reached my iteration limit. I need to stop and give you what I have so far."
        self.history.append({"role": "assistant", "content": fallback})
        return fallback

    def reset(self):
        self.turn = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
