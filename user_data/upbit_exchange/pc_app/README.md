# Upbit Real-Time Chart PC App

**Windows PC용 실시간 차트 앱** - 업비트 트레이딩 전용 듀얼 모니터 차트

## 📊 개요

### 핵심 기능

- **평시**: Oracle Cloud DB (SQLite) 읽기 전용 조회
- **폭주(BURST)**: Upbit WebSocket 직접 구독 + LIVE 오버레이
- **듀얼 모니터**: 모니터 1(XRP+BTC), 모니터 2(ETH+진단패널)
- **Raw Trade 단일 구독**: 3개 심볼 고정, 타임프레임 0.1초 전환
- **업비트 유사 UI**: 마지막 봉이 틱 단위로 실시간 갱신

### 모드

- **DB_ONLY**: 평시 DB 조회 (안정)
- **LIVE_ACTIVE**: BURST 감지 후 실시간 WS 구독
- **섞임 방지**: context_id + generation_id 기반 격리

---

## 🚀 빠른 시작 (Windows PC)

**⭐ 상세 가이드**: `WINDOWS_SETUP.md` 참조

```powershell
# 1. Python 3.8+ 설치 확인
python --version

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 실행
python pc_app_main.py
```

---

## 📁 파일 구조

```
pc_app/
├── pc_app_main.py          # 엔트리포인트
├── engine.py               # MainEngine (WS + Aggregation + BURST)
├── ui.py                   # PyQt5 UI (듀얼 모니터)
├── qt.py                   # PyQt5/PySide6 호환 레이어
├── requirements.txt        # 의존성
├── README.md              # 이 파일
├── WINDOWS_SETUP.md       # Windows 설치 가이드 ⭐
├── DESIGN_DUAL_MONITOR.md # 듀얼 모니터 상세 설계
└── WEBSOCKET_OPTIMIZATION.md # WebSocket 최적화 전략
```

---

## 🖥️ 듀얼 모니터 레이아웃

### 모니터 1 (메인 트레이딩)
- 좌측 50%: **XRP** 차트
- 우측 50%: **BTC** 차트
- 각 차트: 헤더 + 컨트롤 + 캔들차트 + 거래량 + 티커

### 모니터 2 (ETH + 진단)
- 좌측 80%: **ETH** 차트
- 우측 20%: **통합 진단 패널** (3개 심볼 상태)

### 단일 모니터 폴백
- 자동 상하 분할
- 탭/스택 모드

---

## ⚙️ 설정

### config.json (자동 생성)

```json
{
  "db_path": "ohlcv_short.sqlite",
  "ws_url": "wss://api.upbit.com/websocket/v1",
  "symbols": ["KRW-XRP", "KRW-BTC", "KRW-ETH"],
  "logo_path": "assets/upbit_logo.png",
  "window_positions": {
    "window1": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "window2": {"x": 1920, "y": 0, "width": 1920, "height": 1080}
  }
}
```

### 로그

`%LOCALAPPDATA%\UpbitRealTimeChart\logs\app.log`

---

## 🎯 사용 방법

### 기본 조작

1. **타임프레임 선택**: 드롭다운에서 1분/5분/15분/1시간/일봉
2. **LIVE 모드**: 진단 패널에서 "LIVE 시작" 버튼
3. **DB 전환**: "DB로 전환(안정)" 버튼
4. **BURST ACK**: BURST 알림 확인 버튼

### 상태 칩 (우측 상단)

- **MODE**: DB_ONLY / LIVE_ACTIVE
- **WS**: OK / RECONNECTING / DEGRADED
- **BURST**: NORMAL / CANDIDATE / ACTIVE

---

## 🔧 기술 스택

- **GUI**: PyQt5 / PySide6
- **WebSocket**: websocket-client
- **Aggregation**: common/MultiAggregator 재사용
- **DB**: SQLite (읽기 전용, mode=ro)
- **Architecture**: 단일 프로세스, 2개 독립 창

---

## 📚 참조 문서

### 이 디렉토리
- `WINDOWS_SETUP.md` ⭐ - **Windows 설치/실행 가이드**
- `DESIGN_DUAL_MONITOR.md` - 듀얼 모니터 상세 설계
- `WEBSOCKET_OPTIMIZATION.md` - WebSocket 최적화 전략
- `WEBSOCKET_STRATEGY.md` (v2.0) - WS 구독 전략
- `DUAL_MONITOR_SUMMARY.md` - 변경 요약

### 상위 문서
- `../docs/ssot/SSOT_*.md` - 전체 프로젝트 SSOT
- `../upbit_exchange_memo/phase2 작업시지서.md.md` - Phase 2.5 작업지시서

---

## ⚠️ 주의사항

- **PC 앱은 읽기 전용**: DB 수정하지 않음
- **Cloud Collector가 정본**: PC 앱은 조회/모니터링 전용
- **LIVE 모드는 일시적**: BURST 종료 후 자동 DB 복귀
- **24/7 실행 비권장**: 트레이딩 시간만 실행 권장
- **로고 파일 필요**: `assets/upbit_logo.png`에 로고 파일을 복사해야 함

---

## 🐛 문제 해결

`WINDOWS_SETUP.md`의 "문제 해결" 섹션 참조

---

**상태**: Phase 2.5 구현 완료 ✅ (2026-01-28)  
**다음 단계**: Windows PC 테스트 및 피드백
