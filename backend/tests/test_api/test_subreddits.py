"""Tests for subreddit API validation."""

import pytest
from pydantic import ValidationError

from app.api.subreddits import SubredditCreate


class TestSubredditValidation:
    """Tests for subreddit name validation."""

    def test_valid_subreddit_names(self):
        valid_names = ["SaaS", "startups", "web_dev", "Python", "ab", "a_b_c_d_e_f_g_h_i_j_k"]
        for name in valid_names:
            s = SubredditCreate(name=name)
            assert s.name == name.lower().replace("r/", "")

    def test_strips_r_prefix(self):
        s = SubredditCreate(name="r/SaaS")
        assert s.name == "saas"

    def test_strips_whitespace(self):
        s = SubredditCreate(name="  SaaS  ")
        assert s.name == "saas"

    def test_rejects_too_short(self):
        with pytest.raises(ValidationError):
            SubredditCreate(name="a")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            SubredditCreate(name="a" * 22)

    def test_rejects_spaces(self):
        with pytest.raises(ValidationError):
            SubredditCreate(name="has spaces")

    def test_rejects_special_chars(self):
        with pytest.raises(ValidationError):
            SubredditCreate(name="test!")

    def test_rejects_hyphens(self):
        with pytest.raises(ValidationError):
            SubredditCreate(name="test-sub")

    def test_allows_underscores(self):
        s = SubredditCreate(name="web_dev")
        assert s.name == "web_dev"

    def test_allows_numbers(self):
        s = SubredditCreate(name="test123")
        assert s.name == "test123"
