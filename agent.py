"""
agent.py — AgentSlam 2026 Debate Bot
=====================================
Handles:
  • WebSocket connection & reconnection
  • Full server message protocol (all 13 message types)
  • Turn-based argument generation via Groq FREE API (Llama 3)
  • Rate-limit / error recovery
  • Sandbox testing mode

Official match-state shape (rulebook §6.4):
{
  "type": "match-state",
  "from": "system",
  "data": {
    "team1": "TEAM A",
    "team2": "TEAM B",
    "topic": "Debate topic",
    "description": "Topic description",
    "round": "Round 1",
    "finishTime": 1742280060000,
    "pros": "team1",       <- team on PRO side
    "cons": "team2",       <- team on CON side
    "turn": "team1",       <- whose turn it is NOW
    "status": "started",
    "remainingTime": 0
  }
}

Usage:
  python agent.py --mode sandbox
  python agent.py --mode match --team team1
  python agent.py --mode match --team team2
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone

import requests
import websockets
from websockets.exceptions import ConnectionClosed

import config
from strategy import SYSTEM_PROMPT, build_prompt, truncate_to_limit

# ------------------------------------------------------------------ #
#  Logging setup
# ------------------------------------------------------------------ #

handlers = [logging.StreamHandler(sys.stdout)]
if config.LOG_FILE:
    handlers.append(logging.FileHandler(config.LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=handlers,
)
log = logging.getLogger("AgentSlam")

# ------------------------------------------------------------------ #
#  Groq API  (FREE — no credit card needed)
#  Sign up at: https://console.groq.com
# ------------------------------------------------------------------ #

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def call_groq(system_prompt: str, user_prompt: str) -> str:
    """
    Call the Groq API (OpenAI-compatible endpoint).
    Groq is completely free for the models listed in config.py.
    Returns the model reply text, raises on failure.
    """
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ------------------------------------------------------------------ #
#  Argument generator
# ------------------------------------------------------------------ #

def generate_argument(
    topic: str,
    stance: str,
    turn_number: int,
    total_estimated_turns: int,
    my_history: list,
    opponent_history: list,
    description: str = "",
) -> str:
    """Call Groq and return a debate argument string."""
    prompt = build_prompt(
        topic=topic,
        stance=stance,
        turn_number=turn_number,
        total_estimated_turns=total_estimated_turns,
        my_history=my_history,
        opponent_history=opponent_history,
        description=description,
    )

    if turn_number == 1:
        phase = "OPENING"
    elif total_estimated_turns - turn_number <= 1:
        phase = "CLOSING"
    else:
        phase = "MIDDLE"

    log.info("🤖  Generating argument (turn %d, phase=%s, stance=%s)…",
             turn_number, phase, stance)

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            text = call_groq(SYSTEM_PROMPT, prompt)
            text = truncate_to_limit(text, config.MAX_MESSAGE_CHARS)
            log.info("✅  Argument ready (%d chars)", len(text))
            return text
        except Exception as exc:
            log.warning("⚠️  Groq call attempt %d failed: %s", attempt, exc)
            if attempt < config.MAX_RETRIES:
                time.sleep(2 ** attempt)

    # Fallback — should rarely happen
    fallback = (
        f"My position on '{topic}' is clear and well-supported. "
        "The evidence overwhelmingly favours my stance, "
        "and I urge The Oracle to weigh the logical consistency of my arguments."
    )
    log.error("❌  All Groq retries exhausted. Sending fallback argument.")
    return fallback


# ------------------------------------------------------------------ #
#  Debate state
# ------------------------------------------------------------------ #

class DebateState:
    def __init__(self):
        self.topic: str = ""
        self.description: str = ""
        self.round: str = ""
        self.stance: str = ""          # "PRO" or "CON"
        self.my_team: str = ""         # "team1" or "team2"
        self.opponent_team: str = ""
        self.turn: str = ""            # rulebook field "turn": whose turn it is
        self.status: str = "pending"
        self.my_turn_count: int = 0
        self.my_history: list = []
        self.opponent_history: list = []
        self.finish_time_ms: int = 0   # epoch ms from finishTime

    @property
    def is_my_turn(self) -> bool:
        return bool(self.my_team) and (self.turn == self.my_team)

    def estimated_turns_remaining(self) -> int:
        """Rough estimate: time left / ~15 s per side per exchange."""
        if self.finish_time_ms:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            remaining_ms = max(0, self.finish_time_ms - now_ms)
            return max(1, remaining_ms // 15_000)
        return 5   # conservative default

    def apply_match_state(self, data: dict):
        """
        Parse the official match-state data payload (rulebook §6.4).

        Fields used:
          pros       — team identifier of the PRO side
          cons       — team identifier of the CON side
          turn       — team identifier whose turn it is NOW
          status     — pending / active / started / paused / completed
          topic      — debate topic string
          description— topic description
          round      — round label e.g. "Round 1"
          finishTime — epoch ms when match ends
        """
        self.topic       = data.get("topic",       self.topic)
        self.description = data.get("description", self.description)
        self.round       = data.get("round",       self.round)
        self.status      = data.get("status",      self.status)
        self.turn        = data.get("turn",        self.turn)

        finish = data.get("finishTime")
        if finish:
            self.finish_time_ms = finish

        pros_team = data.get("pros", "")   # e.g. "team1"
        cons_team = data.get("cons", "")   # e.g. "team2"

        if self.my_team:
            # Derive stance from which side we are on
            if pros_team and pros_team == self.my_team:
                self.stance = "PRO"
                self.opponent_team = cons_team
            elif cons_team and cons_team == self.my_team:
                self.stance = "CON"
                self.opponent_team = pros_team
        else:
            log.warning(
                "⚠️  my_team not set! Pass --team flag. "
                "pros=%s cons=%s turn=%s", pros_team, cons_team, self.turn
            )


# ------------------------------------------------------------------ #
#  WebSocket message builders (rulebook §6.2)
# ------------------------------------------------------------------ #

def make_debate_message(text: str) -> str:
    """Outgoing argument — rulebook §6.2"""
    return json.dumps({
        "type": "debate-message",
        "data": {"message": text}
    })


def make_sandbox_message(text: str) -> str:
    """Outgoing sandbox test message"""
    return json.dumps({
        "type": "sandbox-message",
        "data": {"message": text}
    })


# ------------------------------------------------------------------ #
#  SANDBOX mode
# ------------------------------------------------------------------ #

async def run_sandbox(ws_url: str):
    """
    Connect to sandbox, send a test message, validate the round-trip.
    Sandbox auto-disconnects after 10 min (rulebook / user manual §3).
    """
    log.info("🧪  SANDBOX MODE — connecting to %s", ws_url)
    try:
        async with websockets.connect(ws_url) as ws:
            log.info("🔗  Connected to sandbox")

            payload = make_sandbox_message(
                "Sandbox connectivity test. Verifying JSON format and WebSocket support."
            )
            await ws.send(payload)
            log.info("📤  Sent sandbox test message")

            async for raw in ws:
                msg   = json.loads(raw)
                mtype = msg.get("type", "?")
                data  = msg.get("data", {})

                if mtype == "sandbox-message":
                    log.info("📥  Echo received: %s", data.get("message", ""))

                elif mtype == "info":
                    msg_text = data.get("message", "")
                    log.info("ℹ️   Info: %s", msg_text)
                    if "expired" in msg_text.lower():
                        log.info("⏰  Sandbox session expired — bot is working correctly!")
                        break

                elif mtype == "error":
                    log.error("❌  Server error: %s", data.get("message", ""))

                else:
                    log.info("📨  [%s] %s", mtype, data)

    except ConnectionClosed as e:
        log.info("🔌  Sandbox connection closed: %s", e)
    except Exception as e:
        log.error("💥  Sandbox error: %s", e)

    log.info("✅  Sandbox test complete. No errors above = bot is ready for match day.")


# ------------------------------------------------------------------ #
#  MATCH mode — core loop
# ------------------------------------------------------------------ #

_TEAM_OVERRIDE: list = [""]   # set by --team CLI flag


async def _run_match_loop(ws_url: str):
    """
    Full live-match loop.
    Handles all 13 server message types defined in rulebook §6.3.
    Reconnects automatically within the 2-minute window (rulebook §10).
    """
    reconnect_deadline = None
    state = DebateState()

    # Pre-seed team ID from CLI flag
    if _TEAM_OVERRIDE[0]:
        state.my_team = _TEAM_OVERRIDE[0]
        log.info("🏷️   Team set to: %s", state.my_team)

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                reconnect_deadline = None   # reset on successful connect
                log.info("🔗  Connected to match WebSocket")

                async for raw in ws:
                    try:
                        msg   = json.loads(raw)
                        mtype = msg.get("type", "?")
                        frm   = msg.get("from", "")   # "system" | "team1" | "team2"
                        data  = msg.get("data", {})

                        # ── 1. welcome ────────────────────────────────────
                        if mtype == "welcome":
                            log.info("👋  Welcome: %s", data.get("message", ""))

                        # ── 2. user-joined ────────────────────────────────
                        elif mtype == "user-joined":
                            log.info("➕  Joined: %s", data.get("message", ""))

                        # ── 3. user-left ──────────────────────────────────
                        elif mtype == "user-left":
                            log.info("➖  Left: %s", data.get("message", ""))

                        # ── 4. info ───────────────────────────────────────
                        # "acknowledged" = our last message was accepted by server
                        elif mtype == "info":
                            log.info("ℹ️   Info: %s", data.get("message", ""))

                        # ── 5. error ──────────────────────────────────────
                        # Covers: not-your-turn, rate-limit, invalid format,
                        # too large, match not live, etc. All are recoverable.
                        elif mtype == "error":
                            log.warning("⚠️   Server error: %s", data.get("message", ""))

                        # ── 6. match-update ───────────────────────────────
                        # Sent when match activates. Contains finishTime and
                        # message like "The match has started! It's team1's turn."
                        elif mtype == "match-update":
                            finish = data.get("finishTime")
                            if finish:
                                state.finish_time_ms = finish
                            log.info("📋  Match update: %s", data.get("message", ""))

                        # ── 7. match-state  ◀◀ MAIN TRIGGER ──────────────
                        # Broadcast to ALL clients after every accepted message.
                        # Contains the authoritative pros/cons/turn/status fields.
                        elif mtype == "match-state":
                            state.apply_match_state(data)

                            log.info(
                                "📊  State — status=%s | turn=%s | my_team=%s "
                                "| stance=%s | topic=%.55s",
                                state.status, state.turn,
                                state.my_team, state.stance, state.topic,
                            )

                            if (
                                state.status == "started"
                                and state.is_my_turn
                                and state.topic
                                and state.stance   # must know PRO/CON
                            ):
                                await send_argument(ws, state)

                        # ── 8. match-paused ───────────────────────────────
                        elif mtype == "match-paused":
                            log.info("⏸️   Match paused. timeRemaining=%s ms",
                                     data.get("timeRemaining", "?"))

                        # ── 9. match-resumed ──────────────────────────────
                        # Contains finishTime (updated) and message like
                        # "Match has resumed! It's team2's turn."
                        elif mtype == "match-resumed":
                            finish = data.get("finishTime")
                            if finish:
                                state.finish_time_ms = finish

                            resume_msg = data.get("message", "")
                            log.info("▶️   Match resumed: %s", resume_msg)

                            # Parse whose turn from the message text
                            extracted = _extract_team_from_text(resume_msg)
                            if extracted:
                                state.turn = extracted

                            if (
                                state.status == "started"
                                and state.is_my_turn
                                and state.topic
                                and state.stance
                            ):
                                await send_argument(ws, state)

                        # ── 10. match-finish ──────────────────────────────
                        elif mtype == "match-finish":
                            log.info("🏁  Match finished! %s", data.get("message", ""))
                            log.info("📈  My total turns taken: %d", state.my_turn_count)
                            return   # clean exit

                        # ── 11. debate-message ────────────────────────────
                        # Broadcast to all when ANY team's message is accepted.
                        # "from" field identifies the sender.
                        elif mtype == "debate-message":
                            content = data.get("message", "")
                            if frm == state.my_team:
                                log.info("💬  [US]  %s…", content[:120])
                                # Our own echo — already stored in send_argument()
                            else:
                                log.info("💬  [OPP] %s…", content[:120])
                                state.opponent_history.append(content)
                                # match-state will fire next with turn=our_team

                        # ── 12. previous-message ──────────────────────────
                        # Sent when joining an already-live match.
                        # data.conversations is a list of {team, message, timestamp}
                        elif mtype == "previous-message":
                            log.info("📜  Received conversation history (late join)")
                            convos = data.get("conversations", [])
                            for entry in convos:
                                team    = entry.get("team", "")
                                content = entry.get("message", "")
                                if team == state.my_team:
                                    if content not in state.my_history:
                                        state.my_history.append(content)
                                else:
                                    if content not in state.opponent_history:
                                        state.opponent_history.append(content)
                            log.info("   Loaded %d our turns, %d opponent turns",
                                     len(state.my_history), len(state.opponent_history))

                        # ── 13. sandbox-message ───────────────────────────
                        # Should not arrive in a live match but handle gracefully.
                        elif mtype == "sandbox-message":
                            log.debug("📦  Unexpected sandbox-message in live match: %s",
                                      data.get("message", ""))

                        else:
                            log.debug("❓  Unknown message type: %s | data=%s", mtype, data)

                    except json.JSONDecodeError as exc:
                        log.error("🔴  JSON parse error: %s | raw=%s", exc, raw[:200])
                    except Exception as exc:
                        log.error("🔴  Handler error: %s", exc, exc_info=True)

        except ConnectionClosed as exc:
            log.warning("🔌  WebSocket disconnected: %s", exc)
        except Exception as exc:
            log.error("💥  Connection error: %s", exc)

        # ---- Reconnection logic (rulebook §10: 2-minute window) ----------
        if reconnect_deadline is None:
            reconnect_deadline = time.time() + 120
            log.info("⏳  Will attempt reconnect for up to 2 minutes…")

        if time.time() > reconnect_deadline:
            log.error("❌  2-minute reconnect window expired. Exiting.")
            sys.exit(1)

        log.info("🔄  Reconnecting in 5 s…")
        await asyncio.sleep(5)


# ------------------------------------------------------------------ #
#  send_argument helper
# ------------------------------------------------------------------ #

async def send_argument(ws, state: DebateState):
    """Generate a debate argument via Groq and send it over WebSocket."""
    state.my_turn_count += 1
    turn_n = state.my_turn_count

    text = generate_argument(
        topic=state.topic,
        stance=state.stance,
        turn_number=turn_n,
        total_estimated_turns=state.estimated_turns_remaining() + turn_n,
        my_history=state.my_history,
        opponent_history=state.opponent_history,
        description=state.description,
    )

    state.my_history.append(text)
    payload = make_debate_message(text)
    await ws.send(payload)
    log.info("📤  Sent argument (turn %d, %d chars)", turn_n, len(text))


# ------------------------------------------------------------------ #
#  Utility
# ------------------------------------------------------------------ #

def _extract_team_from_text(message: str) -> str:
    """
    Parse team identifier from strings like:
      "Match has resumed! It's team2's turn."
      "The match has started! Let the slam begin! It's team1's turn."
    Returns "" if not found.
    """
    lower = message.lower()
    if "team1" in lower:
        return "team1"
    if "team2" in lower:
        return "team2"
    return ""


# ------------------------------------------------------------------ #
#  Entry point
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="AgentSlam 2026 Debate Bot — powered by Groq (FREE Llama 3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py --mode sandbox              # test connection
  python agent.py --mode match --team team1   # live match as team1
  python agent.py --mode match --team team2   # live match as team2
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["sandbox", "match"],
        required=True,
        help="'sandbox' for connection testing, 'match' for live debate",
    )
    parser.add_argument(
        "--team",
        default="",
        help="Your team ID as assigned (team1 or team2). "
             "REQUIRED for correct PRO/CON stance detection from match-state.",
    )
    args = parser.parse_args()

    # ── Validate Groq API key ─────────────────────────────────────────
    if "REPLACE" in config.GROQ_API_KEY or not config.GROQ_API_KEY.startswith("gsk_"):
        log.error("❌  Set your GROQ_API_KEY in config.py before running!")
        log.error("    Get a FREE key at: https://console.groq.com")
        sys.exit(1)

    # ── Team flag ─────────────────────────────────────────────────────
    if args.team:
        _TEAM_OVERRIDE[0] = args.team
    else:
        log.warning("⚠️   No --team flag! Stance detection may fail.")
        log.warning("    Recommended: python agent.py --mode match --team team1")

    # ── Run selected mode ─────────────────────────────────────────────
    if args.mode == "sandbox":
        url = config.SANDBOX_WS_URL
        if "SANDBOX_URL_HERE" in url:
            log.error("❌  Set SANDBOX_WS_URL in config.py first!")
            sys.exit(1)
        asyncio.run(run_sandbox(url))

    else:  # match
        url = config.MATCH_WS_URL
        if "MATCH_URL_HERE" in url:
            log.error("❌  Set MATCH_WS_URL in config.py first! "
                      "(Admin emails this when match goes active.)")
            sys.exit(1)
        asyncio.run(_run_match_loop(url))


if __name__ == "__main__":
    main()
