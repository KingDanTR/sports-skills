"""Unit tests for the polymarket module (no network)."""

from sports_skills.polymarket._connector import _text_match, _text_match_market


class TestTextMatch:
    """Cross-venue callers (markets.compare_odds) build "<away> <home>"
    queries whose tokens are never contiguous in Polymarket titles."""

    def test_contiguous_match_still_works(self):
        event = {"title": "Baltimore Orioles vs. Tampa Bay Rays", "description": "", "slug": ""}
        assert _text_match("Tampa Bay Rays", event) is True

    def test_two_token_query_matches_non_contiguous_title(self):
        event = {"title": "Baltimore Orioles vs. Tampa Bay Rays", "description": "", "slug": ""}
        assert _text_match("Orioles Rays", event) is True

    def test_two_token_query_requires_all_tokens(self):
        event = {"title": "Baltimore Orioles vs. Tampa Bay Rays", "description": "", "slug": ""}
        assert _text_match("Orioles Yankees", event) is False

    def test_tokens_may_span_fields(self):
        event = {"title": "Orioles moneyline", "description": "", "slug": "mlb-bal-tb-rays"}
        assert _text_match("Orioles Rays", event) is True

    def test_single_token_stays_contiguous_only(self):
        event = {"title": "Baltimore Orioles vs. Tampa Bay Rays", "description": "", "slug": ""}
        assert _text_match("Cardinals", event) is False


class TestTextMatchMarket:
    def test_two_token_query_matches_market_question(self):
        market = {"question": "Will the Orioles beat the Rays?", "slug": "", "events": []}
        assert _text_match_market("Orioles Rays", market) is True

    def test_two_token_query_matches_parent_event_title(self):
        market = {
            "question": "Moneyline",
            "slug": "",
            "events": [{"title": "Baltimore Orioles vs. Tampa Bay Rays", "slug": ""}],
        }
        assert _text_match_market("Orioles Rays", market) is True

    def test_no_match_returns_false(self):
        market = {"question": "Moneyline", "slug": "", "events": [{"title": "Cubs vs. Cards", "slug": ""}]}
        assert _text_match_market("Orioles Rays", market) is False
