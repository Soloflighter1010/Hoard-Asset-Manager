"""Hoard's videos, scene by scene (issues #273, #274, #289), and its posters' words (#292): what each shows, for how
long, in which of Hoard's own screens (promo/capture.py), what it says in English, Japanese and Korean, and where the
camera goes. build() turns a video into what promo/player.html draws; promo/render.py films it.

The words for Hoard's own buttons ({Sign in}, {Quick refresh}) come from the app's translations, so a video names
them as Hoard does. What a troubleshooting video says follows the wiki's Troubleshooting page, in each language.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
from hoard import heap, themes  # noqa: E402

LANGS = ("en", "ja", "ko")
SITE = "hoard.furryup.link"
WIKI = "github.com/Soloflighter1010/Hoard-Asset-Manager/wiki"
SCREEN = (1920, 1080)
_I18N: dict[str, dict] = {}


def W(en: str, ja: str, ko: str) -> dict:
    """Words in each language."""
    return {"en": en, "ja": ja, "ko": ko}


def ui(lang: str, text: str) -> str:
    """One of Hoard's own words (a button's, a theme's name), as Hoard says it in lang."""
    if lang == "en":
        return text
    if lang not in _I18N:
        _I18N[lang] = json.loads((REPO / "hoard" / "web" / "i18n" / f"{lang}.json").read_text("utf-8"))
    return _I18N[lang].get(text, text)


def say(words, lang: str) -> str:
    """Words in lang, with Hoard's own names put in for {Name}: "Choose {Sign in}" becomes "Choose Sign in"."""
    if words is None:
        return ""
    text = words[lang] if isinstance(words, dict) else words
    return re.sub(r"\{([^{}]+)\}", lambda m: f"<b>{ui(lang, m.group(1))}</b>", text)


# ---- the scenes' kinds

def intro(dur, title=None):
    return {"kind": "intro", "dur": dur, "title": title}


def text(dur, title, body=None, kicker=None):
    return {"kind": "text", "dur": dur, "title": title, "body": body, "kicker": kicker}


def outro(dur, title, body=None, url=None):
    return {"kind": "outro", "dur": dur, "title": title, "body": body, "url": url}


def credits(dur):
    return {"kind": "credits", "dur": dur}


def screen(shot, dur, cam=("all", None), rings=(), cursor=None, kicker=None, title=None, body=None, points=()):
    """One of Hoard's screens: the camera moving from one part of it to another (cam: a part's name from
    capture.FOCUS, or "all"), rings round parts ((part, from, until) seconds), the pointer ((seconds, part, click))."""
    return {"kind": "screen", "shot": shot, "dur": dur, "cam": cam, "rings": rings, "cursor": cursor, "kicker": kicker,
            "title": title, "body": body, "points": points}


def dialog(dur, heading, lines=(), link=None, buttons=(), ring=None, look=None, window=None, kicker=None, title=None,
           body=None, points=()):
    """A window drawn in code: the system's warning about a new app, a store's sign-in."""
    return {"kind": "dialog", "dur": dur, "heading": heading, "lines": lines, "link": link, "buttons": buttons,
            "ring": ring, "look": look, "window": window, "kicker": kicker, "title": title, "body": body, "points": points}


def sketch(dur, says=()):
    return {"kind": "sketch", "dur": dur, "says": says}


# ---- the words

TAGLINE = W("Every avatar asset you've bought, in one pile.", "買ったアバターアセットを、ぜんぶひとつの場所に。",
            "구매한 아바타 에셋을 전부 한곳에.")
STORES_LINE = W("Booth, Gumroad, Jinxxy, Payhip and itch.io", "Booth、Gumroad、Jinxxy、Payhip、itch.io",
                "Booth, Gumroad, Jinxxy, Payhip, itch.io")
GET = W("Get Hoard", "Hoardを手に入れる", "Hoard 받기")
FREE = W("Free · Windows, macOS and Linux", "無料 · Windows、macOS、Linux", "무료 · Windows, macOS, Linux")
TROUBLE = W("Troubleshooting", "トラブルシューティング", "문제 해결")
MORE_HELP = outro(4.2, W("More help", "もっと詳しく", "더 알아보기"),
                  W("The wiki's Troubleshooting page", "wikiのトラブルシューティングのページ", "wiki의 문제 해결 페이지"), url=WIKI)
ALL = W("All your stores, one library", "すべてのストアを、ひとつのライブラリに", "모든 스토어를 하나의 라이브러리로")
FIND = W("Find anything, fast", "なんでも、すぐに見つかる", "무엇이든 금방 찾아요")
SIGN_ONCE = W("Sign in once per store", "ストアごとに、サインインは一度だけ", "스토어마다 로그인은 한 번만")
WISH = W("Wishlists, with their prices", "ほしい物リストも、値段つきで", "위시리스트도 가격과 함께")
PROJECTS = W("Your Unity projects, too", "Unityのプロジェクトも", "Unity 프로젝트도")
YOURS = W("Make it yours", "自分好みに", "내 취향대로")
N_THEMES = len(themes.THEMES)


