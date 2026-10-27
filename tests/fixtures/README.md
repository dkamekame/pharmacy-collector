# テスト用HTML

3地域の一覧ページを **2026-10-27 に実際に保存したもの**（加工なし）。抽出ルール（config.yaml）が実ページで1件に絞れるかをテストする。

| ファイル | 元のページ |
|---|---|
| `kanto.html` | https://kouseikyoku.mhlw.go.jp/kantoshinetsu/chousa/shitei.html |
| `tohoku.html` | https://kouseikyoku.mhlw.go.jp/tohoku/gyomu/gyomu/hoken_kikan/itiran.html |
| `tokai_hokuriku.html` | https://kouseikyoku.mhlw.go.jp/tokaihokuriku/newpage_00287.html |

サイト構造が変わって config.yaml を直したときは、新しいページを保存し直してからテストを通す（手順はリポジトリ直下の README「設定の変え方」）。
テストの期待値（URLが `r0810` / `2610` になっていること）も、保存し直した月に合わせて `tests/conftest.py` の `FILE_URLS` を更新する。
