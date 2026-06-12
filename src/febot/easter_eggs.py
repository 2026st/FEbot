"""Easter eggs and casual conversation handlers."""

import logging
import random
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

# MBTI Quiz structure
MBTI_Q1 = {
    "text": "【MBTI風エンジニア診断 - 第1問】\nバグを見つけたとき、あなたは？",
    "options": [
        {"text": "A) すぐに修正に取りかかる", "value": "A"},
        {"text": "B) まず原因を徹底調査", "value": "B"},
    ],
}

MBTI_Q2 = {
    "text": "【MBTI風エンジニア診断 - 第2問】\n新しい技術を学ぶとき、あなたは？",
    "options": [
        {"text": "A) 公式ドキュメントを読む", "value": "A"},
        {"text": "B) とりあえず動かしてみる", "value": "B"},
    ],
}

MBTI_RESULTS = {
    "AA": "あなたは【慎重派アーキテクト】タイプのエンジニア！\n基礎を大切にし、堅牢なシステムを作る才能があります🏢",
    "BA": "あなたは【実践派スペシャリスト】タイプのエンジニア！\n原因を深く探りつつ、手を動かして解決するバランス感覚を持っています⚖️",
    "AB": "あなたは【理論派リサーチャー】タイプのエンジニア！\nドキュメントを読み込み、理論に基づいた美しいコードを書くのが得意です📚",
    "BB": "あなたは【直感派ハッカー】タイプのエンジニア！\n圧倒的なスピードでプロトタイプを作り上げる突破力を持っています🚀",
}


class EasterEggHandler:
    def __init__(self, config_path: Path | None = None):
        self.rules = []
        if config_path is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
            config_path = root_dir / "data" / "easter_eggs.yaml"

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self.rules = data.get("rules", [])
            except Exception as e:
                log.error(f"Failed to load easter eggs config: {e}")

    def try_handle(self, text: str, say, thread_ts: str | None = None) -> bool:
        """Returns True if the message was handled as an Easter egg."""
        text_lower = text.lower()
        kwargs = {"thread_ts": thread_ts} if thread_ts else {}

        for rule in self.rules:
            matched = False
            for kw in rule.get("keywords", []):
                kw_lower = kw.lower()
                if rule.get("match_type") == "exact":
                    if text_lower == kw_lower:
                        matched = True
                        break
                else:  # partial
                    if kw_lower in text_lower:
                        matched = True
                        break

            if matched:
                rtype = rule.get("type")
                responses = rule.get("responses", [])

                if rtype in ("simple", "random") and responses:
                    msg = random.choice(responses)
                    say(msg, **kwargs)
                    return True

                elif rtype == "mbti":
                    self._start_mbti(say, **kwargs)
                    return True

        return False

    def _start_mbti(self, say, **kwargs):
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": MBTI_Q1["text"]}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": opt["text"]},
                        "action_id": f"mbti_q1_{opt['value']}",
                        "value": opt["value"],
                    }
                    for opt in MBTI_Q1["options"]
                ],
            },
        ]
        say(text="MBTI診断を開始します", blocks=blocks, **kwargs)


def handle_mbti_action(action_id: str, body: dict, client):
    """Handle MBTI button clicks."""
    parts = action_id.split("_")

    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    if len(parts) >= 3 and parts[1] == "q1":
        ans1 = parts[2]
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": MBTI_Q2["text"]}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": opt["text"]},
                        "action_id": f"mbti_q2_{ans1}_{opt['value']}",
                        "value": opt["value"],
                    }
                    for opt in MBTI_Q2["options"]
                ],
            },
        ]
        client.chat_update(channel=channel_id, ts=message_ts, text="MBTI診断 第2問", blocks=blocks)

    elif len(parts) >= 4 and parts[1] == "q2":
        ans1 = parts[2]
        ans2 = parts[3]
        result_key = ans1 + ans2
        result_text = MBTI_RESULTS.get(result_key, "謎のエンジニアタイプです👾")

        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"【診断結果】\n{result_text}"}}
        ]
        client.chat_update(channel=channel_id, ts=message_ts, text="MBTI診断 結果", blocks=blocks)
