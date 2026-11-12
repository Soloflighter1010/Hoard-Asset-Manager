<!-- Translated from Installing-Hoard (English 9c193036aa76). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Installing-Hoard">English</a> · <a href="Hoardのインストール">日本語</a> · <b>한국어</b> · AI의 도움을 받아 영어판에서 번역한 페이지예요. 영어판과 내용이 다르면 영어판이 맞는 정보예요. 이상한 번역을 찾으면 <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">번역 수정</a>으로 알려 주세요.</sub></p>

Hoard는 Windows, macOS, Linux(AppImage, .deb, Flatpak)용 앱이에요. 세 가지 모두에서 소스로 실행할 수도 있어요.

5.2.0 beta 6부터 Hoard는 새로운 방식(창은 Tauri, 서버는 Nuitka로 컴파일)으로 만들어지고, 파일도 새로워졌어요. 이 페이지는 그 파일들에 대한 설명이에요. 5.2.0이 나오기 전까지의 최신 릴리스인 Hoard 5.1은 지금까지와 같은 방법으로 설치해요. 각 섹션에 5.1에서 다른 점을 적어 두었어요.

## 새 Hoard로 옮기기

Hoard 5.1.4와 5.2.0 beta 5는 지금까지의 방식(PyInstaller)으로 만든 마지막 Hoard예요. 그 뒤의 버전은 새 앱으로 설치돼요. 그래서 Hoard가 스스로 그 버전으로 업데이트할 수 없고, 옛 Hoard를 먼저 제거하지 않으면 Hoard가 두 개가 돼요. 새 버전이 나오면 Hoard가 막대 아래에서 알려 줘요.

1. 지금 쓰는 Hoard를 제거하세요:
   - **Windows:** Windows 설정 › 앱 › 설치된 앱 › Hoard › 제거.
   - **macOS:** Hoard를 종료하고, 응용 프로그램에서 휴지통으로 옮기세요.
   - **Linux(Flatpak):** 제거할 것이 없어요. 새 Flatpak이 옛 Flatpak 위에 덮어 설치돼요(Flatpak에게는 같은 앱이에요). AppImage나 .deb를 쓰고 싶다면 소프트웨어 센터에서 Flatpak을 제거하거나 `flatpak uninstall io.github.soloflighter1010.Hoard`를 실행하세요.
   - **소스에서 실행하는 경우:** 제거할 것이 없어요.
2. 내 컴퓨터용 새 Hoard를 [릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)에서 내려받아, 아래 방법으로 설치하세요.

라이브러리, 설정, 로그인, 다운로드는 그대로 남아요. 제거하면 프로그램만 지워지고, 새 Hoard도 옛 Hoard처럼 그것들을 찾아요.

## Windows

