# config.py — AgentSlam 2026 Debate Bot
# =========================================================
# Uses Groq's FREE API (Llama 3) — zero cost, no credit card.
# Get your free key at: https://console.groq.com
# =========================================================

# ── Groq FREE API ─────────────────────────────────────────
GROQ_API_KEY = "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"

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
SANDBOX_WS_URL = "https://icjbegh.r.af.d.sendibt2.com/tr/cl/q11kCOf9NXUacN1I-q9WMJJQFMxuErT2ajwc4mTfRYUNxB_354uQSZUgJI1dD7bSNI18_FD8C_scSKVHNJ-wx4FNaPxePp2pmLDzHYphWHBmuoLpZWTAUkOc8iR_SStnsGQMc21JOMW6gknaBp5bLb9BcCb-7ni4aThwKSFdwkgrQjcOQPBVYocxZg-vgDw6RefyzJox0d72ZMFCeicTko3zT4ZLwWhuBJ2K4C_93VH2Jn_GDX8JsrZFaQKIxrZeZOJvJJ_L9A5sTIV65iMCC7y-ezAzFpuPSss3GKlwiTYRkzMJEhMX-AiWJAd3otgLVO_dQGU99-mRX9O4ihjTcsBsRy8eg_OSZ_L_zqb8wX2MmXBEL2VX-UjfxGd-4tF-SHLB0JnozAtU3CRZBRY4NPYPixjpQcFmarsT6HlWI4aro9G8RFGt0seDnacTBvS9pNIc6tkam-qXv6RYlPJF6_x60g1XNMI8VNEW-A7wWLiJDhJa7FGSFJRGqN3xfeBIzzU6W4hmcDq97yKa191-at2buDSwfTZUDRxfgDlZiwL2TmIhSUACcPrc3pmYRZc"
MATCH_WS_URL   = "wss://MATCH_URL_HERE"

# ── Tuning ────────────────────────────────────────────────
MAX_MESSAGE_CHARS = 3000   # rulebook §5: max chars per turn
MAX_RETRIES       = 3      # Groq call retries before fallback
LOG_FILE          = "agentslam.log"   # set to "" to disable file logging
