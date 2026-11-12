<!-- Translated from Installing-Hoard (English 9c193036aa76). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Installing-Hoard">English</a> · <b>日本語</b> · <a href="Hoard-설치">한국어</a> · AIの助けを借りて英語版から翻訳したページです。英語版と内容が違うときは、英語版が正しい情報です。おかしな訳を見つけたら<a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">翻訳の修正</a>で教えてください。</sub></p>

HoardはWindows、macOS、Linux(AppImage、.deb、Flatpak)向けのアプリです。3つのどれでも、ソースから実行することもできます。

5.2.0 beta 6から、Hoardは新しい作り方(ウィンドウはTauri、サーバーはNuitkaでコンパイル)で作られていて、ファイルも新しくなりました。このページはそれについて説明しています。5.2.0が出るまでの最新リリースであるHoard 5.1は、これまでどおりの方法でインストールします。各セクションに、5.1で違う点を書いています。

## 新しいHoardに移る

Hoard 5.1.4と5.2.0 beta 5は、これまでの作り方(PyInstaller)で作られた最後のHoardです。これより後のバージョンは、新しいアプリとしてインストールされます。そのため、Hoardは自分でそれに更新できません。古いHoardを先にアンインストールしないと、Hoardが2つになってしまいます。新しいバージョンが出ると、Hoardのバーの下でお知らせします。

1. 今のHoardをアンインストールします:
   - **Windows:** Windowsの設定 › アプリ › インストールされているアプリ › Hoard › アンインストール。
   - **macOS:** Hoardを終了して、アプリケーションからゴミ箱に移動します。
   - **Linux(Flatpak):** アンインストールするものはありません。新しいFlatpakが古いものに上書きでインストールされます(Flatpakにとっては同じアプリです)。AppImageや.debにしたい場合は、ソフトウェアセンターでFlatpakを削除するか、`flatpak uninstall io.github.soloflighter1010.Hoard` を実行します。
   - **ソースから実行している場合:** アンインストールするものはありません。
2. お使いのコンピューター用の新しいHoardを[リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)からダウンロードして、下の手順でインストールします。

ライブラリ、設定、サインイン、ダウンロードはそのまま残ります。アンインストールで消えるのはプログラムだけで、新しいHoardも古いHoardと同じように見つけます。

## Windows

