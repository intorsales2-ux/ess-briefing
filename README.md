# 인투알 ESS 데일리 브리핑 — 자동화 파이프라인

매일 아침 07:30, ESS·재생에너지·RE100·입찰 뉴스를 자동 수집하고 Claude가
외함(컨테이너·랙) 사업 관점으로 요약·시사점·To-Do를 작성해
**웹페이지 갱신 + 대표이사 이메일 발송**까지 수행하는 파이프라인입니다.

```
수집(뉴스 RSS·전력거래소 공지·주가) → Claude 선별·요약 → HTML 렌더링 → 웹 게시 + 이메일 발송
```

## 폴더 구조

```
ess-pipeline/
├── main.py                 # 실행 진입점 (오케스트레이터)
├── collectors.py           # 뉴스 RSS · 전력거래소 공지 · 주가(yfinance) 수집
├── ai.py                   # Claude API — 기사 선별·요약·시사점·To-Do 생성
├── render.py               # Jinja2 템플릿 → HTML 렌더링
├── emailer.py              # SMTP 이메일 발송
├── config.yaml             # ★ 키워드·종목·KPI 등 모든 설정 (여기만 고치면 됨)
├── .env.example            # API 키·메일 계정 설정 견본 → .env 로 복사해 사용
├── templates/briefing.j2   # 다크 테마 브리핑 템플릿 (로고 임베드)
├── assets/logo_b64.txt     # 인투알 로고 (base64)
├── data/sample_data.json   # dry-run용 샘플 콘텐츠
├── output/                 # 생성 결과 (index.html + archive/날짜.html)
└── .github/workflows/daily-briefing.yml   # 매일 07:30 자동 실행 (GitHub Actions)
```

## 1분 미리보기 (API 키 없이)

```bash
pip install -r requirements.txt
python main.py --dry-run
# → output/index.html 을 브라우저로 열어 확인
```

## 실제 가동 (수집 + AI 요약 + 발송)

1. **Claude API 키 발급** — https://console.anthropic.com → API Keys
2. `.env.example` 을 `.env` 로 복사하고 값 입력
   - `ANTHROPIC_API_KEY` : 필수
   - `SMTP_*`, `MAIL_TO` : 이메일 발송용 (사내 SMTP, Gmail 앱 비밀번호, 네이버웍스 등)
3. 실행

```bash
python main.py             # 전체 파이프라인 (발송 포함)
python main.py --no-email  # 발송만 생략하고 결과 확인
```

## 매일 자동 실행 — 두 가지 방법

### 방법 A. GitHub Actions + GitHub Pages (서버 불필요, 권장)

1. 이 폴더를 GitHub 비공개 저장소로 push
2. 저장소 **Settings → Secrets and variables → Actions** 에 등록:
   `ANTHROPIC_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`, `MAIL_TO`
3. **Settings → Pages** → Source: `Deploy from a branch`, Branch: `main` / `/docs`
4. 끝 — 매 평일 07:30(KST) 자동 실행되어
   - `https://<계정>.github.io/<저장소>/` 웹페이지 갱신
   - 대표이사 이메일 발송
   - `docs/archive/` 에 일자별 보관

> Actions 탭에서 `Run workflow` 버튼으로 즉시 수동 실행도 가능합니다.

### 방법 B. 사내 서버 cron

```bash
crontab -e
# 매 평일 07:30 실행
30 7 * * 1-5 cd /path/to/ess-pipeline && /usr/bin/python3 main.py >> run.log 2>&1
```

## 커스터마이즈 — `config.yaml` 하나로 관리

| 항목 | 위치 | 설명 |
|---|---|---|
| 뉴스 검색 키워드 | `news.google_news_queries` | 줄 추가/삭제로 즉시 반영 |
| 구독 RSS 추가 | `news.extra_rss` | 전문지 RSS 주소 직접 등록 |
| 입찰 공고 감지 | `kpx.*` | 전력거래소 공지 게시판·키워드 |
| 주가 보드 종목 | `stocks.kr / global` | yfinance 티커로 추가 (예: `009830.KS`) |
| 상단 KPI 4종 | `kpis` | 시장 구조 지표 — 월 1회 수동 갱신 권장 |
| 수신자 변경 | `.env`의 `MAIL_TO` | 쉼표로 여러 명 |

## 운영 시 알아둘 점

- **AI 요약은 검수 후 신뢰** — 발행 전 1분 검토(STEP 3)를 권장합니다. 헤드라인
  클릭 시 원문으로 이동하므로 수치 확인이 쉽습니다.
- **주가는 지연 시세**(야후 파이낸스 기준)이며 투자 판단용이 아닙니다.
  수집 실패 시 자동으로 `SAMPLE DATA` 배지가 붙습니다.
- **전력거래소 공지 수집**은 사이트 개편 시 셀렉터 수정이 필요할 수 있습니다
  (`collectors.py > collect_kpx_notices`). 실패해도 파이프라인은 계속 진행됩니다.
- **확장 아이디어**: 나라장터(g2b) 입찰공고 OpenAPI, DART 전자공시 OpenAPI 연동
  (둘 다 공공데이터포털에서 무료 키 발급 — `collectors.py`에 함수 추가하면 됨),
  카카오워크/슬랙 웹훅 알림, 주간 리포트 모드.
- **비용 감각**: Claude API 호출은 하루 2회(선별 + 총평)로 소량입니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| `ANTHROPIC_API_KEY 없음 → dry-run 전환` | `.env` 파일 위치·키 값 확인 |
| 이메일 발송 실패 | 포트(587/465)·앱 비밀번호 확인, 사내 방화벽의 SMTP 허용 여부 |
| 기사가 너무 적게 잡힘 | `news.lookback_hours` 늘리기, 키워드 추가 |
| Actions가 안 돎 | 저장소 Secrets 등록 여부, Actions 활성화 여부 확인 |
