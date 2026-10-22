<!-- Translated from Installing-Hoard (English 9ab876e03205). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Installing-Hoard">English</a> · <b>日本語</b> · <a href="Hoard-설치">한국어</a> · AIの助けを借りて英語版から翻訳したページです。英語版と内容が違うときは、英語版が正しい情報です。おかしな訳を見つけたら<a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">翻訳の修正</a>で教えてください。</sub></p>

HoardはWindows、macOS、Linux(Flatpak)向けのアプリです。3つのどれでも、ソースから実行することもできます。

## Windows

1. [最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)から **`Hoard-Setup-<version>.exe`** をダウンロードして実行します。あなたのアカウントだけにインストールされ、管理者の確認は出ません。インストール先は `%LOCALAPPDATA%\Programs\Hoard` で、スタートメニューにHoardが追加されます(デスクトップのアイコンは選べます)。フォルダーは変えられません。あなたのアカウントだけが変更できるフォルダーで、ストアのサインインを安全に保つためです。(古いセットアップでほかの場所にインストールしたHoardは、アップデートのときにここへインストールされます。そのあと古いフォルダーは削除してかまいません。)
2. リリースからしばらくの間、Windowsが **「WindowsによってPCが保護されました」** と表示することがあります。Hoardにはコード署名があります。**詳細情報** を選ぶと、発行元としてHoardのメンテナーが表示されます。新しい発行元は、インストールする人が増えるにつれてMicrosoftの信頼を得るので、この警告は時間とともに出なくなります。**実行** を選んでください。先にファイルが本物か確かめたい場合は、[ダウンロードしたファイルを確かめる](#ダウンロードしたファイルを確かめる)をご覧ください。
3. スタートメニューから **Hoard** を開きます。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

ウィンドウを閉じるとHoardは終了します。ダウンロード中は先に確認します。止めて閉じる、バックグラウンドで続ける、すぐに閉じる、から選べます(途中で止まったダウンロードは、次回その続きから再開します)。

**以前ポータブル版のzipを使っていた?** 4.3.6から公開をやめました。ウイルス対策ソフトが何度も誤検知したためです。代わりに `Hoard-Setup` を実行してください。設定、ライブラリ、ダウンロードはそのまま引き継がれ(プログラムとは別に保管されています)、それ以降はHoardが自分でアップデートします。そのあと、zipを展開したフォルダーは削除してください。

**Hoardのウィンドウ** はMicrosoft Edge WebView2を使います。Windows 11には含まれていて、Windows 10でも最新に保たれています。ない場合は、Hoardがそう伝え、代わりにWebブラウザーで開きます。終了するには **設定** の **Hoardを終了** を選びます。

### アップデート

**設定** の **アップデート** で **今すぐ確認** を選びます。新しいバージョンがあれば、**(バージョン)にアップデート** を選びます。HoardはGitHubのリリースからインストーラーをダウンロードし、確認してから閉じ(実行中のダウンロードは次回再開します)、インストールしてもう一度開きます。実行するのは、SHA-256がリリースの `SHA256SUMS-windows.txt` とGitHubに表示されるファイルのチェックサムの両方と一致するインストーラーだけで、一致しないものは削除します。更新やダウンロードの途中ではアップデートしません。終わるのを待つか、**停止** してください。

**アップデートを自動で確認**(5.1からはオフにしない限りオン。前から使っているHoardは、あなたの選んだままです)がオンなら、Hoardは起動するたびと、開いている間は1日1回、バックグラウンドでGitHubに問い合わせます。新しいバージョンがあると、ページの下に **(バージョン)にアップデート** と表示されます。確認のときにGitHubに送るのはリクエストそのものだけです。[セキュリティとプライバシー](セキュリティとプライバシー)をご覧ください。

Hoardが自分でアップデートをインストールするのは、`Hoard-Setup` でインストールしたときだけです。ポータブル版のzipのコピー、Mac版アプリ、Flatpak、Pythonで実行しているHoardでは、新しいバージョンがあること、どのファイルを入手すればよいかを伝え、そのリンクを表示します。新しいセットアップは、いつでも自分で実行することもできます。先にアンインストールする必要はなく、アップデートはプログラムのファイルをすべて置き換えるので、古いバージョンのものは残りません。

設定、ライブラリ、サインイン、タグはHoardのアプリデータフォルダー(`%LOCALAPPDATA%\Hoard`)に、ファイルはダウンロードフォルダーにあるので、インストール、アップデート、アンインストールで消えることはありません。

### アンインストール

ほかのアプリと同じように、Windowsの **設定 › アプリ** から行います。削除されるのはプログラムだけです。Hoardが保管しているものをすべて削除するには、[Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください。

### ダウンロードしたファイルを確かめる

どのリリースも、GitHub Actionsがこのリポジトリから直接ビルドしていて、どうビルドしたかの署名付きの記録があります。[GitHub CLI](https://cli.github.com/)で次のように確かめられます。

```
gh attestation verify Hoard-Setup-<version>.exe -R Soloflighter1010/Hoard-Asset-Manager
```

リリースのどのファイルでも同じように確かめられます(`Hoard-<version>-macos-apple-silicon.pkg`、`Hoard-<version>-linux-x86_64.flatpak` など)。

各リリースにはチェックサムもあります。インストーラーとWindows用zipは `SHA256SUMS-windows.txt`、Mac用パッケージは `SHA256SUMS-macos-apple-silicon.txt` と `SHA256SUMS-macos-intel.txt`、Flatpakは `SHA256SUMS-linux.txt`、ソースのzipは `SHA256SUMS.txt` です。比べる値は、PowerShellでは `Get-FileHash .\Hoard-Setup-<version>.exe`、Macでは `shasum -a 256 <file>`、Linuxでは `sha256sum <file>` で表示できます。

どのファイルも、リリースを公開する前にVirusTotalでスキャンしています。リリースノートに各ファイルのレポートへのリンクがあります。HoardのMac用パッケージはAppleの署名がなく、新しく署名したプログラムはまだ評判が少ないため、まれに1つか2つのエンジンが誤って検出することがあります。どのエンジンかはレポートで分かります。どのリリースも、公開前に人の手で確認しています。

## macOS

HoardはmacOS 11(Big Sur)以降で動きます。

1. [最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)から、あなたのMac用のパッケージをダウンロードします。Mシリーズのチップを搭載したMacなら **`Hoard-<version>-macos-apple-silicon.pkg`**、IntelのMacなら **`Hoard-<version>-macos-intel.pkg`** です。(Appleメニュー › **このMacについて** で分かります。「チップ Apple M…」または「プロセッサ … Intel」と表示されます。)
2. 開きます。HoardはまだAppleの署名がない(毎年費用がかかるため)ので、macOSは **開けない**、または **悪質なソフトウェアがないことを確認できない** と表示します。**完了** を選び(「ゴミ箱に入れる」ではありません)、**システム設定 › プライバシーとセキュリティ** を開いて、Hoardのパッケージについてのメッセージまでスクロールし、**このまま開く** を選びます。先にファイルが本物か確かめたい場合は、[ダウンロードしたファイルを確かめる](#ダウンロードしたファイルを確かめる)をご覧ください。
3. インストーラーが **Hoard** を **アプリケーション** に入れます(すべてのアカウント向けにインストールするアプリと同じく、Macのパスワードを聞かれます)。アプリケーションかLaunchpadから開きます。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

Hoardのブラウザーがはじめてストアにサインインするとき、macOSがキーチェーンを使ってよいか聞いてきます。**常に許可** を選んでください。Hoardのブラウザー(Chromium、約150 MB)は1回だけ `~/Library/Caches/ms-playwright` にダウンロードされます。

**アップデート:** **設定 › アップデート** に新しいバージョンがあると表示されたら、そのバージョンのパッケージをダウンロードして、上と同じように開きます。古いHoardが置き換えられます。**アンインストール:** **Hoard** をアプリケーションからゴミ箱にドラッグします。設定、ライブラリ、サインイン、タグは `~/Library/Application Support/Hoard` にあり、削除しない限り残ります([Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください)。

## Linux(Flatpak)

Linux版のHoardは、x86_64(IntelとAMD)のコンピューター向けの[Flatpak](https://flatpak.org/)です。デスクトップ向けのLinuxの多くにはFlatpakが入っています。入っていない場合は[flatpak.org/setup](https://flatpak.org/setup/)をご覧ください。

1. [最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)から **`Hoard-<version>-linux-x86_64.flatpak`** をダウンロードします。
2. ソフトウェアセンター(GNOME Software、KDE Discover)で開くか、ターミナルからインストールします。

   ```
   flatpak install --user Hoard-<version>-linux-x86_64.flatpak
   ```

   HoardはGNOMEランタイムで動き、Flatpakはそれを[Flathub](https://flathub.org/)から取得します。`org.gnome.Platform` が見つからないと表示されたら、一度Flathubを追加してからやり直してください: `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
3. アプリケーションメニューから **Hoard** を開きます(または `flatpak run io.github.soloflighter1010.Hoard`)。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

Flatpakが使えるのは、ネットワーク、ウィンドウの表示、キーリング(サインインのため。GNOME Keyring、Secret Serviceをオンにした KeePassXC、KWallet)、ホームフォルダーとリムーバブルドライブ(ダウンロードフォルダーのため)だけです。設定、ライブラリ、サインイン、タグは、ほかのLinux版Hoardと同じく `~/.local/share/Hoard` に保管するので、ソースから実行していたHoardのライブラリも引き継がれ、Hoard for Unityからも見つかります。Hoardのブラウザー(Chromium、約150 MB)は1回だけ `~/.var/app/io.github.soloflighter1010.Hoard/cache` にダウンロードされます。

**アップデート:** **設定 › アップデート** に新しいバージョンがあると表示されたら、そのバージョンの `.flatpak` をダウンロードして上と同じようにインストールします。古いものが置き換えられます。**アンインストール:** `flatpak uninstall io.github.soloflighter1010.Hoard`(またはソフトウェアセンター)。設定とライブラリは残ります。それも削除するには[Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください。

## ソースから実行する(Windows、macOS、Linux)

1. [Python 3.10以降](https://www.python.org/downloads/)をインストールします。
2. [最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)から `Hoard-<version>.zip` をダウンロードし、自分のフォルダーに展開します。
3. `Hoard.bat`(Windows)または `./run.sh`(macOSとLinux)を実行します。

最初の実行で、そのフォルダーに専用のPython環境を作ります。すべてのパッケージを事前に記録した指紋と照合するので、改ざんされたパッケージはインストールされません。Windowsでは、そのフォルダーをあなたのアカウントだけが変更できるようにもします。

ソースから実行すると、Hoardは専用のウィンドウではなくWebブラウザーで開きます。終了するには **設定** の **Hoardを終了** を選ぶか、Hoardのページを閉じるだけでかまいません。最後のページを閉じてから数分で自動的に止まります。

ストアへのサインインには、WindowsではMicrosoft Edgeを、それ以外やEdgeがない場合はHoard専用のブラウザー(バージョンを固定したChromium、約150 MB、1回だけダウンロード)を使います。

- **macOS** では、Hoardのブラウザーがキーチェーンを使ってよいか1回聞かれます。**常に許可** を選んでください。
- **Linux** では、サインインを守るためにキーリングが必要です。GNOME Keyring、Secret Serviceをオンにした KeePassXC、またはKWalletです。デスクトップのないコンピューターについては[ストア](ストア#サインイン)をご覧ください。ブラウザーが起動しない場合は、Hoardのフォルダーで `.venv/bin/python -m playwright install-deps chromium` を実行してください。

## Hoard 1.xから移行する

サインインとタグは自動で引き継がれます。セットアップアシスタントの **以前Hoardを使っていましたか?** のステップで、ライブラリの一覧とダウンロードフォルダーを引き継ぎます。1.xを実行していたフォルダーを選んでください。コマンドラインでは `hoard-cli migrate <folder>` です。
