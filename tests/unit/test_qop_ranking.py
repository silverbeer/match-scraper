"""Unit tests for QoPRanking and QoPSnapshot models."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.qop_ranking import QoPRanking, QoPSnapshot


@pytest.mark.unit
class TestQoPRanking:
    """Test cases for QoPRanking Pydantic model."""

    def test_valid_construction(self):
        ranking = QoPRanking(
            rank=1,
            team_name="New York City FC",
            matches_played=16,
            att_score=89.6,
            def_score=83.1,
            qop_score=87.6,
        )

        assert ranking.rank == 1
        assert ranking.team_name == "New York City FC"
        assert ranking.matches_played == 16
        assert ranking.att_score == 89.6
        assert ranking.def_score == 83.1
        assert ranking.qop_score == 87.6

    def test_rank_must_be_at_least_one(self):
        with pytest.raises(ValidationError):
            QoPRanking(
                rank=0,
                team_name="New York City FC",
                matches_played=16,
                att_score=89.6,
                def_score=83.1,
                qop_score=87.6,
            )

    def test_matches_played_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            QoPRanking(
                rank=1,
                team_name="New York City FC",
                matches_played=-1,
                att_score=89.6,
                def_score=83.1,
                qop_score=87.6,
            )

    def test_team_name_whitespace_is_stripped(self):
        ranking = QoPRanking(
            rank=1,
            team_name="  New York City FC  ",
            matches_played=16,
            att_score=89.6,
            def_score=83.1,
            qop_score=87.6,
        )

        assert ranking.team_name == "New York City FC"


@pytest.mark.unit
class TestQoPSnapshot:
    """Test cases for QoPSnapshot Pydantic model."""

    def _make_ranking(self, rank: int = 1) -> QoPRanking:
        return QoPRanking(
            rank=rank,
            team_name="New York City FC",
            matches_played=16,
            att_score=89.6,
            def_score=83.1,
            qop_score=87.6,
        )

    def test_valid_construction(self):
        snapshot = QoPSnapshot(
            detected_at=date(2026, 4, 14),
            division="Northeast",
            age_group="U14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
            rankings=[self._make_ranking()],
        )

        assert snapshot.detected_at == date(2026, 4, 14)
        assert snapshot.division == "Northeast"
        assert snapshot.age_group == "U14"
        assert len(snapshot.rankings) == 1

    def test_division_normalized_to_title_case(self):
        snapshot = QoPSnapshot(
            detected_at=date(2026, 4, 14),
            division="northeast",
            age_group="U14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        )

        assert snapshot.division == "Northeast"

    def test_age_group_normalized(self):
        snapshot = QoPSnapshot(
            detected_at=date(2026, 4, 14),
            division="Northeast",
            age_group="u14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        )

        assert snapshot.age_group == "U14"

    def test_rankings_default_to_empty_list(self):
        snapshot = QoPSnapshot(
            detected_at=date(2026, 4, 14),
            division="Northeast",
            age_group="U14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        )

        assert snapshot.rankings == []

    def test_json_serialization_round_trip(self):
        original = QoPSnapshot(
            detected_at=date(2026, 4, 14),
            division="Northeast",
            age_group="U14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
            rankings=[self._make_ranking(rank=1), self._make_ranking(rank=2)],
        )

        data = original.model_dump(mode="json")
        restored = QoPSnapshot.model_validate(data)

        assert restored == original
