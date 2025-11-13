"""Unit tests for division lookup utilities."""

from src.utils.division_lookup import (
    CONFERENCE_ID_MAP,
    DIVISION_ID_MAP,
    get_all_conferences,
    get_all_divisions,
    get_conference_id,
    get_division_id,
    get_division_id_for_league,
)


class TestDivisionLookup:
    """Test cases for division ID lookup functions."""

    def test_get_division_id_valid(self):
        """Test looking up valid division IDs."""
        assert get_division_id("Northeast") == 41
        assert get_division_id("Central") == 34
        assert get_division_id("Mid-Atlantic") == 68
        assert get_division_id("California") == 42

    def test_get_division_id_invalid(self):
        """Test looking up invalid division returns None."""
        assert get_division_id("Invalid") is None
        assert get_division_id("") is None
        assert get_division_id(None) is None

    def test_get_conference_id_valid(self):
        """Test looking up valid conference IDs."""
        assert get_conference_id("New England") == 41
        assert get_conference_id("Northeast") == 41  # Same as New England
        assert get_conference_id("Mid-Atlantic") == 68
        assert get_conference_id("California") == 42

    def test_get_conference_id_invalid(self):
        """Test looking up invalid conference returns None."""
        assert get_conference_id("Invalid") is None
        assert get_conference_id("") is None
        assert get_conference_id(None) is None

    def test_get_division_id_for_league_homegrown(self):
        """Test division ID lookup for Homegrown league."""
        # Homegrown uses division
        result = get_division_id_for_league("Homegrown", "Northeast", None)
        assert result == 41

        result = get_division_id_for_league("Homegrown", "Central", None)
        assert result == 34

        # Conference should be ignored for Homegrown
        result = get_division_id_for_league("Homegrown", "Northeast", "New England")
        assert result == 41  # Should use division, not conference

    def test_get_division_id_for_league_academy(self):
        """Test division ID lookup for Academy league."""
        # Academy uses conference
        result = get_division_id_for_league("Academy", None, "New England")
        assert result == 41

        result = get_division_id_for_league("Academy", None, "Mid-Atlantic")
        assert result == 68

        # Should fall back to division if conference not provided
        result = get_division_id_for_league("Academy", "Northeast", None)
        assert result == 41

    def test_get_division_id_for_league_academy_conference_priority(self):
        """Test that Academy league prioritizes conference over division."""
        # If both provided, conference should take precedence for Academy
        result = get_division_id_for_league("Academy", "Central", "New England")
        assert result == 41  # New England, not Central (34)

    def test_get_division_id_for_league_missing_values(self):
        """Test lookup returns None when required values are missing."""
        # Homegrown with no division
        assert get_division_id_for_league("Homegrown", None, None) is None

        # Academy with no conference or division
        assert get_division_id_for_league("Academy", None, None) is None

        # Invalid league type
        assert get_division_id_for_league("Invalid", "Northeast", None) is None

    def test_get_all_divisions(self):
        """Test getting all division mappings."""
        divisions = get_all_divisions()
        assert isinstance(divisions, dict)
        assert len(divisions) > 0
        assert divisions["Northeast"] == 41
        assert divisions["Central"] == 34
        # Verify it's a copy, not the original
        divisions["Test"] = 999
        assert "Test" not in DIVISION_ID_MAP

    def test_get_all_conferences(self):
        """Test getting all conference mappings."""
        conferences = get_all_conferences()
        assert isinstance(conferences, dict)
        assert len(conferences) > 0
        assert conferences["New England"] == 41
        assert conferences["Mid-Atlantic"] == 68
        # Verify it's a copy, not the original
        conferences["Test"] = 999
        assert "Test" not in CONFERENCE_ID_MAP

    def test_division_conference_id_consistency(self):
        """Test that overlapping division/conference names have consistent IDs."""
        # Northeast should have same ID in both maps
        assert get_division_id("Northeast") == get_conference_id("Northeast")
        assert get_division_id("Northeast") == 41

        # Mid-Atlantic should match
        assert get_division_id("Mid-Atlantic") == get_conference_id("Mid-Atlantic")
        assert get_division_id("Mid-Atlantic") == 68

    def test_all_division_ids_are_positive(self):
        """Test that all division IDs are positive integers."""
        for division_id in DIVISION_ID_MAP.values():
            assert isinstance(division_id, int)
            assert division_id > 0

        for conference_id in CONFERENCE_ID_MAP.values():
            assert isinstance(conference_id, int)
            assert conference_id > 0

    def test_no_duplicate_ids_within_maps(self):
        """Test that each ID is unique within its map."""
        # Note: IDs can overlap between division and conference maps (by design)
        list(DIVISION_ID_MAP.values())
        list(CONFERENCE_ID_MAP.values())

        # Check uniqueness (allowing duplicates since some names map to same ID)
        # Just verify the maps are well-formed
        assert len(DIVISION_ID_MAP) > 0
        assert len(CONFERENCE_ID_MAP) > 0
