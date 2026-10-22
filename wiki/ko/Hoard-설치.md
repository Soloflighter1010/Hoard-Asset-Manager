<!-- Translated from Installing-Hoard (English 9ab876e03205). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Installing-Hoard">English</a> · <a href="Hoardのインストール">日本語</a> · <b>한국어</b> · AI의 도움을 받아 영어판에서 번역한 페이지예요. 영어판과 내용이 다르면 영어판이 맞는 정보예요. 이상한 번역을 찾으면 <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">번역 수정</a>으로 알려 주세요.</sub></p>

Hoard는 Windows, macOS, Linux(Flatpak)용 앱이에요. 세 가지 모두에서 소스로 실행할 수도 있어요.

## Windows

1. [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)에서 **`Hoard-Setup-<version>.exe`**를 다운로드해서 실행하세요. 내 계정에만 설치되고 관리자 확인 창은 뜨지 않아요. `%LOCALAPPDATA%\Programs\Hoard`에 설치되고 시작 메뉴에 Hoard가 추가돼요(바탕 화면 아이콘은 고를 수 있어요). 폴더는 바꿀 수 없어요. 내 계정만 바꿀 수 있는 폴더라서 스토어 로그인을 안전하게 지켜 주거든요. (예전 설치 프로그램으로 다른 곳에 설치한 Hoard는 업데이트할 때 여기로 설치돼요. 그다음 예전 폴더는 지워도 돼요.)
2. 릴리스 후 한동안 Windows가 **"Windows의 PC 보호"** 화면을 보여 줄 수 있어요. Hoard는 코드 서명이 되어 있어요. **추가 정보**를 고르면 게시자로 Hoard의 관리자가 보여요. 새 게시자는 설치하는 사람이 늘수록 Microsoft의 신뢰를 얻기 때문에, 이 경고는 시간이 지나면 사라져요. **실행**을 고르세요. 먼저 파일이 진짜인지 확인하고 싶다면 [다운로드한 파일 확인하기](#다운로드한-파일-확인하기)를 보세요.
3. 시작 메뉴에서 **Hoard**를 여세요. 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

창을 닫으면 Hoard가 종료돼요. 다운로드 중이면 먼저 물어봐요. 멈추고 닫기, 백그라운드에서 계속하기, 바로 닫기 중에서 고를 수 있어요(중간에 멈춘 다운로드는 다음에 멈춘 곳부터 이어서 해요).

**예전에 포터블 zip을 썼나요?** 4.3.6부터 더 이상 공개하지 않아요. 백신 프로그램이 계속 잘못 탐지했거든요. 대신 `Hoard-Setup`을 실행하세요. 설정, 라이브러리, 다운로드는 그대로 이어지고(프로그램과 따로 보관돼요), 그때부터는 Hoard가 스스로 업데이트해요. 그다음 zip을 풀었던 폴더는 지우세요.

**Hoard 창**은 Microsoft Edge WebView2를 써요. Windows 11에 들어 있고, Windows 10에서도 최신으로 유지돼요. 없으면 Hoard가 알려 주고 대신 웹 브라우저에서 열려요. 종료하려면 **설정**에서 **Hoard 종료**를 고르세요.

### 업데이트

**설정**의 **업데이트**에서 **지금 확인**을 고르세요. 새 버전이 있으면 **(버전)(으)로 업데이트**를 고르세요. Hoard가 GitHub 릴리스에서 설치 프로그램을 다운로드하고, 확인한 다음 닫고(진행 중인 다운로드는 다음에 이어서 해요), 설치하고 다시 열어요. 설치 프로그램의 SHA-256이 릴리스의 `SHA256SUMS-windows.txt`와 GitHub에 나온 파일 체크섬 둘 다와 맞을 때만 실행하고, 맞지 않으면 지워요. 새로고침이나 다운로드 중에는 업데이트하지 않아요. 끝날 때까지 기다리거나 **중지**하세요.

**업데이트 자동 확인**(5.1부터는 끄지 않으면 켜져 있어요. 전부터 쓰던 Hoard는 내가 고른 그대로예요)이 켜져 있으면 Hoard가 시작할 때마다, 그리고 열려 있는 동안 하루에 한 번 백그라운드에서 GitHub에 물어봐요. 새 버전이 있으면 페이지 아래에 **(버전)(으)로 업데이트**가 보여요. 확인할 때 GitHub에 보내는 건 요청 자체뿐이에요. [보안과 개인정보](보안과-개인정보)를 보세요.

Hoard가 업데이트를 직접 설치하는 건 `Hoard-Setup`으로 설치했을 때뿐이에요. 포터블 zip에서 꺼낸 사본, Mac 앱, Flatpak, Python으로 실행한 Hoard는 새 버전이 있다는 것과 어떤 파일을 받으면 되는지 알려 주고, 그 링크를 보여 줘요. 새 설치 프로그램은 언제든 직접 실행해도 돼요. 먼저 제거할 필요는 없고, 업데이트는 프로그램 파일을 모두 바꾸기 때문에 예전 버전의 흔적이 남지 않아요.

설정, 라이브러리, 로그인, 태그는 Hoard의 앱 데이터 폴더(`%LOCALAPPDATA%\Hoard`)에, 파일은 다운로드 폴더에 있어서, 설치, 업데이트, 제거를 해도 사라지지 않아요.

### 제거

다른 앱처럼 Windows의 **설정 › 앱**에서 제거하세요. 프로그램만 지워져요. Hoard가 보관하는 모든 것을 지우려면 [Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요.

### 다운로드한 파일 확인하기

모든 릴리스는 GitHub Actions가 이 저장소에서 바로 빌드하고, 어떻게 빌드했는지 서명된 기록이 남아요. [GitHub CLI](https://cli.github.com/)로 이렇게 확인하세요.

```
gh attestation verify Hoard-Setup-<version>.exe -R Soloflighter1010/Hoard-Asset-Manager
```

릴리스의 모든 파일에서 똑같이 확인할 수 있어요(`Hoard-<version>-macos-apple-silicon.pkg`, `Hoard-<version>-linux-x86_64.flatpak` 등).

릴리스마다 체크섬도 있어요. 설치 프로그램과 Windows zip은 `SHA256SUMS-windows.txt`, Mac 패키지는 `SHA256SUMS-macos-apple-silicon.txt`와 `SHA256SUMS-macos-intel.txt`, Flatpak은 `SHA256SUMS-linux.txt`, 소스 zip은 `SHA256SUMS.txt`예요. 비교할 값은 PowerShell에서는 `Get-FileHash .\Hoard-Setup-<version>.exe`, Mac에서는 `shasum -a 256 <file>`, Linux에서는 `sha256sum <file>`로 볼 수 있어요.

모든 파일은 릴리스를 공개하기 전에 VirusTotal로 검사해요. 릴리스 노트에 파일마다 보고서 링크가 있어요. Hoard의 Mac 패키지는 Apple 서명이 없고, 새로 서명한 프로그램은 아직 평판이 적어서, 가끔 엔진 한두 개가 잘못 탐지할 수 있어요. 어느 엔진인지는 보고서에 나와요. 어쨌든 모든 릴리스는 공개 전에 사람이 직접 확인해요.

## macOS

Hoard는 macOS 11(Big Sur) 이상에서 실행돼요.

1. [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)에서 내 Mac에 맞는 패키지를 다운로드하세요. M 시리즈 칩이 있는 Mac이면 **`Hoard-<version>-macos-apple-silicon.pkg`**, Intel Mac이면 **`Hoard-<version>-macos-intel.pkg`**예요. (Apple 메뉴 › **이 Mac에 관하여**에서 알 수 있어요. "칩 Apple M…" 또는 "프로세서 … Intel"이라고 나와요.)
2. 여세요. Hoard는 아직 Apple 서명이 없어서(해마다 비용이 들어요), macOS가 **열 수 없다**거나 **악성 소프트웨어가 없는지 확인할 수 없다**고 표시해요. **완료**를 고르고('휴지통으로 이동'이 아니에요), **시스템 설정 › 개인정보 보호 및 보안**을 열어서 Hoard 패키지에 대한 메시지까지 스크롤한 다음 **그래도 열기**를 고르세요. 먼저 파일이 진짜인지 확인하고 싶다면 [다운로드한 파일 확인하기](#다운로드한-파일-확인하기)를 보세요.
3. 설치 프로그램이 **Hoard**를 **응용 프로그램**에 넣어요(모든 계정용으로 설치하는 앱처럼 Mac 비밀번호를 물어봐요). 응용 프로그램이나 Launchpad에서 여세요. 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

Hoard의 브라우저가 처음으로 스토어에 로그인할 때, macOS가 키체인을 써도 되는지 물어봐요. **항상 허용**을 고르세요. Hoard의 브라우저(Chromium, 약 150 MB)는 `~/Library/Caches/ms-playwright`에 한 번만 다운로드돼요.

**업데이트:** **설정 › 업데이트**에 새 버전이 있다고 나오면, 그 버전의 패키지를 다운로드해서 위와 같이 여세요. 예전 Hoard를 바꿔 줘요. **제거:** **Hoard**를 응용 프로그램에서 휴지통으로 끌어다 놓으세요. 설정, 라이브러리, 로그인, 태그는 `~/Library/Application Support/Hoard`에 있고, 지우지 않으면 남아 있어요([Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요).

## Linux(Flatpak)

Linux용 Hoard는 x86_64(Intel과 AMD) 컴퓨터용 [Flatpak](https://flatpak.org/)이에요. 데스크톱 Linux 대부분에는 Flatpak이 이미 있어요. 없다면 [flatpak.org/setup](https://flatpak.org/setup/)을 보세요.

1. [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)에서 **`Hoard-<version>-linux-x86_64.flatpak`**를 다운로드하세요.
2. 소프트웨어 센터(GNOME Software, KDE Discover)로 열거나, 터미널에서 설치하세요.

   ```
   flatpak install --user Hoard-<version>-linux-x86_64.flatpak
   ```

   Hoard는 GNOME 런타임에서 실행되고, Flatpak은 그것을 [Flathub](https://flathub.org/)에서 받아요. `org.gnome.Platform`을 찾을 수 없다고 나오면 Flathub를 한 번 추가하고 다시 해 보세요: `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
3. 응용 프로그램 메뉴에서 **Hoard**를 여세요(또는 `flatpak run io.github.soloflighter1010.Hoard`). 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

Flatpak이 쓸 수 있는 건 네트워크, 창 표시, 키링(로그인용: GNOME Keyring, Secret Service를 켠 KeePassXC, KWallet), 홈 폴더와 이동식 드라이브(다운로드 폴더용)뿐이에요. 설정, 라이브러리, 로그인, 태그는 다른 Linux용 Hoard처럼 `~/.local/share/Hoard`에 보관해서, 소스로 실행하던 Hoard의 라이브러리도 이어지고 Hoard for Unity도 찾을 수 있어요. Hoard의 브라우저(Chromium, 약 150 MB)는 `~/.var/app/io.github.soloflighter1010.Hoard/cache`에 한 번만 다운로드돼요.

**업데이트:** **설정 › 업데이트**에 새 버전이 있다고 나오면, 그 버전의 `.flatpak`를 다운로드해서 위와 같이 설치하세요. 예전 것을 바꿔 줘요. **제거:** `flatpak uninstall io.github.soloflighter1010.Hoard`(또는 소프트웨어 센터). 설정과 라이브러리는 남아요. 그것까지 지우려면 [Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요.

## 소스에서 실행하기(Windows, macOS, Linux)

1. [Python 3.10 이상](https://www.python.org/downloads/)을 설치하세요.
2. [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)에서 `Hoard-<version>.zip`을 다운로드해서 내 폴더에 풀어 주세요.
3. `Hoard.bat`(Windows) 또는 `./run.sh`(macOS와 Linux)를 실행하세요.

처음 실행할 때 그 폴더에 전용 Python 환경을 만들어요. 모든 패키지를 미리 기록해 둔 지문과 대조하기 때문에, 변조된 패키지는 설치되지 않아요. Windows에서는 그 폴더를 내 계정만 바꿀 수 있게도 해요.

소스에서 실행하면 Hoard는 전용 창이 아니라 웹 브라우저에서 열려요. 종료하려면 **설정**에서 **Hoard 종료**를 고르거나, Hoard 페이지를 닫기만 하면 돼요. 마지막 페이지를 닫고 몇 분 뒤에 저절로 멈춰요.

스토어 로그인에는 Windows에서는 Microsoft Edge를, 그 밖의 시스템이나 Edge가 없을 때는 Hoard 전용 브라우저(버전을 고정한 Chromium, 약 150 MB, 한 번만 다운로드)를 써요.

- **macOS**는 Hoard의 브라우저가 키체인을 써도 되는지 한 번 물어봐요. **항상 허용**을 고르세요.
- **Linux**는 로그인을 지키기 위해 키링이 필요해요. GNOME Keyring, Secret Service를 켠 KeePassXC, 또는 KWallet이에요. 데스크톱이 없는 컴퓨터는 [스토어](스토어#로그인)를 보세요. 브라우저가 시작되지 않으면 Hoard 폴더에서 `.venv/bin/python -m playwright install-deps chromium`을 실행하세요.

## Hoard 1.x에서 옮겨 오기

로그인과 태그는 저절로 이어져요. 설정 도우미의 **전에 Hoard를 썼나요?** 단계에서 라이브러리 목록과 다운로드 폴더를 가져와요. 1.x를 실행하던 폴더를 고르세요. 명령줄에서는 `hoard-cli migrate <folder>`예요.