1. [リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)から **`Hoard-<version>-windows-setup.exe`** をダウンロードして実行します。あなたのアカウントだけにインストールされ、管理者の確認は出ません。インストール先は `%LOCALAPPDATA%\Hoard` で、スタートメニューにHoardが追加されます。あなたのアカウントだけが変更できるフォルダーで、ストアのサインインを安全に保つためです。
2. リリースからしばらくの間、Windowsが **「WindowsによってPCが保護されました」** と表示することがあります。Hoardにはコード署名があります(中のプログラムとライブラリすべてに)。**詳細情報** を選ぶと、発行元としてHoardのメンテナーが表示されます。新しい発行元は、インストールする人が増えるにつれてMicrosoftの信頼を得るので、この警告は時間とともに出なくなります。**実行** を選んでください。先にファイルが本物か確かめたい場合は、[ダウンロードしたファイルを確かめる](#ダウンロードしたファイルを確かめる)をご覧ください。
3. スタートメニューから **Hoard** を開きます。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

Hoard 5.1のインストーラーは、[最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)の **`Hoard-Setup-<version>.exe`** で、インストール先は `%LOCALAPPDATA%\Programs\Hoard` です。

ウィンドウを閉じるとHoardは終了します。ダウンロード中は先に確認します。止めて閉じる、バックグラウンドで続ける、すぐに閉じる、から選べます(途中で止まったダウンロードは、次回その続きから再開します)。

**Hoardのウィンドウ** はMicrosoft Edge WebView2を使います。Windows 11には含まれていて、Windows 10でも最新に保たれています。

### アップデート

**設定** の **Hoardのアップデート** で **今すぐ確認** を選びます。新しいバージョンがあれば、**(バージョン)にアップデート** を選びます。Hoardは閉じ(実行中のダウンロードは次回再開します)、ウィンドウが新しいバージョンのインストーラーをダウンロードしてインストールし、Hoardをもう一度開きます。インストーラーは、Hoardのウィンドウに組み込まれたHoard自身の鍵の署名があるときだけ残すので、ほかのものが代わりにインストールされることはありません。更新やダウンロードの途中ではアップデートしません。終わるのを待つか、**停止** してください。

**アップデートを自動で確認**(5.1からはオフにしない限りオン。前から使っているHoardは、あなたの選んだままです)がオンなら、Hoardは起動するたびと、開いている間は1日1回、バックグラウンドでGitHubに問い合わせます。新しいバージョンがあると、ページの上、Hoardのバージョンの横に **(バージョン)にアップデート** と表示されます。確認のときにGitHubに送るのはリクエストそのものだけです。[セキュリティとプライバシー](セキュリティとプライバシー)をご覧ください。

新しいインストーラーを、いつでも自分で今のHoardに上書きで実行することもできます。アップデートはプログラムのファイルを置き換えるので、古いバージョンのものは残りません。(Hoard 5.1も、`Hoard-Setup` でインストールしたときは同じようにアップデートをインストールします。その場合はインストーラーをリリースのチェックサムで確かめます。)

設定、ライブラリ、サインイン、タグはプログラムと同じフォルダー(`%LOCALAPPDATA%\Hoard`)に、ファイルはダウンロードフォルダーにありますが、インストール、アップデート、アンインストールで触れるのはプログラム自身のファイルだけです。

### アンインストール

ほかのアプリと同じように、Windowsの **設定 › アプリ** から行います。消えるのはプログラムだけです(アプリのデータを削除するオプションで消えるのは、ウィンドウ自身のキャッシュだけです)。Hoardが保管しているものをすべて消すには、[Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください。

### ダウンロードしたファイルを確かめる

どのリリースも、このリポジトリからGitHub Actionsで直接ビルドされ、どうビルドしたかの署名付きの記録があります。[GitHub CLI](https://cli.github.com/)で:

```
gh attestation verify Hoard-<version>-windows-setup.exe -R Soloflighter1010/Hoard-Asset-Manager
```

リリースのどのファイルにも同じように使えます(`Hoard-<version>-macos-apple-silicon.dmg`、`Hoard-<version>-linux-x86_64.AppImage` など)。

各リリースにはチェックサムも載っています。インストーラーは `SHA256SUMS-windows-x86_64.txt`、Mac用のファイルは `SHA256SUMS-macos-apple-silicon.txt` と `SHA256SUMS-macos-intel.txt`、AppImageと.debは `SHA256SUMS-linux-x86_64.txt`、Flatpakは `SHA256SUMS-flatpak.txt`、ソースのzipは `SHA256SUMS.txt` です。PowerShellでは `Get-FileHash .\Hoard-<version>-windows-setup.exe` で比べる値が表示されます。Macでは `shasum -a 256 <file>`、Linuxでは `sha256sum <file>` です。

どのファイルも、リリースを公開する前にVirusTotalでスキャンされ、リリースノートから各ファイルのレポートを開けます。Mac版のHoardはAppleの署名がなく、新しく署名したプログラムはまだ評判が少ないので、まれに1つか2つのエンジンが誤って検出することがあります。どのエンジンかはレポートでわかります。いずれにしても、各リリースは公開前に人の目で確認しています。

## macOS

HoardはmacOS 11(Big Sur)以降で動きます。

1. お使いのMac用のディスクイメージを[リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)からダウンロードします。MシリーズのチップのMacは **`Hoard-<version>-macos-apple-silicon.dmg`**、IntelのMacは **`Hoard-<version>-macos-intel.dmg`** です。(Appleメニュー › **このMacについて** でわかります。「チップ Apple M…」か「プロセッサ … Intel」です。)
2. 開いて、**Hoard** を **アプリケーション** にドラッグします。
3. アプリケーションからHoardを開きます。HoardはまだAppleの署名がない(毎年費用がかかるため)ので、初回はmacOSが **開けません**、または **悪質なソフトウェアかどうかを確認できません** と表示します。**完了** を選び(ゴミ箱に入れないでください)、**システム設定 › プライバシーとセキュリティ** を開いて、Hoardについてのメッセージまでスクロールし、**このまま開く** を選びます。先にファイルが本物か確かめたい場合は、[ダウンロードしたファイルを確かめる](#ダウンロードしたファイルを確かめる)をご覧ください。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

Hoard 5.1は代わりにパッケージで、[最新リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)の **`Hoard-<version>-macos-apple-silicon.pkg`** か **`...-macos-intel.pkg`** です。開いて、上と同じように **プライバシーとセキュリティ** で許可すると、アプリケーションにHoardがインストールされます。

Hoardのブラウザーが初めてストアにサインインするとき、macOSがキーチェーンを使ってよいか尋ねます。**常に許可** を選んでください。Hoardのブラウザー(Chromium、約150 MB)は一度だけ `~/Library/Caches/ms-playwright` にダウンロードされます。

**アップデート:** **設定 › Hoardのアップデート** で新しいバージョンに **アップデート** します。Windowsと同じように、Hoardのウィンドウがダウンロードし、Hoardの署名があるときだけ残して、アプリケーションのアプリを置き換え、もう一度開きます。(Hoard 5.1は、どのパッケージをダウンロードすればよいかを伝えるので、上と同じように開きます。)**アンインストール:** **Hoard** をアプリケーションからゴミ箱にドラッグします。設定、ライブラリ、サインイン、タグは `~/Library/Application Support/Hoard` にあり、削除しない限り残ります([Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください)。

## Linux

Linux向けのHoardは、x86_64(IntelとAMD)のコンピューター向けで、3つの形があります:

- **AppImage**(`Hoard-<version>-linux-x86_64.AppImage`): ほとんどのLinuxで動く1つのファイルです。実行できるようにして(プロパティで、または `chmod +x Hoard-<version>-linux-x86_64.AppImage`)、開きます。自分でアップデートします。
- **.deb**(`Hoard-<version>-linux-amd64.deb`): Debian、Ubuntuとその仲間向けです。ソフトウェアセンターで開くか、`sudo apt install ./Hoard-<version>-linux-amd64.deb` を実行します。自分でアップデートし、アップデートをインストールするときにパスワードを尋ねます。
- **Flatpak**(`Hoard-<version>-linux-x86_64.flatpak`): 下で説明します。サンドボックスの中で動き、Hoard 5.1もこの形です。

HoardのウィンドウはWebKitGTKを使います。.debは一緒にインストールし、AppImageは中に持っていて、Flatpakはランタイムと一緒に入手します。どれも設定、ライブラリ、サインイン、タグを、ほかのLinux版Hoardと同じ `~/.local/share/Hoard` に保管するので、ほかの形のライブラリも引き継がれ、Hoard for Unityからも見つかります。サインインにはキーリングが必要です。GNOME Keyring、Secret Serviceをオンにした KeePassXC、KWalletのどれかです。

### Flatpak

ほとんどのデスクトップLinuxには、もうFlatpakがあります。ない場合は[flatpak.org/setup](https://flatpak.org/setup/)をご覧ください。

1. [リリース](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)から **`Hoard-<version>-linux-x86_64.flatpak`** をダウンロードします。
2. ソフトウェアセンター(GNOME Software、KDE Discover)で開くか、ターミナルからインストールします:

   ```
   flatpak install --user Hoard-<version>-linux-x86_64.flatpak
   ```

   HoardはGNOMEランタイムで動き、Flatpakはそれを[Flathub](https://flathub.org/)から入手します。`org.gnome.Platform` が見つからないと表示されたら、一度Flathubを追加してからやり直してください:
   `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
3. アプリケーションメニューから **Hoard** を開きます(または `flatpak run io.github.soloflighter1010.Hoard`)。専用のウィンドウで開き、短いセットアップアシスタントが残りを案内します。[はじめに](はじめに)をご覧ください。

Flatpakが使えるのは、ネットワーク、ウィンドウの表示、キーリング(サインイン用)、ホームフォルダーとリムーバブルドライブ(ダウンロードフォルダー用)だけです。Hoardのブラウザー(Chromium、約150 MB)は一度だけ `~/.var/app/io.github.soloflighter1010.Hoard/cache` にダウンロードされます。

**アップデート:** **設定 › Hoardのアップデート** に新しいバージョンがあると表示されたら、そのバージョンの `.flatpak` をダウンロードして、上と同じようにインストールします。古いものと置き換わります。**アンインストール:** `flatpak uninstall io.github.soloflighter1010.Hoard`(またはソフトウェアセンター)。設定とライブラリは残ります。それも消すには[Hoardの保存場所](Hoardの保存場所#すべてを削除する)をご覧ください。

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
