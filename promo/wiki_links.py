"""Links each troubleshooting video from the wiki section that explains its problem, in English, Japanese and Korean,
and the Windows one from the FAQ's antivirus answer too. Run it once the videos are on the media release (their
addresses 404 until then):

    python3 promo/wiki_links.py

A link that's there already is left as it is, so it can run again. Standard library only (and scenes.py, for each
video's length).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import scenes  # noqa: E402

BASE = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/media/"
# each page, and the heading of each section a video goes under: by the video's key in scenes.TROUBLESHOOTING
SECTIONS = {
    "en": ("wiki/Troubleshooting.md", {
        '### "Windows protected your PC"': "windows", "### Security software stops Hoard, or its browser": "windows",
        "### Signing in with Google, Discord or X doesn't work": "sign-in",
        '### "Not signed in to Booth", or "session expired"': "booth-sign-in",
        "### Payhip keeps showing a bot check": "payhip-check", '### itch.io: "didn\'t accept the API key"': "itch-key",
        "### A download keeps failing, or is skipped": "download-fails",
        "### Notifications through Apprise don't arrive": "notifications",
        '### "Hoard didn\'t recognise this page"': "page-not-recognised", "## The hidden library": "pin"}),
    "ja": ("wiki/ja/トラブルシューティング.md", {
        "### 「WindowsによってPCが保護されました」": "windows", "### セキュリティソフトがHoardやそのブラウザーを止める": "windows",
        "### Google、Discord、Xでサインインできない": "sign-in", "### 「Boothにサインインしていません」、「セッションが切れました」": "booth-sign-in",
        "### Payhipがボットのチェックを何度も表示する": "payhip-check", "### itch.io:「itch.ioがAPIキーを受け付けませんでした」": "itch-key",
        "### ダウンロードが何度も失敗する、またはスキップされる": "download-fails", "### Appriseでの通知が届かない": "notifications",
        "### 「Hoardがこのページを認識できませんでした」": "page-not-recognised", "## 非表示のライブラリ": "pin"}),
    "ko": ("wiki/ko/문제-해결.md", {
        '### "Windows의 PC 보호"': "windows", "### 보안 프로그램이 Hoard나 그 브라우저를 막아요": "windows",
        "### Google, Discord, X로 로그인이 안 돼요": "sign-in", '### "Booth에 로그인하지 않았어요", "세션이 만료됐어요"': "booth-sign-in",
        "### Payhip이 봇 확인을 계속 보여 줘요": "payhip-check", '### itch.io: "itch.io가 API 키를 받아들이지 않았어요"': "itch-key",
        "### 다운로드가 계속 실패하거나 건너뛰어져요": "download-fails", "### Apprise 알림이 오지 않아요": "notifications",
        '### "Hoard가 이 페이지를 알아보지 못했어요"': "page-not-recognised", "## 숨긴 라이브러리": "pin"}),
}
FAQ = {"en": ("wiki/FAQ.md", "## Why does my antivirus or Windows warn about Hoard?"),
       "ja": ("wiki/ja/よくある質問.md", "## アンチウイルスやWindowsがHoardについて警告するのはなぜですか?"),
       "ko": ("wiki/ko/자주-묻는-질문.md", "## 백신이나 Windows가 Hoard에 대해 경고하는 이유는 뭔가요?")}


def url(key: str, lang: str) -> str:
    """Where a troubleshooting video is, on the media release."""
    return f"{BASE}troubleshooting-{key}-{lang}.mp4"


def line(key: str, lang: str) -> str:
    """The wiki's line linking a video, with how long it is."""
    secs = round(scenes.total(scenes.TROUBLESHOOTING[key]()))
    return {"en": f"**Video:** [the steps, in {secs} seconds]({url(key, lang)})",
            "ja": f"**動画:**[手順を{secs}秒で見る]({url(key, lang)})",
            "ko": f"**영상:** [{secs}초 만에 보는 단계]({url(key, lang)})"}[lang]


def insert(text: str, heading: str, link: str) -> str:
    """The page with link at the end of the section under heading (once: left alone if the page has that address)."""
    lines = text.split("\n")
    i = next(k for k, s in enumerate(lines) if s.strip() == heading)
    if any(link.split("](")[1] in s for s in lines):
        return text
    j = i + 1
    while j < len(lines) and not lines[j].startswith("#"):
        j += 1
    while lines[j - 1].strip() == "":   # (after the section's last paragraph)
        j -= 1
    lines[j:j] = ["", link]
    return "\n".join(lines)


def main() -> int:
    """Link every video from its sections, each page written once."""
    pages = {}
    for lang, (path, secs) in SECTIONS.items():
        for heading, key in secs.items():
            pages[path] = insert(pages.get(path) or (REPO / path).read_text("utf-8"), heading, line(key, lang))
    for lang, (path, heading) in FAQ.items():
        pages[path] = insert(pages.get(path) or (REPO / path).read_text("utf-8"), heading, line("windows", lang))
    for path, text in pages.items():
        (REPO / path).write_text(text, "utf-8")
    print("Each video is linked. Mark the translations as up to date: python3 scripts/wiki_translations.py --done "
          "ja Troubleshooting (and ja FAQ, ko Troubleshooting, ko FAQ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