def long_promo():
    """The long promo (#273): every part of Hoard, each explained (about 110 seconds)."""
    return [
        intro(4.0, TAGLINE),
        text(3.6, W("Booth? Gumroad? Jinxxy?<br>Payhip? itch.io?", "Booth?Gumroad?Jinxxy?<br>Payhip?itch.io?",
                    "Booth? Gumroad? Jinxxy?<br>Payhip? itch.io?"),
             W("You bought that hoodie. But where? Hoard answers without opening five tabs.",
               "あのパーカー、どこで買いましたっけ?Hoardなら、タブを5つも開かずに分かります。",
               "그 후드티, 어디서 샀더라? Hoard가 있으면 탭을 다섯 개나 열지 않아도 알 수 있어요.")),
        screen("library", 5.5, ("all", "grid"), [("tabs", 1.0, None)], kicker=W("Library", "ライブラリ", "라이브러리"), title=ALL,
               points=[STORES_LINE, W("Your tags, and the creators' tags", "自分のタグと、クリエイターのタグ", "내 태그와 제작자의 태그"),
                       W("Bought something twice? Hoard finds it", "2回買ったものも見つけます", "두 번 산 것도 찾아내요")]),
        screen("search", 5.0, ("all", "menu"), [("menu", 1.0, None)], kicker=W("Search", "検索", "검색"), title=FIND,
               points=[W("<code>creator:</code>, <code>tag:</code>, <code>type:</code> and more",
                         "<code>creator:</code>、<code>tag:</code>、<code>type:</code>など",
                         "<code>creator:</code>, <code>tag:</code>, <code>type:</code> 등"),
                       W("Search Booth and other sites from the same box", "同じボックスから、Boothなどほかのサイトも検索",
                         "같은 검색창에서 Booth 같은 다른 사이트도 검색")]),
        screen("details", 4.5, ("all", "panel"), kicker=W("Details", "詳細", "자세히"),
               title=W("Everything about a product", "商品のことが、ひと目で", "상품의 모든 것을 한눈에"),
               points=[W("Download it, tag it, archive or hide it", "ダウンロード、タグづけ、アーカイブ、非表示",
                         "다운로드, 태그, 보관, 숨기기")]),
        screen("stores", 5.5, ("all", "win"), [("quick", 1.6, None)], cursor=[(0.6, "quick", False), (2.2, "quick", True)],
               kicker=W("{Stores}", "{Stores}", "{Stores}"), title=SIGN_ONCE,
               points=[W("Refresh reads what you've bought", "更新すると、買ったものを読み込みます", "새로고침하면 산 것을 읽어 와요"),
                       W("{Quick refresh}: just the newest, in seconds", "{Quick refresh}なら、新しいものだけをすぐに",
                         "{Quick refresh}은 새것만 금방"),
                       W("Or import pages you saved", "保存したページの取り込みもできます", "저장한 페이지를 가져올 수도 있어요")]),
        screen("downloads", 5.0, ("all", "grid"), kicker=W("{Downloads}", "{Downloads}", "{Downloads}"),
               title=W("Downloaded, and kept up to date", "ダウンロードして、最新に保つ", "다운로드하고 최신으로 유지"),
               points=[W("Tidy folders: store, creator, product", "ストア/クリエイター/商品の整ったフォルダー",
                         "스토어/제작자/상품으로 정리된 폴더"),
                       W("A creator updates? Hoard gets the new files", "クリエイターが更新したら、新しいファイルを取得",
                         "제작자가 업데이트하면 새 파일을 받아요"),
                       W("The version before is kept", "前のバージョンも残します", "이전 버전도 남겨요")]),
        screen("downloads-details", 4.2, ("all", "panel"), kicker=W("{Downloads}", "{Downloads}", "{Downloads}"),
               title=W("Know where it's used", "どこで使っているか分かる", "어디서 쓰는지 알아요"),
               points=[W("Which of your projects has it", "どのプロジェクトに入っているか", "어느 프로젝트에 들어 있는지"),
                       W("Open its folder, or make an editable copy", "フォルダーを開く、編集用のコピーを作る", "폴더 열기, 편집용 사본 만들기")]),
        screen("space", 4.2, ("all", "grid"), kicker=W("{Disk space}", "{Disk space}", "{Disk space}"),
               title=W("See what takes up room", "何が容量を使っているか", "무엇이 공간을 차지하는지"),
               points=[W("Files kept twice, and ones in no project", "2つあるファイルや、どのプロジェクトにもないもの",
                         "두 번 저장된 파일, 어느 프로젝트에도 없는 것")]),
        screen("inside", 4.8, ("all", "win"), kicker=W("{Look inside}", "{Look inside}", "{Look inside}"),
               title=W("Take only the files you need", "必要なファイルだけを取り出す", "필요한 파일만 꺼내요"),
               points=[W("See inside a .unitypackage before you import it", "インポートする前に.unitypackageの中身を確認",
                         "가져오기 전에 .unitypackage 안을 확인"),
                       W("Your own files too, in {Local}", "自分のファイルも{Local}で", "내 파일도 {Local}에서")]),
        screen("sets", 4.5, ("all", "sets"), [("sets", 1.0, None)], kicker=W("{Sets and Wishlists}", "{Sets and Wishlists}", "{Sets and Wishlists}"),
               title=W("Sets: outfits, kits, worlds", "セット:衣装、キット、ワールド", "세트: 의상, 키트, 월드"),
               points=[W("Keep what goes together, together", "一緒に使うものを、ひとまとめに", "함께 쓰는 것을 한데 모아요")]),
        screen("set", 4.2, ("all", "head"), [("share", 1.0, None)],
               title=W("One link, the whole outfit", "リンクひとつで、衣装まるごと", "링크 하나로 의상 통째로"),
               points=[W("Share a set: your friend sees where to get each part", "セットを共有すると、友だちはそれぞれの入手先が分かります",
                         "세트를 공유하면 친구는 각각 어디서 구하는지 알 수 있어요")]),
        screen("wishlist", 5.0, ("all", "prices"), [("down", 1.4, None)], kicker=W("Wishlists", "ほしい物リスト", "위시리스트"),
               title=WISH,
               points=[W("Read from your stores' own wishlists", "ストアのほしい物リストから読み込み", "스토어의 위시리스트에서 읽어 와요"),
                       W("See when something gets cheaper", "値下がりしたら、すぐ分かる", "가격이 내려가면 바로 알아요")]),
        screen("mix", 4.2, ("all", "win"), kicker=W("{Mix and match}", "{Mix and match}", "{Mix and match}"),
               title=W("An outfit, picked for you", "コーデを、おまかせで", "코디를 알아서 골라 줘요"),
               points=[W("Keep the picks you like, pick the rest again", "気に入ったものは残して、ほかを選び直す",
                         "마음에 드는 건 남기고 나머지는 다시 골라요")]),
        screen("projects", 4.5, ("all", "rows"), kicker=W("{Projects}", "{Projects}", "{Projects}"), title=PROJECTS,
               points=[W("The same list as the Creator Companion and ALCOM", "Creator CompanionやALCOMと同じ一覧",
                         "Creator Companion, ALCOM과 같은 목록"),
                       W("Make one with products from your library", "ライブラリの商品で新しく作れる", "라이브러리의 상품으로 새로 만들어요")]),
        screen("project", 4.5, ("all", "subs"),
               title=W("Packages, backups, your products", "パッケージ、バックアップ、自分の商品", "패키지, 백업, 내 상품"),
               points=[W("Update VRChat's packages", "VRChatのパッケージを更新", "VRChat 패키지 업데이트"),
                       W("Add products straight from your library", "ライブラリから商品をそのまま追加", "라이브러리에서 상품을 바로 추가")]),
        screen("project-git", 4.5, ("all", "git"), kicker=W("{Source control}", "{Source control}", "{Source control}"),
               title=W("Git, built in", "Gitも組み込み", "Git도 내장"),
               points=[W("Stage, commit, and see the history", "ステージ、コミット、履歴の確認", "스테이지, 커밋, 기록 보기"),
                       W("Sync with GitHub, GitLab, Gitea or your own", "GitHub、GitLab、Gitea、自分のサーバーと同期",
                         "GitHub, GitLab, Gitea, 내 서버와 동기화")]),
        text(3.8, W("Your library, inside Unity", "ライブラリを、Unityの中に", "라이브러리를 Unity 안에서"),
             W("Hoard for Unity imports products and sets, with their credits.", "Hoard for Unityで、商品やセットをクレジットつきでインポート。",
               "Hoard for Unity로 상품과 세트를 크레디트와 함께 가져와요."),
             W("Hoard for Unity", "Hoard for Unity", "Hoard for Unity")),
        screen("tasks", 4.0, ("all", "win"), kicker=W("{Tasks}", "{Tasks}", "{Tasks}"),
               title=W("Everything Hoard does, in one place", "Hoardがしていることを、ひとつの場所で", "Hoard가 하는 일을 한곳에서"),
               points=[W("What's running, what's waiting, what's done", "実行中、待機中、完了", "실행 중, 대기 중, 완료")]),
        screen("settings-apprise", 4.5, ("all", "list"), kicker=W("Notifications", "通知", "알림"),
               title=W("News, where you are", "知らせを、いつもの場所に", "소식을 늘 쓰는 곳으로"),
               points=[W("Discord, Telegram, ntfy, email and more", "Discord、Telegram、ntfy、メールなど", "Discord, Telegram, ntfy, 이메일 등"),
                       W("New products, updates, prices that drop", "新しい商品、更新、値下がり", "새 상품, 업데이트, 가격 인하")]),
        screen("hidden", 3.8, ("all", "pin"), kicker=W("{Hidden}", "{Hidden}", "{Hidden}"),
               title=W("Some things, just for you", "自分だけのものも", "나만 보는 것도"),
               points=[W("Hide items behind a PIN", "PINで非表示に", "PIN 뒤에 숨겨요")]),
        screen("settings-look", 5.5, ("all", "themes"), [("themes", 1.0, 3.2), ("styles", 3.2, None)],
               kicker=W("{Appearance}", "{Appearance}", "{Appearance}"), title=YOURS,
               points=[W(f"{N_THEMES} themes, in light and dark", f"{N_THEMES}のテーマ、ライトとダーク", f"테마 {N_THEMES}개, 라이트와 다크"),
                       W("Three styles: {Standard}, {Treasure}, {Workbench}", "3つのスタイル:{Standard}、{Treasure}、{Workbench}",
                         "스타일 3가지: {Standard}, {Treasure}, {Workbench}"),
                       W("Text size, spacing, less motion", "文字の大きさ、間隔、動きを減らす", "글자 크기, 간격, 움직임 줄이기")]),
        text(3.8, W("Free, and open source", "無料で、オープンソース", "무료, 오픈 소스"),
             W("Windows, macOS and Linux. In English, Japanese and Korean.", "Windows、macOS、Linux。英語、日本語、韓国語で。",
               "Windows, macOS, Linux. 영어, 일본어, 한국어로.")),
        outro(5.5, GET, FREE),
        credits(6.0),
    ]