1. [릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)에서 **`Hoard-<version>-windows-setup.exe`**를 내려받아 실행하세요. 내 계정에만 설치되고, 관리자 확인은 나오지 않아요. `%LOCALAPPDATA%\Hoard`에 설치되고, 시작 메뉴에 Hoard가 추가돼요. 내 계정만 바꿀 수 있는 폴더라서, 스토어 로그인을 안전하게 지켜 줘요.
2. 릴리스 후 한동안 Windows가 **"Windows의 PC 보호"**를 표시할 수 있어요. Hoard는 코드 서명이 되어 있어요(안의 프로그램과 라이브러리 모두). **추가 정보**를 고르면 게시자로 Hoard 관리자가 보여요. 새 게시자는 설치하는 사람이 늘수록 Microsoft의 신뢰를 얻어서, 이 경고는 시간이 지나면 사라져요. **실행**을 고르세요. 먼저 파일이 진짜인지 확인하고 싶다면 [다운로드한 파일 확인하기](#다운로드한-파일-확인하기)를 보세요.
3. 시작 메뉴에서 **Hoard**를 여세요. 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

Hoard 5.1의 설치 프로그램은 [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)의 **`Hoard-Setup-<version>.exe`**이고, `%LOCALAPPDATA%\Programs\Hoard`에 설치돼요.

창을 닫으면 Hoard가 종료돼요. 다운로드 중이면 먼저 물어봐요. 멈추고 닫기, 백그라운드에서 계속하기, 바로 닫기 중에서 고를 수 있어요(중간에 멈춘 다운로드는 다음에 이어서 해요).

**Hoard의 창**은 Microsoft Edge WebView2를 써요. Windows 11에 들어 있고, Windows 10에서도 최신으로 유지돼요.

### 업데이트

**설정**의 **Hoard 업데이트**에서 **지금 확인**을 고르세요. 새 버전이 있으면 **(버전)(으)로 업데이트**를 고르세요. Hoard가 닫히고(진행 중인 다운로드는 다음에 이어서 해요), 창이 새 버전의 설치 프로그램을 내려받아 설치한 뒤 Hoard를 다시 열어요. 설치 프로그램은 Hoard의 창에 들어 있는 Hoard 자신의 키로 서명된 경우에만 남기기 때문에, 다른 것이 대신 설치될 수 없어요. 새로 고침이나 다운로드 중에는 업데이트하지 않아요. 끝날 때까지 기다리거나 **중지**하세요.

**업데이트 자동 확인**(5.1부터는 끄지 않는 한 켜져 있어요. 전부터 쓰던 Hoard는 내가 고른 대로예요)을 켜면, Hoard가 시작할 때마다, 그리고 열려 있는 동안 하루에 한 번 백그라운드에서 GitHub에 물어봐요. 새 버전이 있으면 페이지 위쪽, Hoard 버전 옆에 **(버전)(으)로 업데이트**가 보여요. 확인할 때 GitHub에 보내는 것은 요청 자체뿐이에요. [보안과 개인정보](보안과-개인정보)를 보세요.

새 설치 프로그램을 언제든지 직접 지금의 Hoard 위에 실행할 수도 있어요. 업데이트는 프로그램 파일을 바꾸기 때문에, 옛 버전의 것은 남지 않아요. (Hoard 5.1도 `Hoard-Setup`으로 설치했다면 같은 방식으로 업데이트를 설치해요. 그때는 설치 프로그램을 릴리스의 체크섬으로 확인해요.)

설정, 라이브러리, 로그인, 태그는 프로그램과 같은 폴더(`%LOCALAPPDATA%\Hoard`)에, 파일은 다운로드 폴더에 있지만, 설치, 업데이트, 제거는 프로그램 자신의 파일만 건드려요.

### 제거

다른 앱처럼 Windows의 **설정 › 앱**에서 하세요. 지워지는 것은 프로그램뿐이에요(앱 데이터를 지우는 옵션으로 지워지는 것은 창 자신의 캐시뿐이에요). Hoard가 보관하는 모든 것을 지우려면 [Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요.

### 다운로드한 파일 확인하기

모든 릴리스는 이 저장소에서 GitHub Actions로 바로 빌드되고, 어떻게 빌드했는지에 대한 서명된 기록이 있어요. [GitHub CLI](https://cli.github.com/)로:

```
gh attestation verify Hoard-<version>-windows-setup.exe -R Soloflighter1010/Hoard-Asset-Manager
```

릴리스의 모든 파일에 똑같이 쓸 수 있어요(`Hoard-<version>-macos-apple-silicon.dmg`, `Hoard-<version>-linux-x86_64.AppImage` 등).

각 릴리스에는 체크섬도 있어요. 설치 프로그램은 `SHA256SUMS-windows-x86_64.txt`, Mac용 파일은 `SHA256SUMS-macos-apple-silicon.txt`와 `SHA256SUMS-macos-intel.txt`, AppImage와 .deb는 `SHA256SUMS-linux-x86_64.txt`, Flatpak은 `SHA256SUMS-flatpak.txt`, 소스 zip은 `SHA256SUMS.txt`예요. PowerShell에서는 `Get-FileHash .\Hoard-<version>-windows-setup.exe`로 비교할 값이 나와요. Mac에서는 `shasum -a 256 <file>`, Linux에서는 `sha256sum <file>`이에요.

모든 파일은 릴리스를 공개하기 전에 VirusTotal로 검사하고, 릴리스 노트에서 파일마다 보고서를 열 수 있어요. Mac용 Hoard는 Apple의 서명이 없고, 새로 서명한 프로그램은 아직 평판이 적어서, 드물게 한두 개의 엔진이 잘못 탐지할 수 있어요. 어느 엔진인지는 보고서에서 알 수 있어요. 어쨌든 각 릴리스는 공개 전에 사람이 직접 확인해요.

## macOS

Hoard는 macOS 11(Big Sur) 이상에서 돌아가요.

1. 내 Mac용 디스크 이미지를 [릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)에서 내려받으세요. M 시리즈 칩의 Mac은 **`Hoard-<version>-macos-apple-silicon.dmg`**, Intel Mac은 **`Hoard-<version>-macos-intel.dmg`**예요. (Apple 메뉴 › **이 Mac에 관하여**에서 알 수 있어요. "칩 Apple M…" 또는 "프로세서 … Intel"이에요.)
2. 열고, **Hoard**를 **응용 프로그램**으로 끌어다 놓으세요.
3. 응용 프로그램에서 Hoard를 여세요. Hoard는 아직 Apple의 서명이 없어서(해마다 비용이 들어요), 처음에는 macOS가 **열 수 없음** 또는 **악성 소프트웨어가 있는지 확인할 수 없음**이라고 표시해요. **완료**를 고르고(휴지통으로 이동하지 마세요), **시스템 설정 › 개인정보 보호 및 보안**을 열어 Hoard에 관한 메시지까지 스크롤한 뒤 **그래도 열기**를 고르세요. 먼저 파일이 진짜인지 확인하고 싶다면 [다운로드한 파일 확인하기](#다운로드한-파일-확인하기)를 보세요. 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

Hoard 5.1은 대신 패키지예요. [최신 릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest)의 **`Hoard-<version>-macos-apple-silicon.pkg`** 또는 **`...-macos-intel.pkg`**를 열고, 위와 같이 **개인정보 보호 및 보안**에서 허용하면 응용 프로그램에 Hoard가 설치돼요.

Hoard의 브라우저가 처음 스토어에 로그인할 때, macOS가 키체인을 써도 되는지 물어요. **항상 허용**을 고르세요. Hoard의 브라우저(Chromium, 약 150 MB)는 한 번만 `~/Library/Caches/ms-playwright`에 내려받아요.

**업데이트:** **설정 › Hoard 업데이트**에서 새 버전으로 **업데이트**하세요. Windows와 같이 Hoard의 창이 내려받아, Hoard의 서명이 있을 때만 남기고, 응용 프로그램의 앱을 바꾼 뒤 다시 열어요. (Hoard 5.1은 어떤 패키지를 내려받을지 알려 주니, 위와 같이 여세요.) **제거:** **Hoard**를 응용 프로그램에서 휴지통으로 끌어다 놓으세요. 설정, 라이브러리, 로그인, 태그는 `~/Library/Application Support/Hoard`에 있고, 지우지 않는 한 남아 있어요([Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요).

## Linux

Linux용 Hoard는 x86_64(Intel과 AMD) 컴퓨터용이고, 세 가지 형태가 있어요:

- **AppImage**(`Hoard-<version>-linux-x86_64.AppImage`): 대부분의 Linux에서 돌아가는 파일 하나예요. 실행할 수 있게 만든 뒤(속성에서, 또는 `chmod +x Hoard-<version>-linux-x86_64.AppImage`) 여세요. 스스로 업데이트해요.
- **.deb**(`Hoard-<version>-linux-amd64.deb`): Debian, Ubuntu와 그 계열용이에요. 소프트웨어 센터에서 열거나 `sudo apt install ./Hoard-<version>-linux-amd64.deb`를 실행하세요. 스스로 업데이트하고, 업데이트를 설치할 때 비밀번호를 물어요.
- **Flatpak**(`Hoard-<version>-linux-x86_64.flatpak`): 아래에서 설명해요. 샌드박스 안에서 돌아가고, Hoard 5.1도 이 형태예요.

Hoard의 창은 WebKitGTK를 써요. .deb는 함께 설치하고, AppImage는 안에 들어 있고, Flatpak은 런타임과 함께 받아요. 어느 것이든 설정, 라이브러리, 로그인, 태그를 다른 Linux용 Hoard와 같은 `~/.local/share/Hoard`에 보관해서, 다른 형태의 라이브러리도 이어지고 Hoard for Unity도 찾을 수 있어요. 로그인에는 키링이 필요해요. GNOME Keyring, Secret Service를 켠 KeePassXC, KWallet 중 하나예요.

### Flatpak

대부분의 데스크톱 Linux에는 이미 Flatpak이 있어요. 없다면 [flatpak.org/setup](https://flatpak.org/setup/)을 보세요.

1. [릴리스](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases)에서 **`Hoard-<version>-linux-x86_64.flatpak`**을 내려받으세요.
2. 소프트웨어 센터(GNOME Software, KDE Discover)에서 열거나, 터미널에서 설치하세요:

   ```
   flatpak install --user Hoard-<version>-linux-x86_64.flatpak
   ```

   Hoard는 GNOME 런타임에서 돌아가고, Flatpak은 그것을 [Flathub](https://flathub.org/)에서 받아요. `org.gnome.Platform`을 찾을 수 없다고 나오면, Flathub를 한 번 추가하고 다시 해 보세요:
   `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
3. 응용 프로그램 메뉴에서 **Hoard**를 여세요(또는 `flatpak run io.github.soloflighter1010.Hoard`). 전용 창에서 열리고, 짧은 설정 도우미가 나머지를 안내해요. [시작하기](시작하기)를 보세요.

Flatpak이 쓸 수 있는 것은 네트워크, 창 표시, 키링(로그인용), 홈 폴더와 이동식 드라이브(다운로드 폴더용)뿐이에요. Hoard의 브라우저(Chromium, 약 150 MB)는 한 번만 `~/.var/app/io.github.soloflighter1010.Hoard/cache`에 내려받아요.

**업데이트:** **설정 › Hoard 업데이트**에 새 버전이 있다고 나오면, 그 버전의 `.flatpak`을 내려받아 위와 같이 설치하세요. 옛것을 대신해요. **제거:** `flatpak uninstall io.github.soloflighter1010.Hoard`(또는 소프트웨어 센터). 설정과 라이브러리는 남아요. 그것까지 지우려면 [Hoard가 저장하는 곳](Hoard가-저장하는-곳#모두-삭제하기)을 보세요.

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
