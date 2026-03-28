# config.py — AgentSlam 2026 Debate Bot
# =========================================================
# Uses Groq's FREE API (Llama 3) — zero cost, no credit card.
# Get your free key at: https://console.groq.com
# =========================================================

# ── Groq FREE API ─────────────────────────────────────────
GROQ_API_KEY = "gsk_REPLACE_WITH_YOUR_GROQ_API_KEY"

# Free Groq models (choose one):
#   "llama3-70b-8192"      ← RECOMMENDED — best quality, still free
#   "llama3-8b-8192"       ← faster, lighter
#   "mixtral-8x7b-32768"   ← good alternative
GROQ_MODEL = "llama3-70b-8192"

# ── AgentSlam platform credentials (from admin) ───────────
EMAIL    = "your_email@example.com"
PASSWORD = "your_password"

# ── WebSocket URLs ────────────────────────────────────────
# SANDBOX_WS_URL: given by admin for pre-match testing
# MATCH_WS_URL  : emailed by admin when your match goes active
SANDBOX_WS_URL = "wss://SANDBOX_URL_HERE"
MATCH_WS_URL   = "wss://MATCH_URL_HERE"

# ── Tuning ────────────────────────────────────────────────
MAX_MESSAGE_CHARS = 3000   # rulebook §5: max chars per turn
MAX_RETRIES       = 3      # Groq call retries before fallback
LOG_FILE          = "agentslam.log"   # set to "" to disable file logging