def short_promo():
    """The short promo (#273): the best of it (about 32 seconds)."""
    return [
        intro(3.2, TAGLINE),
        screen("library", 3.8, ("all", "grid"), [("tabs", 0.8, None)], title=ALL, points=[STORES_LINE]),
        screen("search", 3.5, ("all", "menu"), title=FIND,
               points=[W("Search everything at once", "ぜんぶまとめて検索", "전부 한꺼번에 검색")]),
        screen("stores", 3.5, ("all", "win"), [("quick", 0.9, None)], title=SIGN_ONCE,
               points=[W("Downloaded, and kept up to date", "ダウンロードして、最新に保つ", "다운로드하고 최신으로 유지")]),
        screen("wishlist", 3.5, ("all", "prices"), [("down", 0.9, None)], title=WISH,
               points=[W("Sets you can share, too", "共有できるセットも", "공유할 수 있는 세트도")]),
        screen("projects", 3.5, ("all", "rows"), title=PROJECTS,
               points=[W("With Git, and Hoard for Unity", "Gitも、Hoard for Unityも", "Git도, Hoard for Unity도")]),
        screen("settings-look", 3.5, ("all", "themes"), [("themes", 0.9, None)], title=YOURS,
               points=[W(f"{N_THEMES} themes, three styles", f"{N_THEMES}のテーマ、3つのスタイル", f"테마 {N_THEMES}개, 스타일 3가지")]),
        outro(4.0, GET, FREE),
        credits(3.5),
    ]


