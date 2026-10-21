<!-- Translated from Where-Hoard-Keeps-Things (English cfbec4adc8e9). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Where-Hoard-Keeps-Things">English</a> · <a href="Hoardの保存場所">日本語</a> · <b>한국어</b> · AI의 도움을 받아 영어판에서 번역한 페이지예요. 영어판과 내용이 다르면 영어판이 맞는 정보예요. 이상한 번역을 찾으면 <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">번역 수정</a>으로 알려 주세요.</sub></p>

Hoard가 보관하는 것은 두 가지로 나뉘어요. 내가 고른 폴더에 있는 다운로드와, 그 밖의 모든 것을 담은 내 사용자 계정 전용의 비공개 앱 데이터 폴더예요.

## Hoard의 앱 데이터 폴더

| Windows | macOS | Linux |
|---|---|---|
| `%LOCALAPPDATA%\Hoard` | `~/Library/Application Support/Hoard` | `~/.local/share/Hoard` |

Linux Flatpak도 `~/.local/share/Hoard`를 써요(`~/.var/app` 아래의 자기 폴더가 아니에요). 그래서 소스로 실행하는 Hoard와 라이브러리를 같이 쓰고, Hoard for Unity도 찾을 수 있어요. Flatpak만의 것은 Hoard 브라우저의 사본(`~/.var/app/io.github.soloflighter1010.Hoard/cache`)뿐이에요.

