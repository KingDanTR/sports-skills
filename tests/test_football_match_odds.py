"""get_match_odds: bookmaker odds for upcoming fixtures from football-data.co.uk.

The provider's fixtures file is rolling and can be stale for days between rounds,
so most of these guard the contract that the command never presents old prices
as current and never blames a club's name for what is really an empty file.
"""

import pytest

from sports_skills.football import _connector as c

HEAD = (
    "Div,Date,Time,HomeTeam,AwayTeam,"
    "B365H,B365D,B365A,PSH,PSD,PSA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,"
    "B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5\r\n"
)


def _row(div, date, time, home, away, avg=("2.00", "3.50", "3.80"), **over):
    cells = {
        "B365H": "",
        "B365D": "",
        "B365A": "",
        "PSH": "",
        "PSD": "",
        "PSA": "",
        "MaxH": "",
        "MaxD": "",
        "MaxA": "",
        "AvgH": avg[0],
        "AvgD": avg[1],
        "AvgA": avg[2],
        "B365>2.5": "",
        "B365<2.5": "",
        "P>2.5": "",
        "P<2.5": "",
        "Max>2.5": "",
        "Max<2.5": "",
        "Avg>2.5": "1.80",
        "Avg<2.5": "2.05",
    }
    cells.update(over)
    return ",".join([div, date, time, home, away, *cells.values()]) + "\r\n"


TODAY = "2026-10-23"
CSV = HEAD + "".join(
    [
        _row("D1", "24/10/2026", "17:30", "Dortmund", "Ein Frankfurt", ("1.45", "4.94", "5.66")),
        _row("D1", "23/10/2026", "19:30", "Stuttgart", "M'gladbach", ("1.34", "5.71", "7.02")),
        _row("D1", "16/10/2026", "19:30", "Ein Frankfurt", "FC Koln"),  # last round
        _row("E0", "24/10/2026", "15:00", "Arsenal", "Chelsea"),  # other division
        _row(
            "D1", "25/10/2026", "14:30", "Freiburg", "Bayern Munich", ("", "", ""), **{"Avg>2.5": "", "Avg<2.5": ""}
        ),  # no prices at all
    ]
)


class TestFairProbabilities:
    def test_sum_to_one_and_report_the_margin(self):
        fair, overround = c._fair_probabilities([2.0, 3.5, 3.8])
        assert sum(fair) == pytest.approx(1.0)
        assert overround > 1.0
        assert fair[0] > fair[1] > fair[2]


class TestDecimalCells:
    @pytest.mark.parametrize("cell", ["", "abc", "1.0", "0.5", None])
    def test_non_prices_are_rejected(self, cell):
        assert c._fduk_decimal(cell) is None

    def test_real_price_parses(self):
        assert c._fduk_decimal(" 1.45 ") == 1.45


class TestKickoffUtc:
    def test_summer_time_is_one_hour_behind_utc(self):
        assert c._fduk_kickoff_utc("2026-10-23", "19:30") == "2026-10-23T18:30Z"

    def test_winter_time_equals_utc(self):
        # Clocks go back on 2026-10-25; a 14:30 UK kickoff that day is 14:30 UTC.
        assert c._fduk_kickoff_utc("2026-10-25", "14:30") == "2026-10-25T14:30Z"

    @pytest.mark.parametrize("time_text", ["", "TBC", "7pm"])
    def test_unparseable_time_is_omitted_not_guessed(self, time_text):
        assert c._fduk_kickoff_utc("2026-10-25", time_text) is None


class TestFixturesFromCsv:
    def test_keeps_only_this_division(self):
        fixtures, _ = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)
        assert {f["home_team"]["name"] for f in fixtures} == {"Dortmund", "Stuttgart"}

    def test_past_rows_are_dropped_and_counted(self):
        fixtures, stale = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)
        assert stale == 1
        assert all(f["date"] >= TODAY for f in fixtures)

    def test_rows_without_any_price_are_skipped(self):
        fixtures, _ = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)
        assert "Freiburg" not in {f["home_team"]["name"] for f in fixtures}

    def test_sorted_by_kickoff(self):
        fixtures, _ = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)
        assert [f["home_team"]["name"] for f in fixtures] == ["Stuttgart", "Dortmund"]

    def test_implied_probabilities_remove_the_margin(self):
        fixtures, _ = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)
        implied = fixtures[1]["implied_probabilities"]
        assert implied["basis"] == "average"
        assert implied["home"] + implied["draw"] + implied["away"] == pytest.approx(1.0, abs=1e-3)
        assert implied["overround"] > 1.0
        totals = fixtures[1]["implied_total_goals_2_5"]
        assert totals["over"] + totals["under"] == pytest.approx(1.0, abs=1e-3)

    def test_falls_back_to_a_named_book_when_the_average_is_missing(self):
        text = HEAD + _row(
            "D1",
            "24/10/2026",
            "15:30",
            "Mainz",
            "Werder Bremen",
            ("", "", ""),
            B365H="1.70",
            B365D="4.00",
            B365A="4.50",
        )
        fixtures, _ = c._fduk_fixtures_from_csv(text, "D1", TODAY)
        assert fixtures[0]["implied_probabilities"]["basis"] == "bet365"

    def test_maximum_prices_are_reported_but_never_a_basis(self):
        # The best price across books is not one book's market: de-vigging it
        # can produce an overround below 1 and meaningless probabilities.
        text = HEAD + _row(
            "D1", "24/10/2026", "15:30", "Mainz", "Werder Bremen", ("", "", ""), MaxH="1.90", MaxD="4.20", MaxA="4.80"
        )
        fixture = c._fduk_fixtures_from_csv(text, "D1", TODAY)[0][0]
        assert "maximum" in fixture["odds"]["match_result"]
        assert "implied_probabilities" not in fixture

    def test_carries_utc_kickoff_alongside_the_published_uk_time(self):
        fixture = c._fduk_fixtures_from_csv(CSV, "D1", TODAY)[0][0]
        assert (fixture["time"], fixture["time_zone"]) == ("19:30", "Europe/London")
        assert fixture["kickoff_utc"] == "2026-10-23T18:30Z"

    def test_empty_text_is_empty_not_an_error(self):
        assert c._fduk_fixtures_from_csv("", "D1", TODAY) == ([], 0)


