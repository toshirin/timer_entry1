# timer_entry1

時刻起点の短期売買戦略を研究・検証・運用するための専用リポジトリです。
本リポジトリは単一戦略に集中し、戦略階層を持たずに `scan` / `qualify` / `runtime` / `ops` を並列に管理します。

最上位の不変方針は [docs/FX_Research_Constitution.md](docs/FX_Research_Constitution.md) に置きます。
特に Bid / Ask 完全分離、未来参照禁止、監視窓の分離は本リポジトリ全体で厳守します。

## このリポジトリの目的

- タイマー売買戦略の研究資産を専用 repo として整理する
- scan と qualify と runtime の整合性を高める
- 軽量フィルター、価格系列規約、1分足バックテスト core を共通化する
- 実装監査を parity test と別系統 LLM レビューで補強する

## 用語定義

- `strategy`
  - 売買のやり方そのものを指す
  - 本リポジトリではタイマー売買戦略そのものを意味する
- `slot`
  - 1時間ごとの時間帯を指す
  - 例として `tyo09` や `lon08` のような単位で扱う
- `setting`
  - 1つの slot の中で使う具体的な売買条件を指す
  - entry 時刻、forced exit 時刻、TP / SL、軽量フィルター条件を含む

## ディレクトリ方針

- `docs/`
  - 研究憲法や repo 全体の設計方針を置く
- `src/timer_entry/`
  - 共通 core を置く
  - Bid / Ask 規約、時刻処理、特徴量、軽量フィルター、1分足バックテスト、共通 dataclass を管理する
  - 詳細は `src/timer_entry/README.md` と `src/timer_entry/Spec.md` を参照する
- `scan/`
  - 全時間帯・条件帯の総当たり探索
  - 役割はエッジ検出と仮説生成であり、最終運用判断ではない
- `qualify/`
  - scan で見つけた候補の深掘りと昇格審査
  - E001-E008 を同一フレームワーク上で実行する
  - tick replay はここで共通化する
- `runtime/`
  - 実売買を行う本番コード
  - 共通 core の setting 定義と軽量フィルターを利用する
- `ops/`
  - runtime 外側の運用補助をまとめる
  - 売買結果分析、設定管理補助、監視補助、日次集計などを含む
- `tools/`
  - データ変換や補助スクリプトを置く
- `tests/`
  - 共通 core、parity test、sanity test を置く

## scan / qualify / runtime / ops の役割分担

### scan

- 目的は広い探索であり、仮説生成に留める
- 1分足ベースの総当たり探索を実施する
- 軽量フィルターは系統ごとの当たりを見るため、基本閾値だけを確認する
- 例として `pre_open_slope` では `ge0` / `le0` のような粗い確認を行う
- 候補出力は後段で qualify できる形に標準化する

### qualify

- 目的は昇格審査であり、scan の独立監査ではない
- 同じ core を使って深掘り検証を行う
- E001 は scan で反応した filter family を深掘りする段階とする
- 例として `pre_open_slope` では `ge2` / `ge4` などの閾値 sweep、`vol` 系では percentile sweep を行う
- `all` は追加の有効 filter がないかを見直す入口としても使う
- holdout、walk-forward、slippage、entry delay、kill-switch、risk_fraction、tick replay をここで評価する
- E001-E008 は個別スクリプトの寄せ集めではなく、共通シナリオ実行基盤で扱う

### runtime

- 目的は設定駆動での実売買である
- strategy setting と filter setting は core で定義した形式に合わせる
- scan / qualify で使った軽量フィルター定義と乖離しないことを重視する

### ops

- 目的は runtime の外側にある運用補助全般である
- 実損益分析だけでなく、設定投入補助、状態確認、日次集計、監査ログ整理も含める

## 共通 core の考え方

`src/timer_entry/` は scan / qualify / runtime にまたがる共通基盤です。
初期段階では少なくとも以下を共通化します。

- 時刻処理
  - JST / London など市場時刻変換
  - 日付境界と監視窓の切り方
  - 東京系は `Asia/Tokyo`、東京以外は `Europe/London` を基準に DST aware に扱う
  - 米国統計時間は時間帯基準の切り替えではなく除外窓として扱う
- 価格系列規約
  - side ごとの entry / TP / SL / forced exit 系列
- 特徴量
  - pre-open slope
  - 左右の形
  - pre-range
  - trend ratio
- 軽量フィルター
  - canonical 名称と定義を固定する
- 1分足バックテスト
  - Bid / Ask 規約と same-bar sanity を内包する
- 共通 dataclass
  - strategy setting
  - scan candidate
  - qualify scenario
  - backtest result
  - sanity summary

一方で tick replay は初版では `qualify/` 側でのみ共通化します。

## 実装と監査の方針

- scan / qualify / runtime の入口は分ける
- ただし core のロジックは極力共有する
- 異なってよいのは主に実行 engine であり、仕様は共通 core で固定する
- 監査は独立実装の二重化ではなく、以下の組み合わせで担保する
  - parity test
  - sanity check
  - 別系統 LLM レビュー

特に Bid / Ask 系列、same-bar 競合、forced exit の監視窓分離は最優先監査項目です。

## 実行 engine の分担

- `scan`
  - 高速 engine を使って全探索を行う
  - 主目的は slot ごとのエッジ探索と、軽量フィルター family の当たり探しである
- `qualify`
  - pandas ベースの canonical `backtest_1m` を使う
  - 主目的は setting の深掘りと、軽量フィルター閾値の探索である
- `tick replay`
  - tick ベースの execution 確認に使う
  - 主目的は約定順序、slippage、entry delay、forced exit 現実性の確認である

3者は engine は分かれていても、以下の仕様は同じ core に従う。

- 価格系列規約
- 特徴量定義
- 軽量フィルター定義
- same-bar 解釈
- 保守的 SL exit モデル

## 命名と管理

- ディレクトリ名には世代表記を付けない
- 大きな変更はブランチまたは repo の切り直しで管理する
- filter 名、setting 名、scenario 名は曖昧な通称ではなく仕様固定された canonical 名を使う

## 進め方

1. `src/timer_entry/Spec.md` に共通 core の仕様を固定する
2. `scan/` を立てて総当たり探索を移植する
3. `runtime/` を立てて本番コードを移植する
4. `ops/` を立てて運用補助を整理する
5. `qualify/` を立てて E001-E008 を統合する
6. parity test と sanity test を整備する

## データ前提

- 1分足データは年ごとの pickle を使用する
- tick データは Parquet dataset を使用する
- 具体的なデータ仕様と実装標準は [src/timer_entry/Spec.md](src/timer_entry/Spec.md) を参照する

## 現状

現時点では共通 core と各世代ディレクトリをこれから整備する段階です。
この README は初版の設計方針を固定するためのドラフトであり、実装に合わせて更新します。
