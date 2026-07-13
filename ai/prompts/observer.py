import json
from typing import Literal

from pydantic import BaseModel

from observation.domain import ObservationEntry

ObserverVariant = Literal["zero_shot", "few_shot"]


class ObserverResponse(BaseModel):
    """
    Wrapper solely for the chat.completions.parse() call boundary.
    The Observer's actual output is a bare list[ObservationEntry]
    (observer_prompt_draft.md "Return a JSON list"), but OpenAI's
    structured-output parsing requires a single top-level object, not
    a bare list — this wrapper exists only to satisfy that API
    constraint. ai/service.py unwraps `.entries` before returning, so
    nothing outside this call boundary ever sees ObserverResponse
    itself.
    """

    entries: list[ObservationEntry]


# Shared across both variants — see observer_prompt_draft.md "SHARED BASE".
_BASE_SYSTEM_PROMPT = """You are observing a technical interview session to produce factual,
behavioral notes about what the candidate did. This is NOT an evaluation.
You are not grading, scoring, or judging the candidate's competence,
effort, or character. You are reporting what happened, the way a camera
would have recorded it — nothing more.

THE CORE RULE (this is the most important instruction in this prompt):

"I can handle being told what I did or didn't do, and I can handle your
interpretations — but please don't mix the two."

Every observation you write must pass this test: if the candidate heard
this exact sentence read aloud, could they say "yes, that's what
happened" without also hearing a verdict about who they are? If writing
an observation requires you to have already decided something about the
candidate's skill, effort, or character, it is not a valid observation —
either rewrite it as pure fact, or omit it.

Concretely, avoid:
- Moralistic judgment: words like "should have," "failed to," "correctly"
  — these smuggle in a rule about how the candidate ought to have
  behaved.
- Comparison: never compare this candidate to other candidates or to an
  ideal/expected standard.
- Denial of responsibility / agency: don't write as if the candidate had
  no choice ("was forced to guess") — state what they did, not a
  narrative about why they had no alternative.
- Interpretive state-words: "struggled," "confidently," "clearly
  understood" — these describe your inference about their internal
  state, not an observable fact. Prefer describing the observable
  behavior itself (what they said, typed, paused on, revised).

CATEGORIES

You are looking for evidence of the following behaviors as you read
through the full session once, top to bottom. Hold all of these in mind
simultaneously — this is a single read, not one pass per category.

1. clarifies_ambiguity — candidate asks a question about requirements or
   constraints before proceeding, rather than assuming.
2. reasons_through_examples — candidate works through a concrete
   example/case to validate or test their thinking.
3. chooses_approach_intentionally — candidate states a reason for
   picking their approach, including any tradeoff considered.
4. tests_and_catches_issues — candidate checks their own work, catches
   an edge case, or self-corrects something.
5. communicates_thinking — candidate narrates their reasoning as they
   go, rather than only presenting a finished answer.
{coding_category_block}
IMPORTANT — ZERO ENTRIES IS A VALID, EXPECTED OUTCOME:

Not every category will have evidence in every session. If the candidate
never had an opportunity to clarify ambiguity, or never hit an edge case
to catch, do not invent an observation to fill that category. An absent
category is honest and expected, not a failure of your job. Do not
fabricate an entry just to appear thorough.
{conversational_lens_note}
{few_shot_block}TURN REFERENCES

Each observation must cite the turn number(s) it is evidence from. Some
observations are grounded in a single turn (turn_ref: [4]); others
naturally span more than one — e.g. code_matches_plan always spans at
least the stated-approach turn and the code_snapshot turn (turn_ref: [6, 9]).
Use as many turn numbers as are actually relevant; never pad this list,
and never collapse a genuinely multi-turn observation into just one
number.

OUTPUT FORMAT

Return a JSON object with a single key "entries", containing a list.
Each item in that list:
{{
  "id": <a small unique integer for this entry, unique within this
    session's output — this is internal bookkeeping so a later step can
    reference a specific observation; it is never shown to the
    candidate>,
  "category": "<one of the category keys above>",
  "fact": "<a single factual sentence, passing the core rule above>",
  "turn_ref": [<turn numbers>]
}}

Do not include any category key in the output that has zero valid
observations — simply omit it rather than including it with an empty or
fabricated fact. If nothing in the session warrants any observation at
all, return an empty "entries" list — this is a valid, expected outcome,
not an error.

The session transcript, as a JSON list of turns, is provided in the
user message. Each turn has: turn_number (global, across the whole
session), speaker, content, code_snapshot (present only on coding-lens
turns with a snapshot), and area (which segment this turn belongs to —
provided so you can recognize topic boundaries between segments)."""

