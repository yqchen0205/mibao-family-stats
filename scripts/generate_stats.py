#!/usr/bin/env python3
"""Mibao Family contribution stats generator."""

from __future__ import annotations

import json
import os
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests

DEFAULT_AUTHOR_EMAILS = ["Mibao0211@163.com", "1063037668@qq.com"]
DEFAULT_TIMEZONE = "Asia/Shanghai"
STATS_DIR = "stats"
STATS_JSON_PATH = os.path.join(STATS_DIR, "contributions.json")
STATS_SVG_PATH = os.path.join(STATS_DIR, "contributions.svg")
STATS_README_PATH = os.path.join(STATS_DIR, "README.md")
COMMIT_INDEX_PATH = os.path.join(STATS_DIR, "commit_index.json")


def stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_index_commit_map(commits_by_sha: Dict) -> Dict:
    normalized: Dict[str, Dict] = {}
    for key, entry in commits_by_sha.items():
        if not isinstance(entry, dict):
            continue
        commit_identity = entry.get("sha") or entry.get("commit_key") or key
        committed_date = entry.get("committed_date")
        if not commit_identity or not committed_date:
            continue
        repo_identity = entry.get("repo_key") or entry.get("repo", "")
        normalized[stable_digest(str(commit_identity))] = {
            "committed_date": committed_date,
            "repo_key": stable_digest(repo_identity) if repo_identity else "",
        }
    return normalized


def parse_author_emails(env: Dict[str, str]) -> List[str]:
    raw = env.get("AUTHOR_EMAILS", "")
    if not raw.strip():
        return list(DEFAULT_AUTHOR_EMAILS)

    emails: List[str] = []
    for token in raw.split(","):
        value = token.strip()
        if value and value not in emails:
            emails.append(value)

    return emails or list(DEFAULT_AUTHOR_EMAILS)


def parse_iso8601(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def format_utc_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit_timestamp_to_local_day(timestamp: str, timezone_name: str) -> str:
    commit_time_utc = parse_iso8601(timestamp)
    local_time = commit_time_utc.astimezone(ZoneInfo(timezone_name))
    return local_time.strftime("%Y-%m-%d")


def compute_incremental_since(
    last_successful_sync: Optional[str],
    now_utc: Optional[datetime] = None,
) -> str:
    now = now_utc or datetime.now(timezone.utc)

    if not last_successful_sync:
        return format_utc_z(now - timedelta(days=365))

    try:
        last = parse_iso8601(last_successful_sync)
    except ValueError:
        return format_utc_z(now - timedelta(days=365))

    since = last - timedelta(hours=2)
    if since > now:
        since = now - timedelta(hours=2)

    return format_utc_z(since)


def make_empty_index(timezone_name: str, tracked_emails: List[str]) -> Dict:
    return {
        "last_successful_sync": None,
        "timezone": timezone_name,
        "tracked_emails": list(tracked_emails),
        "commits_by_sha": {},
    }


def load_commit_index(path: str = COMMIT_INDEX_PATH) -> Optional[Dict]:
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    commits = data.get("commits_by_sha")
    if not isinstance(commits, dict):
        return None

    sanitized_commits = normalize_index_commit_map(commits)

    loaded = {
        "last_successful_sync": data.get("last_successful_sync"),
        "timezone": data.get("timezone", DEFAULT_TIMEZONE),
        "tracked_emails": data.get("tracked_emails", list(DEFAULT_AUTHOR_EMAILS)),
        "commits_by_sha": sanitized_commits,
    }

    if not isinstance(loaded["tracked_emails"], list):
        loaded["tracked_emails"] = list(DEFAULT_AUTHOR_EMAILS)

    return loaded


def save_commit_index(index: Dict, path: str = COMMIT_INDEX_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)


def github_get(url: str, token: str, params: Optional[Dict] = None) -> requests.Response:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    return requests.get(url, headers=headers, params=params, timeout=30)


def get_all_repos(token: str) -> List[Dict]:
    repos: List[Dict] = []

    for page in range(1, 21):
        response = github_get(
            "https://api.github.com/user/repos",
            token,
            params={
                "per_page": 100,
                "page": page,
                "affiliation": "owner,collaborator,organization_member",
                "sort": "updated",
                "direction": "desc",
            },
        )

        if response.status_code != 200:
            print(f"   ! Failed to list repos: HTTP {response.status_code}")
            break

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            break

        repos.extend(payload)

        if len(payload) < 100:
            break

    return repos


def get_repo_branches(owner: str, repo: str, token: str) -> List[str]:
    branches: List[str] = []

    for page in range(1, 21):
        response = github_get(
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            token,
            params={"per_page": 100, "page": page},
        )

        if response.status_code == 409:
            break

        if response.status_code != 200:
            print(f"   ! Failed to list branches for {owner}/{repo}: HTTP {response.status_code}")
            break

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            break

        for branch in payload:
            name = branch.get("name")
            if name and name not in branches:
                branches.append(name)

        if len(payload) < 100:
            break

    return branches


def normalize_commit(raw_commit: Dict, repo_full_name: str, branch: str, matched_email: str) -> Optional[Dict]:
    sha = raw_commit.get("sha")
    commit_block = raw_commit.get("commit", {})
    author_block = commit_block.get("author") or {}
    committer_block = commit_block.get("committer") or {}
    committed_date = author_block.get("date") or committer_block.get("date")

    if not sha or not committed_date:
        return None

    return {
        "sha": sha,
        "committed_date": committed_date,
        "repo": repo_full_name,
        "branch": branch,
        "author_email": author_block.get("email") or matched_email,
    }


def get_branch_commits(
    owner: str,
    repo: str,
    branch: str,
    author_email: str,
    since: str,
    token: str,
) -> List[Dict]:
    commits: List[Dict] = []

    for page in range(1, 21):
        response = github_get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            token,
            params={
                "author": author_email,
                "sha": branch,
                "since": since,
                "per_page": 100,
                "page": page,
            },
        )

        if response.status_code == 409:
            break

        if response.status_code != 200:
            print(
                f"   ! Failed commits {owner}/{repo}@{branch} for {author_email}: "
                f"HTTP {response.status_code}"
            )
            break

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            break

        commits.extend(payload)

        if len(payload) < 100:
            break

    return commits


