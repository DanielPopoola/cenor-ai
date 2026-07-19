import json

SYSTEM_PROMPT = """You are organizing a GitHub profile's raw API data into a small,
structured summary. Most of the schema is intentionally narrow — your
only real judgment call is picking which repositories are worth
surfacing as "notable_repos."

WHAT YOU ARE NOT RESPONSIBLE FOR

account_age_years and top_languages are computed separately from the
raw data and will be overwritten regardless of what you output — do not
spend effort deriving these precisely; any placeholder value is fine
and will be discarded.

bio

Copy the profile's own bio field if present, unedited. Leave null if
the profile has no bio.

notable_repos — BE PERMISSIVE

The repos provided are already the candidate's ~10 most recently
updated repositories, pre-selected by GitHub's own API — you do not
need to filter this list down further or apply your own judgment about
which ones are "good enough." Include a repo as notable unless it is
genuinely empty of any signal (no name, no description, and no
language/topics at all). When in doubt, include it — this list feeds a
candidate-context summary, not a quality gate; a downstream step
(the completeness bar, interviewer context) is responsible for
weighting relevance, not this step.

For each notable repo, populate name, description, primary_language,
and topics from the corresponding input fields — note that the input's
field is called "language" (GitHub's own naming), which maps to the
output's "primary_language". Do not write your own description if the
repo has none; leave it null.

is_valid / reason

is_valid should be false only if the input itself is unusable — e.g.
the profile data is empty or missing required identifying fields
entirely. A profile with no bio, no repos, or minimal activity is still
valid; reflect that as empty/null fields, not as is_valid=false.

OUTPUT FORMAT

Return a single JSON object matching the GitHubStructured schema:
is_valid, reason, bio, account_age_years, top_languages, notable_repos.
Populate account_age_years and top_languages with any value (they are
discarded) — focus your effort on bio and notable_repos.
"""

# The only fields build_user_message actually needs from each raw repo.
# GitHub's repo objects carry 60+ fields (a dozen self-referential
# *_url links, a duplicated `owner` object, `permissions`, etc.) that
# the prompt never asks about — sending them wasted ~19.5K tokens
# against Groq's 8K TPM limit for a 10-repo profile and triggered a
# 413. Trimming here (not in github_fetch.py) keeps the raw-fetch
# contract intact for github_computation.py's separate consumers
# (compute_account_age_years/compute_top_languages), which still get
# the untouched raw dict.
_RELEVANT_REPO_FIELDS = ("name", "description", "language", "topics", "fork")

# Same idea for the profile object — GitHub's /users/{username} payload
# includes ~15 self-referential API URLs the prompt never reads.
_RELEVANT_PROFILE_FIELDS = ("login", "name", "bio", "company", "location")


def _trim_repo(repo: dict) -> dict:
    return {field: repo.get(field) for field in _RELEVANT_REPO_FIELDS}


def _trim_profile(profile: dict) -> dict:
    return {field: profile.get(field) for field in _RELEVANT_PROFILE_FIELDS}


def build_user_message(raw_profile_data: dict) -> str:
    """
    raw_profile_data is {"profile": {...}, "repos": [...]} — the exact
    shape returned by candidate_profile.github_fetch.fetch_github_raw_profile,
    straight from GitHub's REST API with no pre-processing upstream.
    Trimmed here to only the handful of fields the prompt actually asks
    about (see _RELEVANT_REPO_FIELDS/_RELEVANT_PROFILE_FIELDS) before
    being sent to the model — the untrimmed payload is what caused a
    413 (19.5K tokens for one 10-repo profile against an 8K TPM limit).
    """
    trimmed = {
        "profile": _trim_profile(raw_profile_data.get("profile", {})),
        "repos": [_trim_repo(r) for r in raw_profile_data.get("repos", [])],
    }
    return json.dumps(trimmed, indent=2)