| 무엇 | 무엇을 위한 것인지 |
|---|---|
| `sign-ins/` | 스토어 로그인. 스토어마다 폴더 하나이고, 운영체제가 암호화해요. 이 폴더는 절대 공유하지 마세요 |
| `config.json` | 설정. [설정](설정)을 보세요 |
| `library.json` | 라이브러리 목록. 가진 것의 이름, 제작자, 링크, 이미지 주소 |
| `keys/` | Windows에서는 Windows 계정으로 암호화한 itch.io API 키. (Mac에서는 키체인, Linux에서는 키링에 있어요.) [스토어](스토어#itchio)를 보세요 |
| `tags.json` | 내 태그 |
| `picture-looks.json` | 상품 이미지가 어떻게 보이는지(이미지의 SHA-256마다 64비트 해시). 두 스토어가 다르게 저장한 한 상품의 사본을 묶기 위해서예요. [라이브러리](라이브러리#찾기)를 보세요 |
| `asset-updates.json` | 지난번 **업데이트 확인**에서 찾은 것. 다운로드한 것마다, 스토어에 있는데 아직 내게 없는 파일. [다운로드](다운로드#다운로드하지-않고-업데이트-확인하기)를 보세요 |
| `marks.json` | 보관, 숨기기, 삭제한 것, 그리고 숨긴 라이브러리의 PIN과 복구 단어(둘 다 솔트를 친, 시간이 오래 걸리는 해시로만) |
| `projects/` | Hoard 창을 연 Unity 프로젝트마다 작은 보고서(Hoard for Unity 0.4.0 이상). 이름과 폴더, 쓰는 에셋, 크레딧 설정. Hoard의 **프로젝트**에 나오고, **이 프로젝트 잊기**로 하나를 지워요. [Hoard for Unity 사용법](Hoard-for-Unity-사용법#hoard의-프로젝트)을 보세요 |
| `library_folders.json` | 다른 라이브러리 폴더마다, Hoard가 마지막으로 읽었을 때 어떤 상품이 있었는지. 그 드라이브가 연결되지 않은 동안 동기화가 건드리지 않게 하려는 거예요. [다운로드](다운로드#다른-드라이브의-라이브러리-폴더)를 보세요 |
| `integrity.key` | Hoard가 기록을 봉인하는 키([봉인](#봉인)을 보세요). 내 계정만의 것이에요 |
| `sealed-files.json` | 이 설치가 봉인한 기록. 봉인이 없어지면 알아채기 위해서예요 |
| `cache/thumbs/` | 상품 이미지. 오프라인에서도 라이브러리를 쓸 수 있게 저장해요 |
| `cache/inside/` | **내용 보기**가 패키지나 zip에서 읽은 것과 미리보기. 최근에 내용을 본 40개분이에요(4.0). [다운로드](다운로드#다운로드-보기)를 보세요 |
| `sets.json` | 세트. 이름, 메모, 사진 링크, 세트마다 상품(태그와 같은 키로)과 각각이 무엇인지(4.0, 4.2.0). 짧은 링크를 만들었다면 그 키와, Hoard가 그걸 업데이트하거나 지울 수 있게 해 주는 토큰(4.3.0). 그리고 위시리스트와, 상품마다 마지막으로 읽었을 때의 가격, 바뀌었다면 그 전 가격(4.4.0). [세트](세트#위시리스트)를 보세요 |
| `set-pictures/` | 세트 타일에 쓰려고 고른 이미지(4.2.0). 백업에는 들어가지 않아요. [세트](세트#세트-이미지)를 보세요 |
| `local-pictures/` | 내 패키지 타일에 쓰려고 고른 이미지. Hoard가 그 옆에도 복사해요(4.2.0). [내 패키지](내-패키지#이미지)를 보세요 |
| `package-needs.json` | 다운로드한 패키지마다 안에 있는 것과 쓰는 것의 ID. **필요한 것**이 다시 읽지 않고 알 수 있게 하려는 거예요(4.0) |
| `logs/hoard-<date>_<time>.log` | 콘솔 없이 실행될 때 Hoard가 출력하는 내용. 무엇을 읽었는지, 무엇을 다운로드했는지, 오류(비밀번호, 쿠키, 페이지 내용은 없어요). Hoard를 시작할 때마다 하나씩, 30일 동안 남겨요(오래됐어도 최근 10개는 남겨요). 20 MB 넘게 쓰는 실행은 `-part2`로 이어져요. 설정의 **로그 폴더 열기**가 이 폴더를 열어요. (2.9.2 전에는 모든 실행에 `hoard.log` 하나였어요.) |
| `diagnostics/incidents.jsonl` | 최근 오류와 충돌 트레이스백의 로컬 전용 비공개 기록. 지원 보고서를 만들 때 쓰고, 절대 자동으로 보내지 않아요 |
| `window/` | 창 자체의 저장 공간 |
| `window-place.json` | 마지막으로 닫았을 때 창의 크기와 위치, 최대화했는지 여부. 다음에도 거기서 열기 위해서예요. 지우면 보통 크기로 가운데에서 열려요 |
| `tasks.json` | 작업 창의 끝난 작업 목록(최근 60개). 각각 무엇을 했는지, 어떻게 됐는지, 진행 기록. 목록을 비우려면 이걸 지우거나 작업에서 **지우기**를 고르세요 |
| `sync.json` | 마지막 동기화를 시작한 때 |
| `routine.json` | 정기 점검을 마지막으로 실행한 때(다음이 언제인지 알기 위해)와, 찾은 것 중 아직 보지 않은 것의 수 |
| `update.json` | Hoard가 마지막으로 업데이트를 확인한 때와, 찾은 가장 새 버전 |
| `updates/` | 업데이트하는 동안 다운로드하고 확인한 새 버전의 설치 프로그램. 업데이트가 설치되면 지워요 |
| `debug/` | 문제 해결용 파일. `debug`나 `probe`를 실행할 때만 |

내가 직접 공유하지 않는 한, 이 중 어느 것도 내 컴퓨터를 떠나지 않아요.

## 지원 보고서

**지원 보고서 만들기**를 고르면, Hoard가 개인 정보를 지운 ZIP을 `Documents/Hoard/Support Reports`에 쓰고, 그 폴더를 열어 새 보고서를 선택해요. 이 폴더는 Hoard의 비공개 앱 데이터 밖에 있어서 ZIP을 찾아 첨부하기 쉬워요. 원본 로그, 로그인, 라이브러리 파일, 그 밖의 비공개 앱 데이터 파일은 ZIP에 복사하지 않아요. 공개 이슈에 첨부하기 전에 보고서 내용을 확인하세요.

## 다운로드 폴더

[설정](설정)에서 다른 곳을 고르지 않으면 문서 폴더 안의 `Hoard` 폴더예요. 상품은 `<스토어>/<제작자>/<상품>` 폴더에 있고, Hoard는 그 옆에 기록을 둬요.

| 무엇 | 무엇을 위한 것인지 |
|---|---|
| `catalog.json` | 다운로드한 모든 상품. 스토어, 이름, 제작자, 폴더, 스토어 페이지, 파일, 태그. [Hoard for Unity](Hoard-for-Unity-사용법) 같은 다른 프로그램이 읽어요 |
| `tags.json` | 모든 태그와 추천 태그, 그리고 그게 붙은 상품 |
| `<product>/asset.json` | 상품 하나의 같은 정보. 그 상품 폴더에 있어요 |
| `<product>/_thumbnail.*` | 상품 이미지 |
| `<Store>/_manifest.json` | 그 스토어에서 무엇을 어디에 다운로드했는지에 대한 Hoard 자체의 기록. 편집하지 마세요 |
| `*.part` | 중간에 멈춘 다운로드. 다음 다운로드가 끝난 곳부터 이어서 해요 |
| `Payhip/_download-yourself.html` | 2.5.0 전 버전이 남긴 것. Payhip 상품을 직접 다운로드하라고 목록으로 보여 줬어요. Hoard는 이제 Payhip에서 다운로드하지 않아서([스토어](스토어#payhip)를 보세요) 이 페이지를 쓰지도 읽지도 않아요. 지워도 돼요 |

`catalog.json`, `tags.json`, `asset.json`은 다른 프로그램이 읽으라고 쓰는 것이고, 깔끔한 텍스트, 평범한 상대 경로, 상품 자체의 스토어로 가는 링크만 있다고 약속해요. 정확한 형식은 [docs/DATA-FORMATS.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/DATA-FORMATS.md)(영어)에 있어요.

## 봉인

Hoard가 쓰는 모든 기록(라이브러리 목록과 표시, 다운로드 폴더의 스토어마다 있는 `_manifest.json`, `catalog.json`, `tags.json`, 모든 `asset.json`)에는 `integrity.key`로 만든 봉인이 붙어 있어요. 기록이 Hoard가 아닌 다른 것에 의해 바뀌면 봉인으로 알 수 있고, Hoard는 이렇게 해요.

- 알려 주고, 바뀐 파일의 사본을 볼 수 있게 남겨 둬요(`_manifest.changed-<date>.json` 같은 것).
- 기록은 남기지만 링크는 남기지 않고, 다음 새로고침이나 동기화 때 스토어에서 링크를 다시 가져와요(편집된 `marks.json`은 선택은 남기지만 숨긴 라이브러리의 PIN은 지워요).

`hoard-cli verify`는 다운로드 폴더의 모든 기록을 점검한 다음 카탈로그 파일을 다시 만들어요. 손상된 파일(올바른 JSON이 아닌 것 등)은 `<name>.damaged-<date>.json`으로 따로 두고, Hoard는 그것 없이 계속해요.

## 다운로드 폴더 하나를 컴퓨터 두 대에서

컴퓨터마다 Hoard는 자기 키로 기록을 봉인해서, 상대의 기록을 확인되지 않은 것("saved by Hoard on another computer")으로 다루고 스토어 링크를 다시 가져와요. NAS 등에서 다운로드 폴더 하나를 같이 쓰려면, 한 컴퓨터의 Hoard 앱 데이터 폴더에 있는 `integrity.key`를 다른 컴퓨터의 같은 곳으로 복사하세요.

## 백업, 그리고 새 컴퓨터로 옮기기

- **다운로드 폴더**는 Hoard의 기록이 옆에 있는 평범한 파일이에요. 통째로 백업하거나 옮기세요.
- **Hoard의 앱 데이터 폴더**에는 설정, 라이브러리 목록, 태그, 표시, `integrity.key`가 있어요. 새 컴퓨터의 같은 곳에 복사하면 봉인이 유효한 채로 그대로 써요.
- **로그인은 옮길 수 없어요.** 만든 컴퓨터의 내 계정용으로 암호화되어 있어서, 새 컴퓨터에서는 스토어에 다시 로그인하세요.

새 컴퓨터에서 다운로드 폴더가 다른 곳에 있다면 [설정](설정)에서 고르세요.

## 모두 삭제하기

1. **스토어**에서 **모든 스토어에서 로그아웃**을 고르세요. 할 수 있으면 세션을 끝내고, 모든 스토어의 아이템을 라이브러리에서 빼요.
2. Hoard를 제거하세요([Hoard 설치](Hoard-설치#제거)를 보세요. Mac에서는 응용 프로그램에서 휴지통으로 끌어다 놓고, Flatpak은 `flatpak uninstall --delete-data io.github.soloflighter1010.Hoard`).
3. Hoard의 앱 데이터 폴더(위)와, 파일이 필요 없다면 다운로드 폴더를 지우세요.
4. Hoard 전용 브라우저를 다운로드했다면 그것도 지우세요. Windows에서는 `%LOCALAPPDATA%\ms-playwright`, Mac에서는 `~/Library/Caches/ms-playwright`, Linux에서는 `~/.cache/ms-playwright`예요(Flatpak의 것은 `--delete-data`로 지워져요). Playwright를 쓰는 다른 프로그램과 같이 쓰고 있을 수 있어요.

전체 목록과 각각의 이유는 [PRIVACY.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/PRIVACY.md)(영어)에 있어요.