def collect_commits(token: str, author_emails: List[str], since: str) -> Dict:
    repos = get_all_repos(token)

    commits: List[Dict] = []
    repos_with_new_commits = set()
    branches_scanned = 0

    print(f"   Repositories discovered: {len(repos)}")

    for repo in repos:
        owner = repo.get("owner", {}).get("login")
        repo_name = repo.get("name")
        if not owner or not repo_name:
            continue

        full_name = f"{owner}/{repo_name}"
        branches = get_repo_branches(owner, repo_name, token)

        if not branches:
            default_branch = repo.get("default_branch")
            if default_branch:
                branches = [default_branch]

        branches_scanned += len(branches)
        repo_total = 0

        for branch in branches:
            for email in author_emails:
                raw_commits = get_branch_commits(owner, repo_name, branch, email, since, token)
                for raw_commit in raw_commits:
                    normalized = normalize_commit(raw_commit, full_name, branch, email)
                    if normalized:
                        commits.append(normalized)
                        repo_total += 1

        privacy = "private" if repo.get("private") else "public"
        print(
            f"   Checked {full_name} ({privacy}) - branches: {len(branches)}, "
            f"new matches: {repo_total}"
        )

        if repo_total:
            repos_with_new_commits.add(full_name)

    return {
        "repos_scanned": len(repos),
        "repos_with_new_commits": len(repos_with_new_commits),
        "branches_scanned": branches_scanned,
        "commits": commits,
    }


def merge_commits_into_index(index: Dict, incoming_commits: Iterable[Dict]) -> Dict:
    commits_by_sha = normalize_index_commit_map(index.setdefault("commits_by_sha", {}))

    for commit in incoming_commits:
        sha = commit.get("sha") or commit.get("commit_key")
        committed_date = commit.get("committed_date")
        if not sha or not committed_date:
            continue

        commit_key = stable_digest(sha)
        if commit_key not in commits_by_sha:
            repo_identity = commit.get("repo_key") or commit.get("repo", "")
            commits_by_sha[commit_key] = {
                "committed_date": committed_date,
                "repo_key": stable_digest(repo_identity) if repo_identity else "",
            }

    index["commits_by_sha"] = commits_by_sha
    return index


def prune_index(index: Dict, now_utc: Optional[datetime] = None) -> Dict:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=365)

    commits_by_sha = index.get("commits_by_sha", {})
    pruned = {}

    for sha, commit in commits_by_sha.items():
        timestamp = commit.get("committed_date")
        if not timestamp:
            continue

        try:
            commit_dt = parse_iso8601(timestamp)
        except ValueError:
            continue

        if commit_dt >= cutoff:
            pruned[sha] = commit

    index["commits_by_sha"] = pruned
    return index


def calculate_streak(contributions_by_date: Dict[str, int], timezone_name: str) -> int:
    today = datetime.now(ZoneInfo(timezone_name)).date()
    streak = 0

    for offset in range(365):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        if contributions_by_date.get(day, 0) > 0:
            streak += 1
        elif offset > 0:
            break

    return streak


