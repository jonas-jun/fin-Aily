# fin-aily-us 디자인 리브랜딩 계획

## 1. 개요

fin-aily-kr의 리브랜딩 기획안(issue #11)과 동일한 디자인 언어를 US 버전에 적용한다.
KR 버전과의 차이는 Primary 색상(Rose Red → Green)과 배지 텍스트(`KR` → `US`)뿐이며, 구조와 컴포넌트 패턴은 동일하게 맞춘다.

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 서비스명 | StockInsight / fin-Aily | fin-aily-us |
| 핵심 컬러 | blue-600 (`#2563EB`) | Emerald Green `#22C55E` |
| 보조 컬러 | slate 계열 | Navy Blue `#1E3A5F` |
| 로고 | 📈 이모지 + 텍스트 | SVG 로고 (주식 상승 삼각형 아이콘 포함) |

---

## 2. 색상 체계 (Color System)

| 역할 | 색상 | Hex |
|---|---|---|
| Primary (강조 · CTA · 배지) | Emerald Green | `#22C55E` |
| Brand Text | Navy Blue | `#1E3A5F` |
| Surface / Background | White | `#FFFFFF` |
| Border / Divider | Slate 200 | `#E2E8F0` |
| Body Text | Slate 700 | `#334155` |
| Muted Text | Slate 400 | `#94A3B8` |

---

## 3. 로고 디자인

**구성 요소** (첨부 로고 이미지 기준)
- **워드마크**: `fin-aily` — Navy Blue(`#1E3A5F`), 굵은 Sans-serif
- **아이콘**: 주식 상승 삼각형(▲) — Emerald Green(`#22C55E`), `fin`의 `i` 닷 + `aily`의 `i` 닷 위치에 배치
- **배지**: `us` — 흰색 텍스트, Emerald Green 배경의 둥근 사각형
- **이모지 없음**: 📈 그래프 이모지는 Header, Hero, Auth 어디에도 사용하지 않음

**사용처별 크기**

| 사용처 | 크기 |
|---|---|
| Header (PC) | height: 32px |
| Header (모바일) | height: 24px |
| Hero 섹션 | height: 56px |

---

## 4. 파일별 변경 사항

### 4-1. `tailwind.config.js`
- 커스텀 컬러 추가: `brand-navy: '#1E3A5F'`, `brand-green: '#22C55E'`

### 4-2. `components/ui/Logo.tsx` (신규)
- SVG 로고 컴포넌트 구현 (이모지 없음, 순수 SVG)
- `size` prop으로 `"header"` / `"hero"` 두 가지 크기 지원
- 삼각형 ▲ 아이콘을 `i` 닷 위치에 인라인 SVG로 배치
- `us` 배지 포함

### 4-3. `components/ui/Header.tsx`
- 📈 이모지 + 텍스트 로고 → `<Logo size="header" />` 교체
- 활성 Nav 링크 색상: `text-[#22C55E]` (기존 `text-blue-700`)

### 4-4. `app/layout.tsx`
- `<title>`: `fin-aily-us — AI Stock News Insights`
- `description`: `Get AI-powered summaries of the latest news for US-listed companies.`
- `lang="en"` (기존 `lang="ko"`)

### 4-5. `app/page.tsx`
- 히어로 섹션에서 `📈` 이모지 div + `<h1>fin-Aily</h1>` 텍스트 완전 제거 → `<Logo size="hero" />` 단일 요소로 대체
- 탭 활성 색상: `text-[#22C55E]` (기존 `text-blue-600`)
- 로딩 스피너: `border-[#22C55E]` (기존 `border-blue-600`)
- 설명 텍스트: 한국어 → 영어로 변경

### 4-6. `components/ui/TickerSearch.tsx`
- 검색창 focus ring: `focus:border-[#22C55E] focus:ring-[#22C55E]` (기존 blue-500)
- 검색 버튼 배경: `bg-[#22C55E] hover:bg-green-600` (기존 blue-600)
- placeholder 텍스트: 영어로 변경 (`Search by ticker (e.g. AAPL, TSLA)`)
- 검색 버튼 텍스트: `Search` (기존 `검색`)

### 4-7. `components/news/DigestCard.tsx`
- Market Pulse 번호 색상: `text-[#22C55E]` (기존 `text-blue-500`)
- "Yahoo Finance 최신 뉴스 AI 요약" → "Yahoo Finance News AI Summary"

### 4-8. `components/news/ArticleList.tsx`
- 번호 색상: `text-[#22C55E]` (기존 `text-blue-500`)
- 기사 hover 색상: `group-hover:text-[#22C55E]` (기존 `group-hover:text-blue-600`)
- `↗` 아이콘 색상: `text-[#22C55E]` (기존 `text-blue-500`)
- "관련 기사" → "Related Articles"

### 4-9. `app/auth/page.tsx`
- `📈` 이모지 + "StockInsight" h1 완전 제거 → `<Logo size="header" />` 교체
- 한국어 텍스트 → 영어 변경

---

## 5. 구현 순서

| 순서 | 파일 | 내용 |
|---|---|---|
| 1 | `tailwind.config.js` | 커스텀 컬러 추가 |
| 2 | `components/ui/Logo.tsx` | SVG 로고 컴포넌트 신규 생성 |
| 3 | `components/ui/Header.tsx` | 로고 교체, 활성 색상 변경 |
| 4 | `app/layout.tsx` | metadata + lang 업데이트 |
| 5 | `app/page.tsx` | Hero 재구성, 색상 + 텍스트 변경 |
| 6 | `components/ui/TickerSearch.tsx` | 색상 + 텍스트 영문화 |
| 7 | `components/news/DigestCard.tsx` | 색상 + 텍스트 영문화 |
| 8 | `components/news/ArticleList.tsx` | 색상 + 텍스트 영문화 |
| 9 | `app/auth/page.tsx` | 로고 교체 + 텍스트 영문화 |
