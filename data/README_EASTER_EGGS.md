# イースターエッグ・日常会話機能の追加手順

FEbotのイースターエッグや日常会話（挨拶、感謝など）のキーワードや返答は、`data/easter_eggs.yaml` で管理されています。

## 新しいキーワード・返答の追加方法

`data/easter_eggs.yaml` ファイルをテキストエディタで開き、`rules` リストに新しいルールを追加します。

### 基本構造

```yaml
  - id: rule_name # 一意のID（英数字）
    type: simple # simple（単一/ランダム返答）, random（ランダム返答）, mbti（MBTI診断）など
    match_type: partial # partial（部分一致） または exact（完全一致）
    keywords:
      - "キーワード1"
      - "キーワード2"
    responses:
      - "返答パターン1"
      - "返答パターン2"
```

### タイプの種類
- `simple` / `random`: `responses` の中からランダムに1つの返答を返します。
- `mbti`: MBTI風の診断フローを開始します（返答パターンの追加はPythonコード側の修正が必要です）。

### マッチ条件 (`match_type`)
- `partial`: ユーザーのメッセージにキーワードが含まれていれば反応します。
- `exact`: ユーザーのメッセージがキーワードと完全に一致した場合のみ反応します。

※ キーワードの検知は大文字・小文字を区別しません。

### 追加例（新しい挨拶を追加する場合）

```yaml
  - id: new_greeting
    type: simple
    match_type: partial
    keywords: ["ヤッホー", "やっほー"]
    responses:
      - "ヤッホー！今日も勉強頑張りましょう！"
```

ファイルを保存してボットを再起動すると、新しいルールが適用されます。