def calculate_max_streak(contributions_by_date: Dict[str, int]) -> int:
    non_zero_dates = sorted(
        day for day, value in contributions_by_date.items() if value and value > 0
    )

    max_streak = 0
    current_streak = 0
    prev_date = None

    for day in non_zero_dates:
        current_date = datetime.strptime(day, "%Y-%m-%d")
        if prev_date and (current_date - prev_date).days == 1:
            current_streak += 1
        else:
            current_streak = 1

        if current_streak > max_streak:
            max_streak = current_streak

        prev_date = current_date

    return max_streak


def build_stats_from_index(
    index: Dict,
    timezone_name: str,
    repos_scanned: int = 0,
    sync_mode: str = "incremental",
) -> Dict:
    contributions_by_date: Dict[str, int] = defaultdict(int)
    repos_with_commits = set()

    commits_by_sha = index.get("commits_by_sha", {})
    for commit in commits_by_sha.values():
        timestamp = commit.get("committed_date")
        if not timestamp:
            continue

        try:
            day = commit_timestamp_to_local_day(timestamp, timezone_name)
        except ValueError:
            continue

        contributions_by_date[day] += 1
        repo_key = commit.get("repo_key")
        if not repo_key and commit.get("repo"):
            repo_key = stable_digest(commit.get("repo", ""))
        if repo_key:
            repos_with_commits.add(repo_key)

    total_commits = len(commits_by_sha)

    return {
        "total_commits": total_commits,
        "repos_scanned": repos_scanned,
        "repos_with_commits": len(repos_with_commits),
        "current_streak": calculate_streak(contributions_by_date, timezone_name),
        "max_streak": calculate_max_streak(contributions_by_date),
        "contributions_by_date": dict(contributions_by_date),
        "tracked_emails": list(index.get("tracked_emails", [])),
        "timezone": timezone_name,
        "last_successful_sync": index.get("last_successful_sync"),
        "sync_mode": sync_mode,
    }


def generate_contribution_heatmap(
    contributions_by_date: Dict[str, int],
    title: str,
    timezone_name: str,
) -> str:
    weeks = []
    today = datetime.now(ZoneInfo(timezone_name))
    start_date = today - timedelta(days=364)
    start_date = start_date - timedelta(days=start_date.weekday())

    for week_idx in range(53):
        week_data = {"contributionDays": []}
        for day_idx in range(7):
            date = start_date + timedelta(days=week_idx * 7 + day_idx)
            date_str = date.strftime("%Y-%m-%d")

            count = contributions_by_date.get(date_str, 0)

            if count == 0:
                color = "#ebedf0"
            elif count <= 2:
                color = "#9be9a8"
            elif count <= 5:
                color = "#40c463"
            elif count <= 10:
                color = "#30a14e"
            else:
                color = "#216e39"

            week_data["contributionDays"].append(
                {
                    "date": date_str,
                    "contributionCount": count,
                    "color": color,
                }
            )
        weeks.append(week_data)

    svg_width = 828
    svg_height = 140
    cell_size = 10
    cell_gap = 2

    svg_parts = [
        f'<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">',
        (
            '<text x="10" y="20" font-family="-apple-system, BlinkMacSystemFont, '
            'Segoe UI, Helvetica, Arial, sans-serif" font-size="14" font-weight="600" '
            f'fill="#24292f">{title}</text>'
        ),
        '<g transform="translate(10, 35)">',
    ]

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_month = None
    for week_idx, week in enumerate(weeks):
        first_day = week["contributionDays"][0]
        date = datetime.strptime(first_day["date"], "%Y-%m-%d")
        month_abbr = months[date.month - 1]
        if month_abbr != current_month:
            x = week_idx * (cell_size + cell_gap)
            svg_parts.append(
                f'<text x="{x}" y="-6" font-family="-apple-system, BlinkMacSystemFont, '
                f'Segoe UI, Helvetica, Arial, sans-serif" font-size="9" fill="#767676">{month_abbr}</text>'
            )
            current_month = month_abbr

    weekdays = ["Mon", "Wed", "Fri"]
    for idx, day in enumerate(weekdays):
        y = (idx * 2 + 1) * (cell_size + cell_gap) + cell_size / 2
        svg_parts.append(
            f'<text x="-25" y="{y}" font-family="-apple-system, BlinkMacSystemFont, '
            f'Segoe UI, Helvetica, Arial, sans-serif" font-size="9" fill="#767676">{day}</text>'
        )

    for week_idx, week in enumerate(weeks):
        for day_idx, day in enumerate(week["contributionDays"]):
            count = day["contributionCount"]
            color = day["color"]
            x = week_idx * (cell_size + cell_gap)
            y = day_idx * (cell_size + cell_gap)
            tooltip = f"{day['date']}: {count} commits"
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
                f'fill="{color}" rx="2"><title>{tooltip}</title></rect>'
            )

    legend_y = 85
    legend_x = 10
    legend_colors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

    svg_parts.append(
        f'<text x="{legend_x}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, '
        'Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">Less</text>'
    )

    for idx, color in enumerate(legend_colors):
        x = legend_x + 35 + idx * 15
        svg_parts.append(
            f'<rect x="{x}" y="{legend_y}" width="{cell_size}" height="{cell_size}" '
            f'fill="{color}" rx="2"/>'
        )

    svg_parts.append(
        f'<text x="{legend_x + 115}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, '
        'Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">More</text>'
    )

    svg_parts.extend(["</g>", "</svg>"])
    return "\n".join(svg_parts)


