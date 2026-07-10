from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from scripts import build_data as mod


class TestFetchCategory:
    def test_shapes_rows_into_dicts_with_expected_types(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("gpt-x", "openai", 1, Decimal("1234.5"), 9876),
            ("claude-y", "anthropic", 2, Decimal("1200.0"), 5000),
        ]

        result = mod.fetch_category(cur, "overall")

        assert result == [
            {
                "model_name": "gpt-x",
                "organization": "openai",
                "rank": 1,
                "rating": 1234.5,
                "vote_count": 9876,
            },
            {
                "model_name": "claude-y",
                "organization": "anthropic",
                "rank": 2,
                "rating": 1200.0,
                "vote_count": 5000,
            },
        ]
        assert isinstance(result[0]["rating"], float)
        assert isinstance(result[0]["vote_count"], int)

    def test_queries_scoped_to_requested_category(self):
        cur = MagicMock()
        cur.fetchall.return_value = []

        mod.fetch_category(cur, "coding")

        args = cur.execute.call_args.args
        assert args[1] == ("coding", "coding")


class TestDiffRanks:
    def test_detects_moved_entered_and_dropped(self):
        previous = {"model-a": 2, "model-old": 1}
        current = {"model-a": 1, "model-new": 20}

        result = mod.diff_ranks(previous, current)

        assert result == {
            "moved": [{"model_name": "model-a", "from_rank": 2, "to_rank": 1}],
            "entered": [{"model_name": "model-new", "rank": 20}],
            "dropped": [{"model_name": "model-old", "last_rank": 1}],
        }

    def test_no_changes_when_ranks_identical(self):
        ranks = {"model-a": 1, "model-b": 2}

        result = mod.diff_ranks(ranks, dict(ranks))

        assert result == {"moved": [], "entered": [], "dropped": []}

    def test_moved_sorted_by_largest_delta_first(self):
        previous = {"model-a": 5, "model-b": 2}
        current = {"model-a": 4, "model-b": 10}

        result = mod.diff_ranks(previous, current)

        assert [m["model_name"] for m in result["moved"]] == ["model-b", "model-a"]


class TestBuildHeadline:
    EMPTY = {"moved": [], "entered": [], "dropped": []}

    def _diffs(self, **overrides):
        diffs = {cat: dict(self.EMPTY) for cat in mod.CATEGORIES}
        diffs.update(overrides)
        return diffs

    def test_new_number_one_via_move_wins(self):
        diffs = self._diffs(overall={
            "moved": [{"model_name": "model-a", "from_rank": 2, "to_rank": 1}],
            "entered": [], "dropped": [],
        })

        assert mod.build_headline(diffs) == "model-a이 Overall 부문 2위→1위로 올라섰습니다"

    def test_new_number_one_via_entry_wins(self):
        diffs = self._diffs(coding={
            "moved": [], "entered": [{"model_name": "model-new", "rank": 1}], "dropped": [],
        })

        assert mod.build_headline(diffs) == "model-new이 Coding 부문 1위로 새로 진입했습니다"

    def test_falls_back_to_biggest_move_when_no_new_number_one(self):
        diffs = self._diffs(math={
            "moved": [{"model_name": "model-a", "from_rank": 10, "to_rank": 3}],
            "entered": [], "dropped": [],
        })

        assert mod.build_headline(diffs) == "model-a이 Math 부문 10위→3위로 올라섰습니다"

    def test_falls_back_to_best_new_entry_when_no_moves(self):
        diffs = self._diffs(overall={
            "moved": [], "entered": [{"model_name": "model-new", "rank": 15}], "dropped": [],
        })

        assert mod.build_headline(diffs) == "model-new이 Overall 부문 15위로 새로 진입했습니다"

    def test_none_when_nothing_changed(self):
        diffs = self._diffs()

        assert mod.build_headline(diffs) is None


class TestBuildChangelog:
    def test_returns_none_when_no_category_has_a_previous_snapshot(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [(date(2026, 7, 2),)],  # overall: only 1 date
            [],                      # coding: no snapshots yet
            [(date(2026, 7, 2),)],  # math: only 1 date
        ]

        assert mod.build_changelog(cur) is None

    def test_diffs_only_categories_with_history_and_picks_widest_date_range(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [(date(2026, 7, 2),), (date(2026, 6, 30),)],  # overall: 2 dates
            [("model-a", 2), ("model-old", 1)],            # overall previous ranks
            [("model-a", 1), ("model-new", 20)],           # overall current ranks
            [(date(2026, 7, 2),)],                          # coding: only 1 date
            [],                                             # math: no snapshots yet
        ]

        result = mod.build_changelog(cur)

        assert result["previous_snapshot_date"] == "2026-06-30"
        assert result["current_snapshot_date"] == "2026-07-02"
        assert result["headline"] == "model-a이 Overall 부문 2위→1위로 올라섰습니다"
        assert result["overall"] == {
            "moved": [{"model_name": "model-a", "from_rank": 2, "to_rank": 1}],
            "entered": [{"model_name": "model-new", "rank": 20}],
            "dropped": [{"model_name": "model-old", "last_rank": 1}],
        }
        assert result["coding"] == {"moved": [], "entered": [], "dropped": []}
        assert result["math"] == {"moved": [], "entered": [], "dropped": []}
