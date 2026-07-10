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
