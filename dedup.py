# -*- coding: utf-8 -*-
"""기출(이미 발행한 기사 URL) 관리 — 에디터 지시서 v2의 '중복 방지'를 담당.

- output/seen_urls.json 에 발행한 기사 URL을 누적 보관합니다.
- 수집 직후 이 목록과 대조해, 이미 실린 기사를 카드 후보에서 제외합니다.
- 실제 발행(이메일 발송)했을 때만 기록합니다. --dry-run 은 기록하지 않습니다.

※ GitHub Actions 자동화 시에는 이 파일을 저장소에 다시 커밋해야 다음 날에도
   기억이 유지됩니다. (자동화 세팅 6단계에서 함께 설정할 예정)
"""
from __future__ import annotations
import json
from pathlib import Path

SEEN_PATH = Path(__file__).resolve().parent / "output" / "seen_urls.json"
KEEP_LAST = 500  # 최근 500건만 보관 (약 3개월치 — '직전 5개 호' 규칙보다 넉넉하게)


def load_seen() -> set:
    """기출 URL 목록을 읽어온다. 파일이 없거나 깨졌으면 빈 목록."""
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def filter_new(articles: list[dict], seen: set) -> tuple[list[dict], int]:
    """기출 URL을 제외한 기사 목록과, 제외한 건수를 돌려준다."""
    fresh = [a for a in articles if a.get("url") not in seen]
    return fresh, len(articles) - len(fresh)


def record(urls: list[str], seen: set) -> None:
    """발행에 실제 사용한 URL을 기출 목록에 추가 저장한다."""
    merged = list(seen) + [u for u in urls if u and u not in seen]
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(merged[-KEEP_LAST:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