def trouble(title, *middle):
    """A troubleshooting video (#274): the problem, the steps, and where there's more."""
    return [text(3.0, title, kicker=TROUBLE), *middle, MORE_HELP]


TROUBLESHOOTING = {
    "windows": lambda: trouble(
        W("“Windows protected your PC”", "「WindowsによってPCが保護されました」", "“Windows의 PC 보호”"),
        dialog(5.5, W("Windows protected your PC", "WindowsによってPCが保護されました", "Windows의 PC 보호"),
               [W("Windows doesn't know this app's publisher well yet.", "Windowsはまだ、このアプリの発行元をよく知りません。",
                  "Windows가 아직 이 앱의 게시자를 잘 몰라요.")],
               link=W("More info", "詳細情報", "추가 정보"), buttons=[{"text": W("Don't run", "実行しない", "실행 안 함")}],
               ring="link", look="warn",
               title=W("Choose More info", "「詳細情報」を選ぶ", "'추가 정보'를 고르세요"),
               body=W("Hoard is code-signed: its maintainer shows as the publisher.",
                      "Hoardにはコード署名があり、発行元としてHoardのメンテナーが表示されます。",
                      "Hoard는 코드 서명이 되어 있어서 게시자로 Hoard의 관리자가 보여요.")),
        dialog(5.5, W("Windows protected your PC", "WindowsによってPCが保護されました", "Windows의 PC 보호"),
               [W("App: Hoard's installer", "アプリ:Hoardのインストーラー", "앱: Hoard 설치 프로그램"),
                W("Publisher: Hoard's maintainer", "発行元:Hoardのメンテナー", "게시자: Hoard의 관리자")],
               buttons=[{"text": W("Run anyway", "実行", "실행"), "main": True}, {"text": W("Don't run", "実行しない", "실행 안 함")}],
               ring=0, look="warn",
               title=W("Then Run anyway", "「実行」を選ぶ", "'실행'을 고르세요"),
               body=W("The warning fades as more people install Hoard's releases. To check the file first, see Installing Hoard in the wiki.",
                      "リリースをインストールする人が増えるにつれて、この警告は出なくなります。先にファイルを確かめるには、wikiの「Hoardのインストール」をご覧ください。",
                      "릴리스를 설치하는 사람이 늘수록 이 경고는 사라져요. 먼저 파일을 확인하려면 wiki의 'Hoard 설치'를 보세요.")),
        text(5.0, W("Security software stops Hoard?", "セキュリティソフトがHoardを止める?", "보안 프로그램이 Hoard를 막나요?"),
             W("Allow Hoard, and the browser it installs, or report a false positive to the software's maker. Every release is scanned by VirusTotal before it's published.",
               "Hoardと、Hoardがインストールするブラウザーを許可するか、誤検知としてソフトの作者に報告してください。すべてのリリースは公開前にVirusTotalでスキャンされます。",
               "Hoard와 Hoard가 설치하는 브라우저를 허용하거나, 오탐지로 프로그램 제작사에 알려 주세요. 모든 릴리스는 공개하기 전에 VirusTotal로 검사해요."),
             W("Antivirus", "セキュリティソフト", "보안 프로그램"))),
    "sign-in": lambda: trouble(
        W("Signing in with Google, Discord or X", "Google、Discord、Xでサインイン", "Google, Discord, X로 로그인"),
        dialog(6.0, W("Sign in to the store", "ストアにサインイン", "스토어에 로그인"),
               [W("Continue with Google", "Googleで続ける", "Google로 계속"), W("Continue with Discord", "Discordで続ける", "Discord로 계속"),
                W("Continue with X", "Xで続ける", "X로 계속")],
               buttons=[{"text": W("Sign in", "サインイン", "로그인"), "main": True}],
               window=W("Hoard: Sign in", "Hoard:サインイン", "Hoard: 로그인"),
               title=W("They work in Hoard's window", "Hoardのウィンドウで使えます", "Hoard 창에서 돼요"),
               body=W("The sign-in window is the browser's own, which Google and the others accept.",
                      "サインインのウィンドウはブラウザー自体のもので、Googleなども受け付けます。",
                      "로그인 창은 브라우저 자체의 창이라 Google 등이 받아들여요.")),
        text(5.5, W("Use a password instead", "代わりにパスワードで", "대신 비밀번호로"),
             W("Set a password for your store account in your usual browser, then sign in with it in Hoard's window.",
               "ふだんのブラウザーでストアのアカウントにパスワードを設定してから、Hoardのウィンドウでそのパスワードでサインインしてください。",
               "평소 쓰는 브라우저에서 스토어 계정에 비밀번호를 설정한 다음, Hoard 창에서 그 비밀번호로 로그인하세요."),
             W("Still refused?", "それでも拒否される?", "그래도 거부되나요?"))),
    "booth-sign-in": lambda: trouble(
        W("“Not signed in to Booth”", "「Boothにサインインしていません」", "“Booth에 로그인하지 않았어요”"),
        screen("t-booth", 7.0, ("all", "row"), [("note", 0.9, 3.4), ("signin", 3.4, None)], cursor=[(2.6, "signin", False), (4.0, "signin", True)],
               title=W("Sign in again", "もう一度サインイン", "다시 로그인"),
               points=[W("Stores end sign-ins from time to time", "ストアはときどきサインインを終わらせます", "스토어는 가끔 로그인을 끝내요"),
                       W("In {Stores}, choose {Sign in} on that store", "{Stores}で、そのストアの{Sign in}を選ぶ",
                         "{Stores}에서 그 스토어의 {Sign in}을 고르세요"),
                       W("Close the browser window when you're done", "終わったら、ブラウザーのウィンドウを閉じる", "끝나면 브라우저 창을 닫으세요")])),
    "payhip-check": lambda: trouble(
        W("Payhip keeps showing a bot check", "Payhipがボットのチェックを何度も表示する", "Payhip이 봇 확인을 계속 보여 줘요"),
        screen("t-payhip", 8.0, ("all", "row"), [("note", 0.9, 4.2), ("import", 4.2, None)],
               title=W("Finish it, or import instead", "チェックを済ませるか、取り込む", "확인을 마치거나 가져오세요"),
               points=[W("Complete the check in Payhip's window: Hoard waits up to 3 minutes",
                         "Payhipのウィンドウでチェックを済ませると、Hoardが続けます(最大3分)",
                         "Payhip 창에서 확인을 마치면 Hoard가 이어서 해요(최대 3분)"),
                       W("Still kept out? Save each shop's library page in your usual browser", "それでもだめなら、ふだんのブラウザーで各ショップのライブラリページを保存",
                         "그래도 안 되면 평소 쓰는 브라우저에서 상점마다 라이브러리 페이지를 저장"),
                       W("Then choose {Import pages}", "それから{Import pages}を選ぶ", "그런 다음 {Import pages}를 고르세요")])),
    "itch-key": lambda: trouble(
        W("itch.io's API key", "itch.ioのAPIキー", "itch.io의 API 키"),
        screen("t-itch", 8.0, ("all", "dialog"), [("key", 1.0, 4.4), ("save", 4.4, None)],
               title=W("Make a key on itch.io", "itch.ioでキーを作る", "itch.io에서 키 만들기"),
               points=[W("On itch.io: Settings, then API keys", "itch.ioで:Settings、API keys", "itch.io에서: Settings, API keys"),
                       W("Generate a new key, and copy it", "新しいキーを作って、コピー", "새 키를 만들어 복사"),
                       W("Paste it here, and choose {Save key}", "ここに貼り付けて、{Save key}を選ぶ", "여기에 붙여 넣고 {Save key}를 고르세요"),
                       W("Not accepted? It was cut short, or deleted: make a new one", "受け付けられない?途中で切れたか削除されています。新しく作りましょう",
                         "받아들이지 않나요? 잘렸거나 지워졌어요. 새로 만드세요")])),
    "download-fails": lambda: trouble(
        W("A download keeps failing", "ダウンロードが何度も失敗する", "다운로드가 계속 실패해요"),
        screen("t-failed", 7.5, ("all", "body"), [("body", 1.0, None)],
               title=W("The summary says why", "理由は、まとめに出ます", "이유는 요약에 나와요"),
               points=[W("Every failed or skipped file, with its reason", "失敗したりスキップしたりしたものすべてに、その理由",
                         "실패하거나 건너뛴 모든 것과 그 이유"),
                       W("Gumroad's “no download page”: a refund, or a membership that ended", "Gumroadの「no download page」:返金か、終了したメンバーシップ",
                         "Gumroad의 “no download page”: 환불이나 끝난 멤버십"),
                       W("Stopped part way? The next sync picks up where it stopped", "途中で止まった?次の同期で続きから再開します",
                         "중간에 멈췄나요? 다음 동기화가 멈춘 곳부터 이어 받아요")])),
    "notifications": lambda: trouble(
        W("Notifications don't arrive", "Appriseでの通知が届かない", "Apprise 알림이 오지 않아요"),
        screen("t-apprise", 7.5, ("all", "list"), [("list", 1.0, None)],
               title=W("Send a test", "テストを送る", "테스트 보내기"),
               points=[W("Choose {Send a test} in {Settings}", "{Settings}で{Send a test}を選ぶ", "{Settings}에서 {Send a test}를 고르세요"),
                       W("401: a wrong token. 404: an address that isn't there", "401はトークンの誤り、404は存在しないアドレス",
                         "401은 잘못된 토큰, 404는 없는 주소"),
                       W("Check the address against the service's page in Apprise's documentation", "Appriseのドキュメントで、そのサービスのページとアドレスを見比べる",
                         "Apprise 문서의 그 서비스 페이지와 주소를 비교하세요")])),
    "page-not-recognised": lambda: trouble(
        W("“Hoard didn't recognise this page”", "「Hoardがこのページを認識できませんでした」", "“Hoard가 이 페이지를 알아보지 못했어요”"),
        screen("t-key", 7.0, ("all", None),
               title=W("Open Hoard again", "Hoardをもう一度開く", "Hoard를 다시 여세요"),
               points=[W("The page doesn't have this run's access key", "そのページに、今回の起動のアクセスキーがありません",
                         "그 페이지에 이번 실행의 접근 키가 없어요"),
                       W("An old bookmark, or an address from before Hoard restarted", "古いブックマークや、Hoardの再起動前のアドレス",
                         "오래된 북마크나, Hoard를 다시 시작하기 전의 주소"),
                       W("Open Hoard from the Start menu: its window comes to the front", "スタートメニューからHoardを開くと、ウィンドウが前面に出ます",
                         "시작 메뉴에서 Hoard를 열면 창이 앞으로 나와요")])),
    "pin": lambda: trouble(
        W("Forgot the hidden library's PIN?", "非表示のライブラリのPINを忘れた?", "숨긴 라이브러리의 PIN을 잊었나요?"),
        screen("t-pin", 7.0, ("all", "pin"), [("forgot", 1.0, None)], cursor=[(1.8, "forgot", False), (3.2, "forgot", True)],
               title=W("Use your recovery words", "復元ワードを使う", "복구 단어를 쓰세요"),
               points=[W("Choose {Forgot your PIN?}", "{Forgot your PIN?}を選ぶ", "{Forgot your PIN?}를 고르세요"),
                       W("Enter your 6 recovery words, and set a new PIN", "6つの復元ワードを入力して、新しいPINを設定",
                         "복구 단어 6개를 입력하고 새 PIN을 정하세요"),
                       W("Nothing is lost", "何も失われません", "잃는 건 없어요")])),
}


