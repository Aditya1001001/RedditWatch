"""Tests for the analyzer service."""

import pytest
from app.services.analyzer import (
    AnalysisOutput,
    InsightData,
    validate_llm_output,
    VALID_INSIGHT_TYPES,
    VALID_CATEGORIES,
)


class TestLLMOutputValidation:
    """Tests for LLM JSON output validation."""

    def test_valid_output(self):
        raw = {
            "category": "pain_point",
            "insights": [
                {
                    "type": "pain_point",
                    "theme_key": "pricing_confusion",
                    "title": "Pricing issues",
                    "description": "Users confused by pricing",
                    "intensity_score": 75,
                }
            ],
        }
        result = validate_llm_output(raw)
        assert result.category == "pain_point"
        assert len(result.insights) == 1
        assert result.insights[0].type == "pain_point"
        assert result.insights[0].intensity_score == 75

    def test_invalid_category_defaults_to_general(self):
        raw = {"category": "not_a_real_category", "insights": []}
        result = validate_llm_output(raw)
        assert result.category == "general"

    def test_invalid_type_defaults_to_pain_point(self):
        raw = {
            "category": "general",
            "insights": [{"type": "invalid_type", "title": "Test"}],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].type == "pain_point"

    def test_intensity_clamped_to_0_100(self):
        raw = {
            "category": "general",
            "insights": [
                {"type": "pain_point", "intensity_score": 200},
                {"type": "pain_point", "intensity_score": -50},
            ],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].intensity_score == 100
        assert result.insights[1].intensity_score == 0

    def test_intensity_non_numeric_defaults_to_50(self):
        raw = {
            "category": "general",
            "insights": [{"type": "pain_point", "intensity_score": "high"}],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].intensity_score == 50

    def test_theme_key_normalized(self):
        raw = {
            "category": "general",
            "insights": [
                {"type": "pain_point", "theme_key": "My Bad Theme!"},
                {"type": "pain_point", "theme_key": "pricing-confusion"},
                {"type": "pain_point", "theme_key": "UPPER CASE"},
            ],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].theme_key == "my_bad_theme"
        assert result.insights[1].theme_key == "pricing_confusion"
        assert result.insights[2].theme_key == "upper_case"

    def test_empty_theme_key_defaults_to_unknown(self):
        raw = {
            "category": "general",
            "insights": [{"type": "pain_point", "theme_key": ""}],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].theme_key == "unknown"

    def test_max_5_insights_per_post(self):
        raw = {
            "category": "general",
            "insights": [
                {"type": "pain_point", "title": f"Insight {i}"}
                for i in range(10)
            ],
        }
        result = validate_llm_output(raw)
        assert len(result.insights) == 5

    def test_invalid_sentiment_set_to_none(self):
        raw = {
            "category": "general",
            "insights": [
                {"type": "product_mention", "sentiment": "extremely_positive"},
            ],
        }
        result = validate_llm_output(raw)
        assert result.insights[0].sentiment is None

    def test_valid_sentiments(self):
        for sentiment in ["positive", "negative", "neutral", "mixed"]:
            raw = {
                "category": "general",
                "insights": [
                    {"type": "product_mention", "sentiment": sentiment},
                ],
            }
            result = validate_llm_output(raw)
            assert result.insights[0].sentiment == sentiment

    def test_completely_invalid_output_returns_empty(self):
        result = validate_llm_output({"random_key": "random_value"})
        assert result.category == "general"
        assert result.insights == []

    def test_missing_fields_use_defaults(self):
        raw = {
            "category": "pain_point",
            "insights": [{"type": "pain_point"}],
        }
        result = validate_llm_output(raw)
        i = result.insights[0]
        assert i.theme_key == "unknown"
        assert i.title == ""
        assert i.intensity_score == 50
        assert i.quote is None


class TestInsightDataModel:
    """Tests for the InsightData Pydantic model."""

    def test_all_valid_types_accepted(self):
        for t in VALID_INSIGHT_TYPES:
            insight = InsightData(type=t)
            assert insight.type == t

    def test_all_valid_categories_accepted(self):
        for c in VALID_CATEGORIES:
            output = AnalysisOutput(category=c)
            assert output.category == c