@pytest.fixture
def offline(monkeypatch):
    """Patch every network edge; tests set the fixtures text per case."""
    c._cache.clear()
    state = {"fixtures": CSV, "season": ""}
    monkeypatch.setattr(c, "_fduk_fetch_fixtures", lambda: state["fixtures"])
    monkeypatch.setattr(c, "_fduk_fetch_season", lambda div, code, cur: state["season"])
    names = {"124": "Borussia Dortmund", "125": "Eintracht Frankfurt", "132": "Bayern Munich"}
    monkeypatch.setattr(c, "_resolve_team_id", lambda tid, params=None: tid)
    monkeypatch.setattr(
        c,
        "_resolve_espn_team_meta",
        lambda tid, hint=None: {"name": names[tid], "slug": "bundesliga"} if tid in names else None,
    )

    class _Today:
        @staticmethod
        def now(tz=None):
            from datetime import datetime as real

            return real(2026, 10, 23, 12, 0, tzinfo=tz)

        strptime = staticmethod(__import__("datetime").datetime.strptime)

    monkeypatch.setattr(c, "datetime", _Today)
    return state


def _call(**params):
    return c.get_match_odds({"params": params})


class TestGetMatchOdds:
    def test_needs_a_competition_or_a_team(self, offline):
        out = _call()
        assert out["error"] is True

    def test_unknown_competition_is_an_error(self, offline):
        out = _call(competition_id="not-a-league")
        assert out["error"] is True
        assert "get_competitions" in out["message"]

    def test_uncovered_league_says_so(self, offline):
        out = _call(competition_id="mls")
        assert out["fixtures"] == []
        assert "No free bookmaker odds" in out["message"]

    def test_league_returns_upcoming_fixtures_with_the_caveat(self, offline):
        out = _call(competition_id="bundesliga")
        assert len(out["fixtures"]) == 2
        assert out["stale_rows_dropped"] == 1
        assert out["source"] == "football-data.co.uk"
        assert "never places bets" in out["note"]

    def test_unreachable_file_is_reported(self, offline):
        offline["fixtures"] = ""
        out = _call(competition_id="bundesliga")
        assert "could not be fetched" in out["message"]

    def test_stale_file_never_passes_old_prices_as_current(self, offline):
        offline["fixtures"] = HEAD + _row("D1", "16/10/2026", "19:30", "Ein Frankfurt", "FC Koln")
        out = _call(competition_id="bundesliga")
        assert out["fixtures"] == []
        assert "only past Bundesliga matches" in out["message"]

    def test_team_filter_resolves_the_provider_label(self, offline):
        out = _call(team_id="125")
        assert out["teams"][0]["matched_as"] == "Ein Frankfurt"
        assert [f["away_team"]["name"] for f in out["fixtures"]] == ["Ein Frankfurt"]

    def test_two_teams_narrow_to_their_fixture(self, offline):
        out = _call(team_id="124", team_id_2="125")
        assert len(out["fixtures"]) == 1

    def test_two_teams_that_do_not_meet_this_round(self, offline):
        offline["season"] = HEAD + _row("D1", "16/10/2026", "19:30", "Bayern Munich", "Ein Frankfurt")
        out = _call(team_id="132", team_id_2="125")
        assert out["fixtures"] == []
        assert out["teams"][0]["reason"] == "no_upcoming_fixture"

    def test_club_known_this_season_but_absent_is_not_a_name_gap(self, offline):
        offline["season"] = HEAD + _row("D1", "16/10/2026", "19:30", "Bayern Munich", "Ein Frankfurt")
        out = _call(team_id="132")
        assert out["teams"][0]["reason"] == "no_upcoming_fixture"
        assert "name-resolution" not in out["message"]

    def test_unmatched_club_is_reported_as_a_name_gap(self, offline):
        offline["season"] = HEAD + _row("D1", "16/10/2026", "19:30", "Dortmund", "Ein Frankfurt")
        out = _call(team_id="132")
        assert out["teams"][0]["reason"] == "not_found"
        assert "name-resolution gap" in out["message"]

    def test_unverifiable_absence_claims_neither(self, offline):
        offline["season"] = ""  # season file unreachable too
        out = _call(team_id="132")
        assert out["teams"][0]["reason"] == "not_in_fixtures_file"
        assert "name-resolution" not in out["message"]