def sketch_video():
    """The sketch's mockup (#289): over someone's shoulder, every store in a tab of its own; then Hoard."""
    return [
        sketch(9.0, says=[(1.2, W("I need that hoodie to finish my avatar…", "アバターを仕上げるのに、あのパーカーが要るんだけど…",
                                  "아바타를 마무리하려면 그 후드티가 필요한데…")),
                          (4.6, W("Which store was it on?!", "どのストアで買ったっけ?!", "어느 스토어에서 샀더라?!"))]),
        text(3.6, W("Can't find the asset to finish your project?", "プロジェクトを仕上げるアセットが、見つからない?",
                    "프로젝트를 마무리할 에셋을 못 찾겠나요?"),
             W("Five stores. Five libraries. Five tabs.", "5つのストア。5つのライブラリ。5つのタブ。", "스토어 다섯 개. 라이브러리 다섯 개. 탭 다섯 개.")),
        intro(3.8, W("Every store, in one place.", "すべてのストアを、ひとつの場所に。", "모든 스토어를 한곳에.")),
        screen("library", 4.8, ("all", "grid"), [("tabs", 0.9, None)], title=ALL, points=[STORES_LINE]),
        screen("search-hoodie", 5.5, ("all", "grid"), [("box", 0.8, 2.6), ("grid", 2.6, None)],
               title=W("Searched all at once", "まとめて検索", "한꺼번에 검색"),
               points=[W("“hoodie”: Booth and Gumroad, together", "「hoodie」:BoothもGumroadも、一度に", "“hoodie”: Booth와 Gumroad를 함께")]),
        outro(5.0, GET, FREE),
        credits(4.0),
    ]


