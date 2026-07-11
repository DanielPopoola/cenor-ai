import httpx

from candidate_profile.errors import GitHubFetchError
from config import Settings

_GITHUB_API_BASE = "https://api.github.com"
_REPOS_PER_PAGE = 10


async def fetch_github_raw_profile(username: str, settings: Settings) -> dict:
    """Returns {"profile": {...}, "repos": [...]}. Repos are the top 10
    by recent push activity, forks flagged (not silently dropped —
    structuring may still want to know a fork exists, just deprioritized
    by GitHub's own sort=updated ordering)."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_api_token:
        headers["Authorization"] = f"Bearer {settings.github_api_token}"

    async with httpx.AsyncClient(
        timeout=settings.llm_request_timeout_seconds, headers=headers
    ) as client:
        profile_resp = await client.get(f"{_GITHUB_API_BASE}/users/{username}")
        if profile_resp.status_code == 404:
            raise GitHubFetchError(f"No GitHub user found for username '{username}'")
        if profile_resp.status_code != 200:
            raise GitHubFetchError(
                f"GitHub profile fetch failed: {profile_resp.status_code}"
            )

        repos_resp = await client.get(
            f"{_GITHUB_API_BASE}/users/{username}/repos",
            params={"sort": "updated", "per_page": _REPOS_PER_PAGE},
        )
        if repos_resp.status_code != 200:
            raise GitHubFetchError(
                f"GitHub repos fetch failed: {repos_resp.status_code}"
            )

    return {"profile": profile_resp.json(), "repos": repos_resp.json()}
