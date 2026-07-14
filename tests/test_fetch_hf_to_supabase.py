from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts import fetch_hf_to_supabase as mod


def _response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error", response=resp
        )
    else:
        resp.raise_for_status.side_effect = None
    return resp


class TestFilterTopN:
    def test_keeps_only_target_categories_within_top_n(self):
        rows = [
            {"category": "overall", "rank": 1},
            {"category": "overall", "rank": 20},
            {"category": "overall", "rank": 21},
            {"category": "coding", "rank": 5},
            {"category": "some-other-category", "rank": 1},
        ]

        result = mod.filter_top_n(rows)

        assert result == [
            {"category": "overall", "rank": 1},
            {"category": "overall", "rank": 20},
            {"category": "coding", "rank": 5},
        ]

    def test_drops_rows_with_no_rank(self):
        rows = [{"category": "overall", "rank": None}]

        assert mod.filter_top_n(rows) == []


class TestGetWithRetry:
    def test_returns_response_on_first_success(self):
        ok_resp = _response(200, {"ok": True})
        with patch.object(mod.requests, "get", return_value=ok_resp) as get, \
                patch.object(mod.time, "sleep") as sleep:
            result = mod._get_with_retry("https://example.com", timeout=30)

        assert result is ok_resp
        get.assert_called_once_with("https://example.com", timeout=30)
        sleep.assert_not_called()

    def test_retries_after_transient_failure_then_succeeds(self):
        bad_resp = _response(400)
        ok_resp = _response(200, {"ok": True})
        with patch.object(mod.requests, "get", side_effect=[bad_resp, ok_resp]) as get, \
                patch.object(mod.time, "sleep") as sleep:
            result = mod._get_with_retry("https://example.com")

        assert result is ok_resp
        assert get.call_count == 2
        sleep.assert_called_once_with(mod.INITIAL_BACKOFF_SECONDS)

    def test_raises_after_exhausting_all_attempts(self):
        bad_resp = _response(400)
        with patch.object(mod.requests, "get", return_value=bad_resp) as get, \
                patch.object(mod.time, "sleep") as sleep:
            with pytest.raises(requests.exceptions.HTTPError):
                mod._get_with_retry("https://example.com")

        assert get.call_count == mod.MAX_ATTEMPTS
        assert sleep.call_count == mod.MAX_ATTEMPTS - 1


class TestFetchAllRows:
    def test_concatenates_rows_from_every_parquet_file(self):
        index_resp = _response(200, ["https://cdn.example/a.parquet", "https://cdn.example/b.parquet"])
        file_resp_a = MagicMock(content=b"a-bytes")
        file_resp_b = MagicMock(content=b"b-bytes")

        table_a = MagicMock()
        table_a.to_pylist.return_value = [{"model_name": "model-a"}]
        table_b = MagicMock()
        table_b.to_pylist.return_value = [{"model_name": "model-b"}]

        with patch.object(mod, "_get_with_retry", side_effect=[index_resp, file_resp_a, file_resp_b]), \
                patch.object(mod.pq, "read_table", side_effect=[table_a, table_b]):
            rows = mod.fetch_all_rows()

        assert rows == [{"model_name": "model-a"}, {"model_name": "model-b"}]


class TestDiagnoseFetchFailure:
    def test_flags_hf_platform_outage_when_datasets_server_5xxs(self):
        down_resp = _response(503)
        down_resp.raise_for_status.side_effect = None  # not checked, only status_code is read
        with patch.object(mod.requests, "get", return_value=down_resp):
            summary = mod._diagnose_fetch_failure(RuntimeError("boom"))

        assert "platform outage" in summary
        assert "boom" in summary

    def test_does_not_flag_outage_when_datasets_server_is_healthy(self):
        ok_resp = _response(200)
        with patch.object(mod.requests, "get", return_value=ok_resp):
            summary = mod._diagnose_fetch_failure(RuntimeError("boom"))

        assert "platform outage" not in summary
        assert "worth a closer look" in summary

    def test_treats_health_check_network_error_as_not_confirmed_outage(self):
        with patch.object(mod.requests, "get", side_effect=requests.exceptions.ConnectionError()):
            summary = mod._diagnose_fetch_failure(RuntimeError("boom"))

        assert "platform outage" not in summary


class TestWriteSummary:
    def test_appends_to_github_step_summary_when_set(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("existing content\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        mod._write_summary("new section\n")

        assert summary_file.read_text(encoding="utf-8") == "existing content\nnew section\n"

    def test_is_a_no_op_without_github_step_summary(self, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

        mod._write_summary("should not raise")  # just must not throw


class TestMain:
    def test_writes_summary_and_reraises_on_fetch_failure(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://unused")
        error = requests.exceptions.ConnectionError("network down")

        with patch.object(mod, "fetch_all_rows", side_effect=error), \
                patch.object(mod, "_diagnose_fetch_failure", return_value="## diagnosis\n") as diagnose, \
                patch.object(mod, "_write_summary") as write_summary, \
                patch.object(mod, "upsert") as upsert:
            with pytest.raises(requests.exceptions.ConnectionError):
                mod.main()

        diagnose.assert_called_once_with(error)
        write_summary.assert_called_once_with("## diagnosis\n")
        upsert.assert_not_called()