# every video: (name, scenes, layouts, languages)
def videos():
    out = [("promo-long", long_promo, ("landscape", "portrait"), LANGS),
           ("promo-short", short_promo, ("landscape", "portrait"), LANGS)]
    out += [(f"troubleshooting-{k}", f, ("landscape",), LANGS) for k, f in TROUBLESHOOTING.items()]
    out += [("sketch-mockup", sketch_video, ("landscape",), ("en",))]
    return out


# ---- the posters' words (#292)

POSTERS = [
    {"name": "poster", "shot": "library", "title": TAGLINE,
     "body": W("Booth, Gumroad, Jinxxy, Payhip and itch.io, in a single library you can search, filter and keep.",
               "Booth、Gumroad、Jinxxy、Payhip、itch.ioで買ったものを、検索・絞り込み・保管ができるひとつのライブラリに。",
               "Booth, Gumroad, Jinxxy, Payhip, itch.io에서 산 것을 검색하고, 거르고, 보관할 수 있는 하나의 라이브러리로."),
     "points": [W("Downloaded, and kept up to date", "ダウンロードして、最新に保つ", "다운로드하고 최신으로 유지"),
                W("Sets, and wishlists with their prices", "セットと、値段つきのほしい物リスト", "세트, 가격이 보이는 위시리스트"),
                W("Your Unity projects, with Git", "Unityのプロジェクトも、Gitで", "Unity 프로젝트도 Git으로")]},
]


