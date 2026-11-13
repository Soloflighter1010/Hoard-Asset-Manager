<!-- Translated from Hoard-and-Other-Tools (English c21a8dfa6ea9). When the English page changes: python3 scripts/wiki_translations.py --diff -->
<p><sub><a href="Hoard-and-Other-Tools">English</a> · <a href="Hoardとほかのツール">日本語</a> · <b>한국어</b> · AI의 도움을 받아 영어판에서 번역한 페이지예요. 영어판과 내용이 다르면 영어판이 맞는 정보예요. 이상한 번역을 찾으면 <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml">번역 수정</a>으로 알려 주세요.</sub></p>

VRChat 크리에이터가 쓰는 도구는 Hoard만 있는 게 아니에요. 자주 이야기되는 건 VRChat 공식 **Creator Companion**(VCC), **ALCOM**, **KonoAsset** 세 가지예요. 저마다 하는 일이 다르고, 여러 개를 함께 쓰는 사람도 많아요.

- **Creator Companion**은 Unity 프로젝트와 그 패키지(VRChat SDK, 다른 사람의 저장소에 있는 패키지)를 다루는 VRChat 공식 도구예요.
- **ALCOM**은 Creator Companion을 대신하는, 빠른 오픈 소스 도구예요. Windows, macOS, Linux에서 돌아가요.
- **KonoAsset**은 이미 다운로드한 VRChat 에셋을 종류, 카테고리, 태그, 맞는 아바타로 정리해요.
- **Hoard**는 스토어에서 산 것을 읽고, 다운로드해서 최신으로 유지하고, Unity 프로젝트도 관리해요.

함께 쓸 수 있어요. Hoard의 프로젝트는 Creator Companion, ALCOM과 같은 목록을 쓰기 때문에, 어느 쪽에서 만든 프로젝트든 다른 쪽에도 보여요.

## 나란히 비교

각 도구가 하는 일을, 2026년 11월 기준 각 도구의 문서에서 정리했어요. 도구는 바뀌니까 아래에 링크한 각 페이지도 확인하세요.

| | Hoard | Creator Companion | ALCOM | KonoAsset |
|---|---|---|---|---|
| **무엇을 위한 도구인가** | 산 것: 목록으로 보여 주고, 다운로드하고, 최신으로 유지하고, 프로젝트에 넣기 | VRChat의 Unity 프로젝트와 그 패키지 | Creator Companion이 하는 일을, 더 빠르게, 더 많은 운영체제에서 | 다운로드한 에셋 정리 |
| **스토어** | Booth, Gumroad, Jinxxy, Payhip, itch.io에서 가진 것을 내 계정으로 로그인해서, 또는 저장한 페이지에서 읽기 | 없음 | 없음 | BOOTH 링크로 상품 정보 채우기 |
| **다운로드와 업데이트** | 새것과 바뀐 것을 다운로드하고, 이전 버전도 남기기(Payhip 것은 목록만 보여 주고, 다운로드는 Payhip에서) | VPM 저장소의 패키지 | VPM 저장소의 패키지를, 한꺼번에, 변경 내역과 함께 | 없음: 다운로드한 것을 추가(끌어다 놓기, .zip은 압축 해제) |
| **정리** | 태그(내 것과 제작자의 것), 종류, 공유할 수 있는 세트, 가격이 붙은 위시리스트, 접두어 검색 | 없음 | 없음 | 종류, 카테고리, 태그, 메모, 의존 관계, 맞는 아바타로 검색 |
| **Unity 프로젝트** | 라이브러리의 상품을 넣어서 만들기(VRChat 템플릿, 또는 빈 프로젝트), 패키지와 저장소, 백업, Git 소스 관리 | 템플릿으로 만들기, 기존 프로젝트 추가, 마이그레이션, 백업, 패키지, 다른 사람의 저장소(2.1.0부터) | 템플릿으로 만들기(내 템플릿도, 1.1.0부터), 백업, Unity 버전 바꾸기, 마이그레이션, 패키지와 저장소 | 없음 |
| **Unity 안에서** | Hoard for Unity: 창에서 라이브러리 보기, 상품과 세트 가져오기, 크레딧 | VRChat SDK | 없음 | 없음 |
| **운영체제** | Windows, macOS, Linux | Windows 10, 11(macOS와 Linux에서는 일부를 명령줄로) | Windows, macOS, Linux(Linux는 커뮤니티 지원) | Windows 10, 11 |
| **언어** | 영어, 일본어, 한국어 | 영어 | 영어, 일본어, 한국어, 독일어, 프랑스어, 중국어(간체, 번체) | 일본어, 영어, 중국어(간체) |
| **가격** | 무료 | 무료 | 무료 | 무료 |
| **소스** | 오픈 소스(MIT 라이선스) | VRChat 자체 앱으로, 오픈 소스가 아님 | 오픈 소스(MIT 라이선스) | 오픈 소스(MIT 라이선스) |

## 무엇을 쓸까

- **VRChat 패키지로 아바타나 월드를 만들기만 한다면?** Creator Companion은 VRChat 공식 도구이고, 시작하는 방법도 그 문서에 나와 있어요.
- **같은 일을, 더 빠르게, 또는 Mac이나 Linux에서?** ALCOM은 같은 설정으로 Creator Companion이 하는 일을 해서, 오가며 쓸 수 있어요.
- **다운로드한 것을 메모와 맞는 아바타와 함께 직접 정리하고 싶다면?** KonoAsset이 그걸 위한 도구예요.
- **KonoAsset에서 Hoard로 옮긴다면?** Hoard 설정의 **KonoAsset에서 가져오기...**로 라이브러리를 가져올 수 있어요(5.2.0 베타 5). BOOTH 상품으로 Hoard 라이브러리와 맞추고, 나머지는 지금 자리 그대로 로컬 상품으로, 태그와 메모도 함께 가져와요. [내 패키지](내-패키지#konoasset에서)를 보세요.
- **여러 스토어에서 산 것을 한곳에 모으고, 다운로드해서 최신으로 유지하고 싶다면?** 그게 Hoard예요. 상품을 프로젝트에 넣을 수 있고, 프로젝트 목록은 Creator Companion, ALCOM과 같아요.

## 각 도구의 페이지

- Creator Companion: [vcc.docs.vrchat.com](https://vcc.docs.vrchat.com/)
- ALCOM: [vrc-get.anatawa12.com/alcom](https://vrc-get.anatawa12.com/alcom), [GitHub의 소스](https://github.com/vrc-get/vrc-get)
- KonoAsset: [BOOTH 페이지](https://silolab.booth.pm/items/6641548), [GitHub의 소스](https://github.com/siloneco/KonoAsset)

오래된 내용이 있거나 어느 도구에 공정하지 않은 부분이 있다면 [알려 주세요](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new/choose). 고칠게요.
