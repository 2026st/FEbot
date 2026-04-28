"""Test script for content filter functionality."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from febot.config import Settings
from febot.content_filter import ContentFilter


def test_filter():
    """Test content filter with sample questions."""
    # Load settings
    settings = Settings.load(require_slack=False)

    if not settings.ai_api_key:
        print("[ERROR] AI_API_KEY is not set. Please set it in .env file.")
        return

    # Create filter instance
    content_filter = ContentFilter(settings)

    # Test cases
    test_cases = [
        # Should be OK (IT/Programming related)
        ("基本情報技術者試験の勉強方法を教えて", True),
        ("Pythonのリスト内包表記について教えて", True),
        ("データベースの正規化とは何ですか?", True),
        ("アルゴリズムの計算量について説明して", True),
        ("JavaScriptの非同期処理について", True),
        ("ネットワークのOSI参照モデルを説明して", True),
        # Should be NG (Not related to IT/Programming)
        ("今日の天気は?", False),
        ("おすすめのラーメン屋を教えて", False),
        ("東京の観光スポットは?", False),
        ("今日のランチは何がいい?", False),
        ("好きな映画は何ですか?", False),
    ]

    print(f"Content Filter Test (Filter Enabled: {settings.content_filter_enabled})")
    print("=" * 80)

    passed = 0
    failed = 0

    for question, expected_valid in test_cases:
        result = content_filter.validate(question)
        status = "[PASS]" if result.is_valid == expected_valid else "[FAIL]"

        if result.is_valid == expected_valid:
            passed += 1
        else:
            failed += 1

        print(f"\n{status}")
        print(f"Question: {question}")
        print(f"Expected: {'OK' if expected_valid else 'NG'}")
        print(f"Got:      {'OK' if result.is_valid else 'NG'}")
        if result.reason:
            print(f"Reason:   {result.reason}")

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")

    if failed == 0:
        print("All tests passed!")
    else:
        print(f"{failed} test(s) failed. Please review the filter logic.")


if __name__ == "__main__":
    test_filter()