# ---- what the player is given

def _box(boxes: dict, name, pad: int = 40):
    """A part's place on the screen, a little bigger, or the whole screen."""
    if name in (None, "all") or name not in boxes:
        return [0, 0, *SCREEN]
    x, y, w, h = boxes[name]
    return [x - pad, y - pad, w + 2 * pad, h + 2 * pad]


def _fit(r, aspect: float):
    """A rectangle grown to the window's shape (and no bigger than the screen, and on it)."""
    x, y, w, h = r
    cx, cy = x + w / 2, y + h / 2
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    k = min(1.0, SCREEN[0] / w, SCREEN[1] / h)
    w, h = w * k, h * k
    x = min(max(0, cx - w / 2), SCREEN[0] - w)
    y = min(max(0, cy - h / 2), SCREEN[1] - h)
    return [round(x), round(y), round(w), round(h)]


def _chip(rec: dict, lang: str) -> dict:
    """The lower third: the theme (and style) a screen is in, with its colours."""
    t = themes.THEMES[rec["theme"]]
    colours = t[rec["mode"]]
    extra = ui(lang, "Dark" if rec["mode"] == "dark" else "Light")
    if rec.get("style", "standard") != "standard":
        extra += " · " + ui(lang, "Style") + " " + ui(lang, rec["style"].title())
    return {"label": ui(lang, "Theme"), "name": ui(lang, t["name"]), "extra": extra,
            "swatches": [colours["cave"], colours["ledge"], colours["gold"], colours["bone"]],
            "glows": [colours["gold"], colours["gumroad"], colours["jinxxy"], colours["payhip"]]}


def wipe_boxes() -> list[str]:
    """The boxes that tumble past between scenes: each one the Heap's own box, drawn as the logo draws it (its outline
    as thick, its corners as round, the cube on the Projects box and the sparkle on the gold one)."""
    out = []
    for box in (*heap.ORDER, "gold"):
        side = heap.GOLD_BOX if box == "gold" else heap.BOX
        half = side / 2 + heap.LINE / 2
        fill = heap.GOLD if box == "gold" else heap.COLOURS[box]
        extra = ""
        if box == "gold":
            extra = f'<path d="{heap._sparkle(side)}" fill="{heap.SPARK}"/>'
        elif box == "projects":
            extra = (f'<path d="{heap._cube(side)}" fill="none" stroke="{heap.CAVE}" stroke-width="1.5" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-half:g} {-half:g} {2 * half:g} {2 * half:g}">'
                   f'<rect x="{-side / 2:g}" y="{-side / 2:g}" width="{side:g}" height="{side:g}" rx="{heap.ROUND:g}" fill="{fill}" '
                   f'stroke="{heap.CAVE}" stroke-width="{heap.LINE:g}"/>{extra}</svg>')
    return out


def _wordmark() -> str:
    """The word "hoard", light, on its own."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="72 0 154 64"><g fill="#F2EDE4">{heap.word()}</g></svg>'


def credit_names(library: Path) -> list[str]:
    """The creators of the products shown: the products' own (not the made-up ones promo/art.py draws)."""
    sys.path.insert(0, str(HERE))
    import art
    made_up = {p[1] for p in art.PRODUCTS}
    items = json.loads((library / "products.json").read_text("utf-8"))
    names = {i["creator"].strip() for i in items if i.get("creator") and i["creator"].strip() not in made_up}
    return sorted(names, key=str.casefold)


