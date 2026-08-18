"""
Tests for the content generator module.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.content_generator import ContentGenerator, PROPERTY_FACTS


def test_generate_returns_variations():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    assert len(variations) == 6
    print("PASS: generate returns correct number of variations")


def test_all_variations_contain_price():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    for i, text in enumerate(variations):
        assert PROPERTY_FACTS["price"] in text, f"Variation {i} missing price"
    print("PASS: all variations contain correct price")


def test_all_variations_contain_phone():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    for i, text in enumerate(variations):
        assert PROPERTY_FACTS["contact_phone"] in text, f"Variation {i} missing phone"
    print("PASS: all variations contain correct phone")


def test_all_variations_contain_location():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    location_key = PROPERTY_FACTS["location"].split(",")[0].strip()
    for i, text in enumerate(variations):
        assert location_key.lower() in text.lower(), f"Variation {i} missing location"
    print("PASS: all variations contain correct location")


def test_validate_text_valid():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    for text in variations:
        errors = gen.validate_text(text)
        assert len(errors) == 0, f"Validation errors: {errors}"
    print("PASS: validate_text passes for all generated variations")


def test_validate_text_missing_price():
    gen = ContentGenerator()
    errors = gen.validate_text("This text has no price info")
    assert any("Price" in e for e in errors)
    print("PASS: validate_text catches missing price")


def test_variation_index_wraps():
    gen = ContentGenerator(num_variations=3)
    gen.generate()
    v0 = gen.get_variation(0)
    v3 = gen.get_variation(3)  # Should wrap to index 0
    assert v0 == v3
    print("PASS: get_variation wraps correctly")


def test_no_invented_facts():
    gen = ContentGenerator(num_variations=6)
    variations = gen.generate()
    # Check that wrong values do not appear
    for i, text in enumerate(variations):
        assert "3 \u043a\u0456\u043c\u043d\u0430\u0442\u0438" not in text, f"Variation {i} has wrong room count"
        assert "100 \u043c\u00b2" not in text, f"Variation {i} has wrong area"
        assert "$30 000" not in text, f"Variation {i} has wrong price"
    print("PASS: no invented facts in generated text")


if __name__ == "__main__":
    test_generate_returns_variations()
    test_all_variations_contain_price()
    test_all_variations_contain_phone()
    test_all_variations_contain_location()
    test_validate_text_valid()
    test_validate_text_missing_price()
    test_variation_index_wraps()
    test_no_invented_facts()
    print("\nAll content generator tests passed!")
