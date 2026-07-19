import json

from ai.prompts.github_structurer import SYSTEM_PROMPT, build_user_message


def test_build_user_message_serializes_profile_and_repos():
    raw = {"profile": {"login": "adalovelace", "bio": "mathematician"}, "repos": [{"name": "engine"}]}
    msg = build_user_message(raw)
    payload = json.loads(msg)
    assert payload["profile"]["login"] == "adalovelace"
    assert payload["repos"][0]["name"] == "engine"


def test_build_user_message_strips_unused_repo_fields():
    """Regression test: GitHub's raw repo objects carry 60+ fields
    (a dozen self-referential *_url links, a duplicated owner object,
    permissions, etc.) that the prompt never reads. Sending them
    untrimmed pushed a real 10-repo profile to ~19.5K tokens against
    an 8K TPM provider limit and triggered a 413 — this must not
    regress."""
    raw = {
        "profile": {"login": "adalovelace"},
        "repos": [
            {
                "name": "engine",
                "description": "an analytical engine",
                "language": "Python",
                "topics": ["math"],
                "fork": False,
                "owner": {"login": "adalovelace", "id": 1, "url": "https://api.github.com/..."},
                "stargazers_url": "https://api.github.com/repos/adalovelace/engine/stargazers",
                "permissions": {"admin": True, "push": True, "pull": True},
                "html_url": "https://github.com/adalovelace/engine",
                "git_url": "git://github.com/adalovelace/engine.git",
            }
        ],
    }
    msg = build_user_message(raw)
    payload = json.loads(msg)

    repo = payload["repos"][0]
    assert set(repo.keys()) == {"name", "description", "language", "topics", "fork"}
    assert "owner" not in repo
    assert "permissions" not in repo
    assert "stargazers_url" not in repo


def test_build_user_message_strips_unused_profile_fields():
    raw = {
        "profile": {
            "login": "adalovelace",
            "name": "Ada Lovelace",
            "bio": "mathematician",
            "company": None,
            "location": "London",
            "followers_url": "https://api.github.com/users/adalovelace/followers",
            "gravatar_id": "",
            "node_id": "U_123",
        },
        "repos": [],
    }
    msg = build_user_message(raw)
    payload = json.loads(msg)

    assert set(payload["profile"].keys()) == {"login", "name", "bio", "company", "location"}
    assert "followers_url" not in payload["profile"]
    assert "node_id" not in payload["profile"]


def test_build_user_message_handles_missing_fields_gracefully():
    """Real GitHub payloads sometimes omit a field entirely rather
    than sending null (e.g. no bio) — trimming must not KeyError."""
    raw = {"profile": {"login": "adalovelace"}, "repos": [{"name": "engine"}]}
    msg = build_user_message(raw)
    payload = json.loads(msg)
    assert payload["profile"]["bio"] is None
    assert payload["repos"][0]["description"] is None


def test_system_prompt_tells_model_computed_fields_are_discarded():
    assert "account_age_years" in SYSTEM_PROMPT
    assert "top_languages" in SYSTEM_PROMPT
    assert "overwritten" in SYSTEM_PROMPT or "discarded" in SYSTEM_PROMPT


def test_system_prompt_is_permissive_about_notable_repos():
    """Per the design decision: don't apply an additional quality
    filter beyond what GitHub's sort=updated already provided."""
    assert "permissive" in SYSTEM_PROMPT.lower() or "BE PERMISSIVE" in SYSTEM_PROMPT
    assert "When in doubt, include it" in SYSTEM_PROMPT


def test_system_prompt_clarifies_language_field_name_mapping():
    """The trimmed input uses GitHub's own field name 'language', but
    the output schema calls it 'primary_language' — the prompt must
    say so explicitly or the model may look for the wrong input key."""
    assert '"language"' in SYSTEM_PROMPT
    assert "primary_language" in SYSTEM_PROMPT


def test_system_prompt_reserves_is_valid_false_for_unusable_input():
    assert "is_valid should be false only if" in SYSTEM_PROMPT
    assert "still" in SYSTEM_PROMPT and "valid" in SYSTEM_PROMPT