CREDITS = W("Products shown, by", "映っている商品のクリエイター", "화면에 나온 상품의 제작자")
CREDITS_NOTE = W("Thank you to their creators. Products not listed here were made up for this video, drawn in code.",
                 "クリエイターのみなさんに感謝します。ここにない商品は、この動画のためにコードで描いた架空のものです。",
                 "제작자 여러분께 감사드려요. 여기에 없는 상품은 이 영상을 위해 코드로 그린 가상의 상품이에요.")


def build(scenes, lang: str, layout: str, screens: Path, library: Path) -> dict:
    """A video as player.html's load() takes it."""
    shots = json.loads((screens / "shots.json").read_text("utf-8"))
    w, h = (1920, 1080) if layout == "landscape" else (1080, 1920)
    aspect = 1180 / 664 if layout == "landscape" else 1.0
    out = []
    for s in scenes:
        d = {"kind": s["kind"], "dur": s["dur"]}
        for k in ("title", "body", "kicker"):
            if s.get(k):
                d[k] = say(s[k], lang)
        if s.get("points"):
            d["points"] = [say(p, lang) for p in s["points"]]
        if s["kind"] == "screen":
            rec = shots[s["shot"]]
            boxes = rec["boxes"].get(lang) or rec["boxes"]["en"]
            d["shot"] = s["shot"]
            d["src"] = (screens / f"{s['shot']}-{lang}.png").resolve().as_uri()
            a, b = s["cam"]
            d["from"] = _fit(_box(boxes, a), aspect)
            d["to"] = _fit(_box(boxes, b if b else a, 60), aspect)
            d["rings"] = [{"box": boxes[n], "at": at, "end": end} for n, at, end in s["rings"] if n in boxes]
            if s.get("cursor"):
                pts = []
                for t, n, click in s["cursor"]:
                    if n not in boxes:
                        continue
                    x, y, bw, bh = boxes[n]
                    cx, cy = x + bw / 2, y + bh / 2
                    if not pts:   # (in from below and to the right)
                        pts.append([0, min(SCREEN[0] - 40, cx + 260), min(SCREEN[1] - 40, cy + 200), False])
                    pts.append([t, cx, cy, click])
                d["cursor"] = pts or None
            d["chip"] = None if s["shot"].startswith("t-") else _chip(rec, lang)   # (troubleshooting: Hoard's own look)
            d["flat"] = layout == "portrait"
        elif s["kind"] == "dialog":
            d.update({"heading": say(s["heading"], lang), "lines": [say(x, lang) for x in s["lines"]],
                      "link": say(s["link"], lang) if s.get("link") else None,
                      "buttons": [{"text": say(b["text"], lang), "main": b.get("main", False)} for b in s["buttons"]],
                      "ring": s["ring"], "look": s["look"], "window": say(s["window"], lang) if s.get("window") else "",
                      "title2": d.pop("title", ""), "body2": d.pop("body", "")})
        elif s["kind"] == "sketch":
            d["says"] = [[at, say(x, lang)] for at, x in s["says"]]
            items = json.loads((library / "products.json").read_text("utf-8"))
            tabs = []
            for store, name, colour in (("booth", "BOOTH · Library", "#FF6259"), ("gumroad", "Gumroad · Library", "#FF8AD8"),
                                        ("jinxxy", "Jinxxy · My Products", "#56D1DC"), ("payhip", "Payhip · Purchases", "#95A0FF"),
                                        ("itch", "itch.io · My Library", "#7ED67A")):
                pics = [(library / i["image"]).resolve().as_uri() for i in items if i["store"] == store]
                while pics and len(pics) < 15:
                    pics = pics + pics
                tabs.append({"name": name, "colour": colour, "pics": pics[:15]})
            d["tabs"] = tabs
        elif s["kind"] == "outro":
            d["url"] = s.get("url") or SITE
        elif s["kind"] == "credits":
            d["title"] = say(CREDITS, lang)
            d["names"] = credit_names(library)
            d["body"] = say(CREDITS_NOTE, lang)
        out.append(d)
    return {"lang": lang, "w": w, "h": h, "shots": out, "logo": heap.logo(), "mark": heap.mark(), "word": _wordmark(),
            "wipes": wipe_boxes()}


def build_poster(poster: dict, lang: str, layout: str, screens: Path) -> dict:
    """A poster, as a one-frame video."""
    w, h = (1920, 1080) if layout == "landscape" else (1080, 1920)
    shot = {"kind": "poster", "dur": 1, "title": say(poster["title"], lang), "body": say(poster["body"], lang),
            "points": [say(p, lang) for p in poster["points"]], "src": (screens / f"{poster['shot']}-{lang}.png").resolve().as_uri(),
            "url": SITE, "small": say(FREE, lang)}
    return {"lang": lang, "w": w, "h": h, "shots": [shot], "logo": heap.logo(), "mark": heap.mark(), "word": _wordmark(),
            "wipes": []}


def total(scenes) -> float:
    """How long a video is, in seconds."""
    return sum(s["dur"] for s in scenes)


if __name__ == "__main__":
    for name, scenes, layouts, langs in videos():
        print(f"{name}: {total(scenes()):.1f} s, {', '.join(layouts)}, {', '.join(langs)}")
