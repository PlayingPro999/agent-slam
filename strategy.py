"""
strategy.py — Debate strategy and prompt construction for AgentSlam 2026.

The Oracle (Judging Bot) weights (rulebook §6):
  Persuasiveness  40%
  Logic           30%
  API Robustness  20%
  Agility         10%

Every argument this module builds is optimised for those four dimensions.
"""

# ------------------------------------------------------------------ #
#  SYSTEM PROMPT  (sent to Groq/Llama as the system role)
# ------------------------------------------------------------------ #

SYSTEM_PROMPT = """You are a world-class competitive debater competing in
AgentSlam 2026 — a live AI debate tournament. Your arguments are judged by
an autonomous Judging Bot called The Oracle on four weighted criteria:

  1. Persuasiveness (40%) — rhetoric, vivid evidence, compelling narrative
  2. Logic (30%)          — airtight reasoning, no fallacies, clear structure
  3. API Robustness (20%) — clean, concise, well-formatted output
  4. Agility (10%)        — direct, intelligent response to the opponent's last point

HARD RULES you must always obey:
• Keep your response STRICTLY under 3000 characters (count carefully).
• Write in plain prose — no bullet lists, no markdown headers.
• Never fabricate statistics, laws, or research papers.
  If you cite data, it must be real and verifiable; append a source URL inline
  like: "GDP grew 3.2% in 2023. (Source: https://data.worldbank.org/...)"
• Never use offensive, abusive, or toxic language.
• Do not repeat the same argument verbatim across turns.
• Structure matters:
    - Opening turn  → State your position clearly; introduce 2-3 strong pillars.
    - Middle turns  → Rebut the opponent's last point, then reinforce your pillar.
    - Final turn    → Deliver a closing argument: summarise your wins, expose
                      opponent's unresolved weaknesses, end with a punchy sentence.

Your tone should be confident, intellectually rigorous, and persuasive — like a
seasoned policy debater addressing a high-stakes panel.

Return ONLY the argument text, nothing else."""


# ------------------------------------------------------------------ #
#  PROMPT BUILDERS
# ------------------------------------------------------------------ #

def build_prompt(
    topic: str,
    stance: str,                   # "PRO" or "CON"
    turn_number: int,
    total_estimated_turns: int,
    my_history: list,
    opponent_history: list,
    description: str = "",
) -> str:
    """
    Constructs the user-turn prompt sent to Groq/Llama.

    Parameters
    ----------
    topic                  : The debate topic string.
    stance                 : "PRO" or "CON".
    turn_number            : 1-indexed turn counter for our side.
    total_estimated_turns  : Rough estimate of total turns (used to decide phase).
    my_history             : Our previous arguments (oldest first).
    opponent_history       : Opponent's previous arguments (oldest first).
    description            : Optional topic description from match-state.
    """

    # ---- Determine debate phase ----------------------------------------
    if turn_number == 1:
        phase = "OPENING"
    elif total_estimated_turns - turn_number <= 1:
        phase = "CLOSING"
    else:
        phase = "MIDDLE"

    # ---- Build context block -------------------------------------------
    context_lines = [
        f"DEBATE TOPIC: {topic}",
        f"TOPIC DESCRIPTION: {description}" if description else "",
        f"YOUR STANCE: {stance}",
        f"CURRENT PHASE: {phase} (turn {turn_number})",
        "",
    ]

    if opponent_history:
        context_lines.append("OPPONENT'S LAST ARGUMENT:")
        context_lines.append(opponent_history[-1])
        context_lines.append("")

    if my_history:
        context_lines.append("YOUR PREVIOUS ARGUMENTS (do NOT repeat these verbatim):")
        for i, arg in enumerate(my_history[-3:], 1):     # show last 3 max
            context_lines.append(
                f"[Turn {turn_number - len(my_history[-3:]) + i - 1}] {arg[:300]}…"
            )
        context_lines.append("")

    # ---- Phase-specific instruction ------------------------------------
    if phase == "OPENING":
        instruction = (
            "Deliver a powerful OPENING STATEMENT for your stance. "
            "Introduce your core position, outline your 2-3 main pillars, "
            "and set a confident, authoritative tone."
        )
    elif phase == "CLOSING":
        instruction = (
            "Deliver your CLOSING ARGUMENT. Summarise the strongest points you "
            "have made, highlight the key weaknesses in the opponent's case that "
            "remain unresolved, and end with a single memorable, punchy sentence "
            "that leaves The Oracle with no doubt about who won."
        )
    else:
        instruction = (
            "First, directly REBUT the opponent's last argument — identify its "
            "logical flaw or missing evidence. Then reinforce one of your own pillars "
            "with fresh reasoning or a concrete real-world example. "
            "Be agile and responsive."
        )

    context_lines.append(f"YOUR TASK: {instruction}")
    context_lines.append("")
    context_lines.append(
        "Remember: respond in plain prose, under 3000 characters, "
        "cite real sources inline if you use statistics."
    )

    return "\n".join(line for line in context_lines if line is not None)


def truncate_to_limit(text: str, limit: int = 3000) -> str:
    """Hard-truncate at the last sentence boundary before `limit` chars."""
    if len(text) <= limit:
        return text

    truncated = text[:limit - 10]
    # Try to cut at the last full sentence
    for sep in (". ", "! ", "? "):
        idx = truncated.rfind(sep)
        if idx != -1:
            return truncated[: idx + 1].strip()
    return truncated.strip()
