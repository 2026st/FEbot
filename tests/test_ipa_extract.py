"""Tests for IPA PDF text extraction parsers."""

from febot.ipa_extract import (
    extracted_to_qid,
    needs_visual_body,
    parse_ipa_answers,
    parse_ipa_kamoku_a,
    parse_ipa_kamoku_b,
)

_KAMOKU_A_QS = """
問1 デッドロックの発生条件として不適切なものはどれか。
ア 相互排除 イ 占有と待ち ウ プリエンプション エ 循環待ち

問2 TCPの説明として適切なものはどれか。
ア UDPは常に遅い イ TCPは信頼性を高める ウ UDPは順序保証 エ 暗号化
"""

_KAMOKU_A_ANS = """
問1 ウ
問2 イ
"""

_KAMOKU_B_QS = """
問1 次の擬似コードの出力はどれか。
ア 1 イ 2 ウ 3 エ 4

問2 表計算に関する問題。セルの値はどれか。
ア 2 イ 5 ウ 9 エ 14 オ 20 カ 30 キ 40 ク 50
"""

_KAMOKU_B_ANS = """
問1 イ
問2 ク
"""


def test_parse_ipa_answers_multichoice() -> None:
    ans = parse_ipa_answers("問1 ア\n問2 ク\n問3 エ")
    assert ans == {1: "ア", 2: "ク", 3: "エ"}


def test_parse_ipa_kamoku_a() -> None:
    items = parse_ipa_kamoku_a(_KAMOKU_A_QS, _KAMOKU_A_ANS, "2023r05")
    assert len(items) == 2
    assert items[0].correct == "ウ"
    assert items[1].correct == "イ"
    assert items[0].category == "科目A"
    assert len(items[0].choices) == 4


_KAMOKU_B_ANS = """
問1 ア
問2 ク
問3 エ
問4 エ
問5 エ
問6 ア
"""

# 科目B: 擬似言語仕様が問題より前に来る（appendix skip バグの再現用）
_KAMOKU_B_WITH_APPENDIX = """
擬似言語の記述形式（基本情報技術者試験用）
if (条件)
  処理
endif

問1 次のプログラムの空欄に入る正しい記述の組合せはどれか。
ア maxNum mod i ア maxNum mod j
イ maxNum div i ウ maxNum div j

問2 表計算に関する問題。
ア 2 イ 5 ウ 9 エ 14 オ 20 カ 30 キ 40 ク 50
"""


def test_parse_ipa_kamoku_b_with_front_appendix() -> None:
    """擬似言語仕様が冒頭にある科目B PDF でも問題を抽出できる。"""
    items = parse_ipa_kamoku_b(_KAMOKU_B_WITH_APPENDIX, _KAMOKU_B_ANS, "2023r05")
    assert len(items) == 2
    assert items[0].question_number == 1
    assert items[1].correct == "ク"
    assert "共通仕様" not in items[0].body
    assert items[0].appendix


def test_parse_ipa_kamoku_b_multichoice() -> None:
    items = parse_ipa_kamoku_b(_KAMOKU_B_QS, _KAMOKU_B_ANS, "2023r05")
    assert len(items) == 2
    q2 = items[1]
    assert q2.correct == "ク"
    marks = [m for m, _ in q2.choices]
    assert "ク" in marks
    assert len(q2.choices) >= 4


def test_extracted_to_qid() -> None:
    assert extracted_to_qid("2023r05", "B", 2) == "ipa-2023r05-b-q02"


def test_needs_visual_body_figure_hint() -> None:
    assert needs_visual_body("図1に示すネットワーク構成はどれか。")
    assert needs_visual_body("表に示すようにCPUの性能を比較する。")


def test_needs_visual_body_truth_table() -> None:
    body = "X と Y の真理値表\n0 0 0 1\n0 1 0 1\n1 0 0 1\n1 1 1 1"
    assert needs_visual_body(body)


def test_needs_visual_body_plain_text_false() -> None:
    assert not needs_visual_body("デッドロックの発生条件として不適切なものはどれか。")
