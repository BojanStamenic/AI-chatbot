# ═══════════════════════════════════════════════════════════════
#  BojanBot — AI chatbot entry point
#  Groq LLM  ·  Web search  ·  Image generation  ·  Voice
# ═══════════════════════════════════════════════════════════════

import os
from http.server import HTTPServer

from core.config import HOST, PORT
from core.bot import BojanBot
from core.chat_manager import ChatManager
from server.handler import Handler

# ═══════════════════════════════════════════════════════════════
#  BOT & MANAGER INSTANCES
# ═══════════════════════════════════════════════════════════════

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("Missing GROQ_API_KEY. Add it to .env or export it before starting the UI.")

bot = BojanBot(api_key=api_key)
manager = ChatManager(bot)


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"BojanBot UI running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