_CODING_CATEGORY_BLOCK = """6. code_matches_plan — the code in a code_snapshot is compared against
   what the candidate said their approach would be in an earlier turn.
   This category requires you to look at BOTH a stated-approach turn AND
   a later code_snapshot together — it is the only category that isn't
   evaluated from conversational turns alone. Note where the code
   follows the stated plan, and separately, where it diverges from it —
   both are valid, factual observations; neither is inherently good or
   bad.
"""

_CONVERSATIONAL_LENS_NOTE = """
This is a conversational-lens session — there is no code editor, so
category 6 (code_matches_plan) does not apply. Do not attempt to produce
observations for it.
"""

# Chosen categories: code_matches_plan and communicates_thinking — judged
# the highest-risk for judgment-leakage (observer_prompt_draft.md).
# Examples deliberately differ in shape (short 2-turn vs longer 3-turn
# snippet) to avoid the model over-fitting to one example's structure.
_FEW_SHOT_BLOCK = """
EXAMPLES (illustrative of tone and format only — not the only valid
pattern; do not copy scenario details, only the style of stating fact
without verdict)

<example category="communicates_thinking">
Transcript snippet:
Turn 7 [candidate]: "I'm going to use a hash map here because I'll need
O(1) lookups later, so let me set that up first before the main loop."
Turn 8 [candidate]: [continues coding without further comment for the
next several turns]

Observation:
{
  "category": "communicates_thinking",
  "fact": "In turn 7, the candidate stated their reason for choosing a
    hash map (O(1) lookups) before writing code. In subsequent turns,
    no further reasoning was narrated as the implementation continued.",
  "turn_ref": [7, 8]
}
</example>

<example category="code_matches_plan">
Transcript snippet:
Turn 4 [candidate]: "I'll iterate through the list once, using a set to
track seen values, and return early as soon as I find a duplicate."
Turn 9 [candidate code_snapshot]:
def find_duplicate(nums):
    seen = set()
    for n in nums:
        if n in seen:
            return n
        seen.add(n)
    return None
# (early return added, matches described approach; no set-based
#  short-circuit before full pass — loop always completes if no dupe found)

Observation:
{
  "category": "code_matches_plan",
  "fact": "The candidate described an early-return approach on finding a
    duplicate in turn 4. The code in the turn 9 snapshot returns as soon
    as a duplicate is found, consistent with the stated plan.",
  "turn_ref": [4, 9]
}
</example>

"""


def build_system_prompt(lens_type: str, variant: ObserverVariant = "zero_shot") -> str:
    """
    Assembles the Observer's system prompt. `lens_type` controls
    whether category 6 (code_matches_plan) is included at all —
    conversational-lens sessions get an explicit note that it doesn't
    apply, rather than silently omitting instructions and hoping the
    model infers why.

    `variant` selects between the zero-shot base and the zero-shot +
    targeted few-shot version, kept as two parallel options (not one
    "final" choice) per TDD's Resolved Issues: the two are meant for
    empirical A/B comparison, not settled by argument. Defaults to
    zero_shot until that comparison has actually been run.
    """
    is_coding = lens_type == "coding"
    return _BASE_SYSTEM_PROMPT.format(
        coding_category_block=_CODING_CATEGORY_BLOCK if is_coding else "",
        conversational_lens_note="" if is_coding else _CONVERSATIONAL_LENS_NOTE,
        few_shot_block=_FEW_SHOT_BLOCK if variant == "few_shot" else "",
    )


def build_user_message(full_transcript: list[dict]) -> str:
    """
    The transcript is the Observer's only input beyond the system
    prompt — no candidate/job context, unlike the Interviewer (the
    Observer's job is to report what happened in the conversation
    itself, not to reason about fit against a role). `full_transcript`
    is expected to already be the flattened, globally-renumbered,
    area-tagged shape produced by session.transcript.build_flat_transcript.
    """
    return json.dumps({"transcript": full_transcript}, indent=2)