def generate_markdown_report(stats: Dict) -> None:
    cache_token = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    fetched_at = stats.get("fetched_at")
    if isinstance(fetched_at, str) and fetched_at:
        try:
            cache_token = parse_iso8601(fetched_at).strftime("%Y%m%d%H%M%S")
        except ValueError:
            pass

    report = f"""# Mibao Family Contributions

> Last updated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
> Mode: Full commit scan across all accessible repos and branches
> Refresh: Hourly via GitHub Actions
> Date bucket timezone: {stats['timezone']} (UTC+8)
> Sync mode: {stats['sync_mode']}

**{stats['total_commits']} commits in the last year**

- Repositories scanned this run: {stats['repos_scanned']}
- Repositories with commits in 365-day window: {stats['repos_with_commits']}
- Tracked emails: {", ".join(stats['tracked_emails'])}

## Contribution Graph

![Contributions](./contributions.svg?ts={cache_token})

## Streak Stats

- **Current Streak**: {stats['current_streak']} days
- **Max Streak**: {stats['max_streak']} days

---

*Generated by Mibao Bot*
"""

    with open(STATS_README_PATH, "w", encoding="utf-8") as handle:
        handle.write(report)


def should_force_full_sync(index: Optional[Dict], timezone_name: str, tracked_emails: List[str]) -> bool:
    if not index:
        return True

    index_timezone = index.get("timezone")
    if index_timezone != timezone_name:
        return True

    existing_emails = index.get("tracked_emails")
    if sorted(existing_emails or []) != sorted(tracked_emails):
        return True

    return False


def main() -> int:
    print("Generating Mibao Family contribution stats...")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No GITHUB_TOKEN found.")
        return 1

    tracked_emails = parse_author_emails(os.environ)
    timezone_name = os.environ.get("STATS_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    now_utc = datetime.now(timezone.utc)

    print(f"Tracked emails: {tracked_emails}")
    print(f"Timezone: {timezone_name}")

    index = load_commit_index(COMMIT_INDEX_PATH)

    if should_force_full_sync(index, timezone_name, tracked_emails):
        sync_mode = "full_rebuild"
        index = make_empty_index(timezone_name, tracked_emails)
        since = format_utc_z(now_utc - timedelta(days=365))
    else:
        sync_mode = "incremental"
        since = compute_incremental_since(index.get("last_successful_sync"), now_utc=now_utc)

    print(f"Sync mode: {sync_mode}")
    print(f"Fetching commits since: {since}")

    collected = collect_commits(token, tracked_emails, since)

    index = merge_commits_into_index(index, collected["commits"])
    index = prune_index(index, now_utc=now_utc)
    index["timezone"] = timezone_name
    index["tracked_emails"] = tracked_emails
    index["last_successful_sync"] = now_utc.isoformat()

    save_commit_index(index, COMMIT_INDEX_PATH)

    stats = build_stats_from_index(
        index,
        timezone_name=timezone_name,
        repos_scanned=collected["repos_scanned"],
        sync_mode=sync_mode,
    )
    stats["fetched_at"] = now_utc.isoformat()
    stats["last_successful_sync"] = index["last_successful_sync"]
    stats["new_commits_fetched"] = len(collected["commits"])
    stats["branches_scanned"] = collected["branches_scanned"]

    os.makedirs(STATS_DIR, exist_ok=True)
    with open(STATS_JSON_PATH, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    svg_content = generate_contribution_heatmap(
        stats["contributions_by_date"],
        "Mibao Family Contributions",
        timezone_name=timezone_name,
    )
    with open(STATS_SVG_PATH, "w", encoding="utf-8") as handle:
        handle.write(svg_content)

    generate_markdown_report(stats)

    print("Done.")
    print(f"Total commits in window: {stats['total_commits']}")
    print(f"Repos scanned: {stats['repos_scanned']}")
    print(f"Branches scanned: {stats['branches_scanned']}")
    print(f"New commits fetched this run: {stats['new_commits_fetched']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
