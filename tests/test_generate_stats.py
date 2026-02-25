import unittest
from datetime import datetime, timedelta, timezone

from scripts import generate_stats


class GenerateStatsTests(unittest.TestCase):
    def test_default_author_emails_contains_two_expected_addresses(self):
        emails = generate_stats.parse_author_emails({})
        self.assertEqual(
            emails,
            ["Mibao0211@163.com", "1063037668@qq.com"],
        )

    def test_author_emails_can_be_overridden_by_env(self):
        env = {"AUTHOR_EMAILS": "a@example.com, b@example.com ,, c@example.com"}
        emails = generate_stats.parse_author_emails(env)
        self.assertEqual(emails, ["a@example.com", "b@example.com", "c@example.com"])

    def test_commit_date_uses_shanghai_timezone_day_bucket(self):
        # 2026-02-25T16:30:00Z == 2026-02-26 00:30:00+08:00
        day = generate_stats.commit_timestamp_to_local_day(
            "2026-02-25T16:30:00Z",
            "Asia/Shanghai",
        )
        self.assertEqual(day, "2026-02-26")

    def test_two_hour_overlap_window_for_incremental_sync(self):
        last_sync = "2026-02-25T10:00:00+00:00"
        since = generate_stats.compute_incremental_since(last_sync)
        self.assertEqual(since, "2026-02-25T08:00:00Z")

    def test_merge_new_commits_deduplicates_by_sha(self):
        index = {
            "last_successful_sync": "2026-02-25T10:00:00+00:00",
            "timezone": "Asia/Shanghai",
            "tracked_emails": ["a@example.com"],
            "commits_by_sha": {
                "sha-1": {
                    "sha": "sha-1",
                    "committed_date": "2026-02-20T12:00:00Z",
                    "repo": "foo/bar",
                    "branch": "main",
                    "author_email": "a@example.com",
                }
            },
        }
        incoming = [
            {
                "sha": "sha-1",
                "committed_date": "2026-02-20T12:00:00Z",
                "repo": "foo/bar",
                "branch": "dev",
                "author_email": "a@example.com",
            },
            {
                "sha": "sha-2",
                "committed_date": "2026-02-21T12:00:00Z",
                "repo": "foo/bar",
                "branch": "main",
                "author_email": "a@example.com",
            },
        ]

        merged = generate_stats.merge_commits_into_index(index, incoming)
        self.assertEqual(len(merged["commits_by_sha"]), 2)
        self.assertIn(generate_stats.stable_digest("sha-1"), merged["commits_by_sha"])
        self.assertIn(generate_stats.stable_digest("sha-2"), merged["commits_by_sha"])

    def test_prune_index_keeps_recent_365_days(self):
        now = datetime(2026, 2, 25, 0, 0, 0, tzinfo=timezone.utc)
        index = {
            "last_successful_sync": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "tracked_emails": ["a@example.com"],
            "commits_by_sha": {
                "new": {
                    "sha": "new",
                    "committed_date": (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "repo": "foo/bar",
                    "branch": "main",
                    "author_email": "a@example.com",
                },
                "old": {
                    "sha": "old",
                    "committed_date": (now - timedelta(days=366)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "repo": "foo/bar",
                    "branch": "main",
                    "author_email": "a@example.com",
                },
            },
        }

        pruned = generate_stats.prune_index(index, now_utc=now)
        self.assertEqual(sorted(pruned["commits_by_sha"].keys()), ["new"])

    def test_build_contributions_from_index_returns_combined_total(self):
        index = {
            "last_successful_sync": "2026-02-25T10:00:00+00:00",
            "timezone": "Asia/Shanghai",
            "tracked_emails": ["a@example.com", "b@example.com"],
            "commits_by_sha": {
                "sha-1": {
                    "sha": "sha-1",
                    "committed_date": "2026-02-24T16:30:00Z",  # 2026-02-25 CST
                    "repo": "foo/bar",
                    "branch": "main",
                    "author_email": "a@example.com",
                },
                "sha-2": {
                    "sha": "sha-2",
                    "committed_date": "2026-02-25T02:00:00Z",  # 2026-02-25 CST
                    "repo": "foo/bar",
                    "branch": "main",
                    "author_email": "b@example.com",
                },
            },
        }

        stats = generate_stats.build_stats_from_index(index, timezone_name="Asia/Shanghai")
        self.assertEqual(stats["total_commits"], 2)
        self.assertEqual(stats["contributions_by_date"].get("2026-02-25"), 2)


if __name__ == "__main__":
    unittest.main()
