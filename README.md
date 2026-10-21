# ThumbSorter for Autodesk® Fusion®

**English version is below → [English](#english)**

Autodesk Fusion のハブにあるデザインを、サムネイルを見ながら仕分けるアドイン（sin1's studio 製）。
仕分けた結果は次のどちらかで反映できる。

- **同じハブの中で移動**: Fusion の「移動」と同じ操作を自動で行う。バージョン履歴は残る。ダウンロードは不要。
- **パソコンに全部ダウンロード**: ハブの全ファイルを f3d とサムネイル(PNG)で保存する。今の構成のまま／仕分け後の構成のどちらでも。クラウドは変更しない。ダウンロード後は、ファイルサイズで同一のものを自動で探す。

削除は一切しない。画面で「削除」にしたものは、最上位の `DEL` プロジェクトへ移動する（Fusion上で中身を確かめてから手で消す）。

画面は日本語・英語・中国語（簡体字）に対応。Fusion の表示言語に合わせて自動で切り替わり、右上のプルダウンで変えることもできる。

## インストール

1. 緑の「Code」ボタン →「Download ZIP」でダウンロードして展開する（フォルダ名が `FusionSorter-main` なら `FusionSorter` に直す）
2. このフォルダ（`FusionSorter`）を Fusion のアドインフォルダに置く
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - Mac: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. Fusion の「ユーティリティ」タブ →「アドイン」→「スクリプトとアドイン」→「アドイン」タブで `FusionSorter` を実行
4. 同じ場所の「アドイン」パネルに「ThumbSorter」ボタン（カードとフォルダのアイコン）が出る。▼メニューに隠れず直接表示される
5. 次回からは Fusion の起動時に自動で読み込まれる（`runOnStartup`）。止めたいときは「スクリプトとアドイン」で「起動時に実行」を外す

## 使い方

1. 「ThumbSorter」を押すとパネルが開く。ハブを選び、初回は「ハブから最新を取得」（一覧とサムネイルの取得で数分かかる。数百件で3〜5分程度。その間 Fusion は操作できない）
   - クラウドのサムネイルを取得する（デザインは開かない）
   - 次回からはハブを選ぶと前回取得した一覧がすぐ開く。ハブの中身が変わったときは「ハブから最新を取得」
2. 「新しい階層」タブで仕分ける
   - カードをクリックで選択（複数可）→ 左のフォルダをクリックで移動。カードを左へドラッグしても移動できる
   - 新しいフォルダは左の一覧の下で追加（先頭に `/` を付けると最上位＝新しいプロジェクト）
   - 「削除」は `DEL` へ。触らなければ今の場所のまま
   - 変更は自動保存。パネルを閉じても、Fusion を再起動しても続きから
3. 「重複」タブ: 同じ名前のデザインを並べて表示。サムネイルが完全に同じもの、またはダウンロード後にファイルサイズの差が2%未満のものは、版数の多い方を残して他を `DEL` にしてある
4. 「似ているもの」タブ（候補を示すだけで自動では動かさない）
   - 名前が似ているもの: 末尾の番号・v2・(1)・コピーなどを除くと同じ名前になるもの
   - 見た目が似ているもの: サムネイルが近いもの
   - 名前は違うがサイズがほぼ同じもの: ダウンロード後に、サイズの差が0.3%未満で見た目も近いもの
5. 「実行」タブで反映する
   - 移動: 「移動内容を確認」→「移動を実行」→「本当に〇件を移動する」。記録は `moves_日時.csv` に残り、「直前の移動を元に戻す」で戻せる
   - ダウンロード: 構成（今のまま／仕分け後）と保存先を選んで開始。済みのものは飛ばすので、止まっても再実行で続きから。Fusion ごと落ちたデザインは次回から自動で飛ばす

### なぜサイズの判定に幅を持たせるか

f3d は書き出すたびに中身が少し変わり、同じデザインでもサイズが ±1% ほど揺れる（ハッシュも一致しない）。そのため「同じ名前でサイズの差が2%未満」を同一とみなしている。クラウドの一覧からはファイルサイズが取れないので、サイズの判定はダウンロード後に行う。

## 作業フォルダ

`ドキュメント\FusionSorter\<ハブ名>\`

| ファイル | 内容 |
|---|---|
| `inventory.json` | 一覧（サムネイルの見た目ハッシュ、ダウンロード後はサイズも） |
| `plan.json` | 画面で決めた行き先（自動保存） |
| `thumbs\` | クラウドのサムネイル（256px） |
| `thumb_log.txt` | サムネイル取得の結果 |
| `moves_*.csv` | 移動の記録（元に戻すときに使う） |

言語の設定は `ドキュメント\FusionSorter\settings.json` に保存される。移動やダウンロードの記録（CSV）の見出しは、言語によらず英語。

## 注意

- 開いているデザイン、他のデザインから参照されているデザインは移動できないことがある（記録に「失敗」と出る）
- 移動後に空になったフォルダは消さずに残す
- 仕分けは画面上の予定で、「実行」するまでハブは変わらない。未反映のあいだは右上に警告が出て、パネルを閉じたときにも知らせる
- ダウンロードは1件ずつデザインを開くため時間がかかり、その間 Fusion は操作できない
- 無料版（個人利用）ではプロジェクトを新しく作れない（DM-403）。その場合 `DEL` や新しいプロジェクトへの移動は失敗として記録される

## 開発者向け

- `FusionSorter.py`: アドイン本体（ボタンとパレット）
- `sorter_core.py`: 一覧の取得・サムネイル・重複と似ているものの判定・移動・ダウンロード。Python から出す文言（エラー・ダイアログ）は `MSG`
- `palette/index.html`: パレットの画面（Fusion の Qt ブラウザで動くよう、ドラッグは自前で実装）。画面の文言は `I18N`
- `tools/`: アイコン生成と、Fusion なしで判定を試すスクリプト

## ライセンス

MIT License（[LICENSE](LICENSE)）。使い方の解説（日本語）: https://sin1.studio/blog/thumbsorter/

---

## English

ThumbSorter is an add-in for Autodesk Fusion that lets you sort the designs in a hub while looking at their thumbnails (made by sin1's studio).
Apply the result in one of two ways:

- **Move within the same hub**: performs Fusion's "Move" automatically. Version history is kept and nothing is downloaded.
- **Download everything to your PC**: saves every file in the hub as f3d plus a thumbnail (PNG), in either the current layout or the sorted layout. The cloud is not changed. After downloading, identical files are found automatically by file size.

Nothing is ever deleted. Files you mark as "Delete" are moved to a top-level `DEL` project, so you can check them in Fusion and delete them yourself.

The screen is available in Japanese, English and Simplified Chinese. It follows Fusion's display language automatically, and you can switch it with the drop-down at the top right.

### Install

1. Click the green "Code" button → "Download ZIP" and extract it (rename the folder `FusionSorter-main` to `FusionSorter`)
2. Put the `FusionSorter` folder into Fusion's add-in folder
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - Mac: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. In Fusion, open the "Utilities" tab → "Add-Ins" → "Scripts and Add-Ins", and run `FusionSorter` on the "Add-Ins" tab
4. A "ThumbSorter" button (card-and-folder icon) appears in the "Add-Ins" panel, shown directly rather than hidden in the ▼ menu
5. From then on it loads when Fusion starts (`runOnStartup`). To stop that, turn off "Run on Startup" in "Scripts and Add-Ins"

### How to use

1. Press "ThumbSorter" to open the panel. Choose a hub and, the first time, press "Fetch latest from hub" (fetching the list and thumbnails takes a few minutes — 3–5 min for a few hundred files — and Fusion cannot be used meanwhile)
   - It fetches the thumbnails stored in the cloud (designs are not opened)
   - Next time, choosing the hub opens the last list immediately. Press "Fetch latest from hub" when the hub has changed
2. Sort on the "New layout" tab
   - Click cards to select them (multiple allowed) → click a folder on the left to move them. You can also drag cards to the left
   - Add new folders below the list on the left (start the name with `/` to create a top-level project)
   - "Delete" sends a file to `DEL`. Untouched files stay where they are
   - Changes are saved automatically, even if you close the panel or restart Fusion
3. "Duplicates" tab: designs with the same name side by side. When the thumbnails are identical, or the downloaded sizes differ by less than 2%, the one with the most versions is kept and the others are set to `DEL`
4. "Similar" tab (suggestions only; nothing is moved automatically)
   - Similar names: names that become the same after removing trailing numbers, v2, (1), copy, etc.
   - Similar look: thumbnails that look alike
   - Different names, almost the same size: after downloading, files whose sizes differ by less than 0.3% and look alike
5. Apply on the "Run" tab
   - Move: "Preview moves" → "Move now" → "Really move N files". A record is kept in `moves_<date>.csv`, and "Undo last move" puts things back
   - Download: choose the layout (current / sorted) and the destination, then start. Files already saved are skipped, so you can resume by running again. Designs that crashed Fusion are skipped next time

#### Why the size check has a tolerance

An f3d file changes slightly on every export, so the same design varies by about ±1% in size (and the hashes never match). That is why "same name and less than 2% size difference" counts as identical. File sizes are not available from the cloud listing, so the size check runs after downloading.

### Work folder

`Documents\FusionSorter\<hub name>\`

| File | Contents |
|---|---|
| `inventory.json` | The list (thumbnail look hashes, and sizes after downloading) |
| `plan.json` | Where each file goes, as decided on screen (saved automatically) |
| `thumbs\` | Cloud thumbnails (256 px) |
| `thumb_log.txt` | Results of fetching thumbnails |
| `moves_*.csv` | Move records (used by Undo) |

The language setting is stored in `Documents\FusionSorter\settings.json`. The CSV records always use English column names.

### Notes

- Designs that are open or referenced by other designs may fail to move (shown as "failed" in the record)
- Folders left empty after moving are kept
- Sorting is only a plan on screen; the hub does not change until you run it. While there are unapplied moves, a warning appears at the top right, and you are reminded when you close the panel
- Downloading opens each design one by one, so it takes time and Fusion cannot be used meanwhile
- The free (personal use) plan cannot create new projects (error DM-403). Moves to `DEL` or to new projects are then recorded as failed

### License

MIT License ([LICENSE](LICENSE)). A detailed guide (in Japanese): https://sin1.studio/blog/thumbsorter/

---

Autodesk、Autodesk Fusion は、米国およびその他の国における Autodesk, Inc.、その子会社、関連会社の登録商標または商標です。sin1's studio は Autodesk と提携していません。

Autodesk and Autodesk Fusion are registered trademarks or trademarks of Autodesk, Inc., and/or its subsidiaries and/or affiliates in the USA and/or other countries. sin1's studio is not affiliated with Autodesk.
