<!-- Translated from Hoard-and-Other-Tools (English 94250bc0e444). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Hoard-and-Other-Tools">English</a> · <b>日本語</b> · <a href="Hoard와-다른-도구">한국어</a> · AIの助けを借りて英語版から翻訳したページです。英語版と内容が違うときは、英語版が正しい情報です。おかしな訳を見つけたら<a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">翻訳の修正</a>で教えてください。</sub></p>

VRChatのクリエイターが使うツールはHoardだけではありません。よく名前が挙がるのは、VRChat公式の **Creator Companion**(VCC)、**ALCOM**、**KonoAsset** の3つです。それぞれ役割が違い、いくつかを組み合わせて使う人もたくさんいます。

- **Creator Companion** は、Unityのプロジェクトとそのパッケージ(VRChat SDKや、ほかの人のリポジトリのパッケージ)を扱うVRChat公式のツールです。
- **ALCOM** は、Creator Companionの代わりになる、速くてオープンソースのツールです。Windows、macOS、Linuxで動きます。
- **KonoAsset** は、ダウンロード済みのVRChatのアセットを、種類、カテゴリー、タグ、対応アバターで整理します。
- **Hoard** は、ストアで買ったものを読み込み、ダウンロードして最新の状態に保ち、Unityのプロジェクトも管理します。

これらは一緒に使えます。Hoardのプロジェクトは、Creator CompanionやALCOMと同じ一覧を使うので、どれかで作ったプロジェクトはほかでも表示されます。

## 並べて比べる

それぞれのできることを、2026年11月時点の各ツール自身のドキュメントからまとめています。ツールは変わるので、下にリンクしたそれぞれのページも確かめてください。

| | Hoard | Creator Companion | ALCOM | KonoAsset |
|---|---|---|---|---|
| **何のためのツールか** | 買ったもの:一覧にし、ダウンロードし、最新に保ち、プロジェクトに入れる | VRChatのUnityプロジェクトとそのパッケージ | Creator Companionの役割を、より速く、より多くのOSで | ダウンロード済みのアセットの整理 |
| **ストア** | Booth、Gumroad、Jinxxy、Payhip、itch.ioで持っているものを、あなたとしてサインインして、または保存したページから読み込む | なし | なし | BOOTHのリンクから商品情報を入力 |
| **ダウンロードとアップデート** | 新しいものと変わったものをダウンロードし、前のバージョンも残す(Payhipのものは一覧にし、ダウンロードはPayhipで) | VPMリポジトリのパッケージ | VPMリポジトリのパッケージを、まとめて、変更履歴つきで | なし:ダウンロードしたものを追加する(ドラッグ&ドロップ、.zipは展開) |
| **整理** | タグ(自分のものとクリエイターのもの)、種類、共有できるセット、価格つきのほしい物リスト、接頭辞つきの検索 | なし | なし | 種類、カテゴリー、タグ、メモ、依存関係、対応アバターでの検索 |
| **Unityプロジェクト** | ライブラリの商品を入れて作る(VRChatのテンプレート、または空)、パッケージとリポジトリ、バックアップ、Gitでのソース管理 | テンプレートから作る、既存のものを追加、移行、バックアップ、パッケージ、ほかの人のリポジトリ(2.1.0から) | テンプレートから作る(自分のテンプレートも、1.1.0から)、バックアップ、Unityのバージョン変更、移行、パッケージとリポジトリ | なし |
| **Unityの中で** | Hoard for Unity:ライブラリをウィンドウで表示、商品とセットのインポート、クレジット | VRChat SDK | なし | なし |
| **OS** | Windows、macOS、Linux | Windows 10、11(macOSとLinuxでは、一部をコマンドラインで) | Windows、macOS、Linux(Linuxはコミュニティによるサポート) | Windows 10、11 |
| **言語** | 英語、日本語、韓国語 | 英語 | 英語、日本語、韓国語、ドイツ語、フランス語、中国語(簡体字、繁体字) | 日本語、英語、中国語(簡体字) |
| **価格** | 無料 | 無料 | 無料 | 無料 |
| **ソース** | オープンソース(MITライセンス) | VRChat独自のもので、オープンソースではない | オープンソース(MITライセンス) | オープンソース(MITライセンス) |

## どれを使うか

- **VRChatのパッケージで、アバターやワールドを作るだけなら?** Creator CompanionはVRChat公式のツールで、始め方もそのドキュメントで説明されています。
- **同じことを、もっと速く、またはMacやLinuxで?** ALCOMは同じ設定でCreator Companionの役割をこなすので、行き来できます。
- **ダウンロードしたものを、メモや対応アバターつきで自分で整理したいなら?** KonoAssetはそのためのツールです。
- **KonoAssetからHoardに移るなら?** Hoardのメニューか設定の **KonoAssetから取り込む...** で、ライブラリを取り込めます(5.2.0ベータ5)。BOOTHの商品でHoardのライブラリと照らし合わせ、残りは今の場所のままローカルの商品にして、タグとメモも一緒に取り込みます。[自分のパッケージ](自分のパッケージ#konoassetから)をご覧ください。
- **いくつものストアで買ったものを、ひとつにまとめて、ダウンロードして最新に保ちたいなら?** それがHoardです。商品をプロジェクトに入れられ、プロジェクトの一覧はCreator CompanionやALCOMと共通です。

## それぞれのページ

- Creator Companion:[vcc.docs.vrchat.com](https://vcc.docs.vrchat.com/)
- ALCOM:[vrc-get.anatawa12.com/alcom](https://vrc-get.anatawa12.com/alcom)、[GitHubのソース](https://github.com/vrc-get/vrc-get)
- KonoAsset:[BOOTHのページ](https://silolab.booth.pm/items/6641548)、[GitHubのソース](https://github.com/siloneco/KonoAsset)

内容が古い、またはどれかに公平でないところがあれば、[教えてください](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new/choose)。直します。
