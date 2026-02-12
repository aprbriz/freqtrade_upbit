# Upbit Monitor 듀얼 윈도우 UI 리디자인 작업지시서

> Codex CLI 실행용 · engine.py 수정 금지 · ui.py + pc_app_main.py만 수정
> 코인 배치 변경 + 디자인 전면 교체 + 로고 이미지 적용

---

## 1. 목표 (Objective)

듀얼 윈도우의 코인 배치를 변경하고,
테마 가이드 v2의 디자인 시스템(토큰 기반 Light/Dark, 색 분리, 미니멀 운영형)을 적용한다.

### 윈도우 배치

| 윈도우 | 구성 |
|--------|------|
| **Window1** | **BTC (좌 50%) + ETH (우 50%)** 듀얼 차트 |
| **Window2** | **XRP 차트 (좌 65%) + 진단 대시보드 (우 35%)** |

### 헤더 로고

- "Upbit Monitor" 텍스트 대신 **`pc_app/assets/upbit_logo.png` 이미지** 사용
- `QPixmap`으로 로드 → 높이 20px 스케일
- 로고 옆에 "Monitor" 텍스트 (14px Semibold, `text-primary`)
- 로고 로드 실패 시 "UPbit" 텍스트 폴백

---

## 2. 범위 / 비범위

**수정:** `pc_app/ui.py` (전면 재작성), `pc_app/pc_app_main.py` (심볼 변경)
**금지:** engine.py, qt.py, __init__.py, assets/, cloud/, common/ 일체

---

## 2.1 수정 가능한 파일 범위 (ALLOWED FILES)

이번 작업에서 **수정/생성 가능한 파일은 아래 범위로만 제한**한다.

### ✅ 수정/생성 허용

1) PC 앱(UI) 코드
- `user_data/upbit_exchange/pc_app/**`

2) PC 앱 리소스(이미지/아이콘/폰트/스타일 등)
- `user_data/upbit_exchange/pc_app/assets/**`
- `user_data/upbit_exchange/pc_app/resources/**`

3) PC 앱 설정/런처/엔트리포인트(PC 앱 실행에 필요한 것)
- `user_data/upbit_exchange/pc_app_main.py`
- `user_data/upbit_exchange/pc_app/__main__.py`
- `user_data/upbit_exchange/pc_app/*.py`  (단, `pc_app` 하위로 분리되는 경우만)

4) PC 앱 문서(작업지시서/설계/README)
- `user_data/upbit_exchange/pc_app/*.md`
- `user_data/upbit_exchange/pc_app/docs/**`

### ❌ 수정 금지 (FORBIDDEN)

- Cloud Collector 관련 전체: `user_data/upbit_exchange/cloud/**`
- common/ 모듈 원본: `user_data/upbit_exchange/common/**`
  - (PC 앱에서 공통 로직이 필요하면 `common/`을 **직접 참조/수정**하지 말고,
    `pc_app/vendor/`로 복사(vendor)해서 **복사본만** 수정한다.)
- freqtrade 전략/기타: `user_data/strategies/**`, `user_data/freqtrade/**` 등
- 기존 DB/스키마/마이그레이션 변경
- SSOT 문서 내용 변경(이번 작업은 UI 리디자인이며 SSOT는 참고용)

### [새 파일 추가 규칙]

- 새 파일은 `pc_app/` 하위에서만 추가 가능.
- `pc_app/` 외부에 새 파일 추가 금지.
- `pc_app/vendor/`에 복사본을 추가하는 것은 허용(단, 원본 `common/` 수정/직접 참조 금지).


## 3. 데이터 인터페이스 (engine.py — 변경 불가)

### get_snapshot(symbol)
```python
{ "symbol", "display_name", "price", "price_change", "percent_change",
  "candles", "mode", "ws_status", "burst_status", "last_message_age",
  "last_trade_ts", "timeframe_ms" }
```

### get_diagnostics()
```python
{ "now_ms", "symbols": { "KRW-ETH": { "mode","ws","burst","last_trade_ts",
  "last_message_age","total_ticks" }, "KRW-XRP": {...}, "KRW-BTC": {...} } }
```

### 기타: set_active_timeframe, set_symbol_mode, engine.symbols, engine.active_timeframes

---

## 4. 테마 토큰

```python
THEME_LIGHT = {
    "bg-base": "#FFFFFF", "bg-surface": "#F6F7F9", "bg-elevated": "#EDEEF1",
    "bg-tile": "#F0F1F4", "bg-hover": "#E8E9ED",
    "text-primary": "#1A1D24", "text-secondary": "#3D4350",
    "text-tertiary": "#6B7280", "text-quaternary": "#9CA3AF",
    "border-subtle": "#E2E4E9", "border-muted": "#D0D3DA",
    "chart-up": "#E54040", "chart-up-bg": "rgba(229,64,64,0.08)",
    "chart-down": "#3182F6", "chart-down-bg": "rgba(49,130,246,0.08)",
    "chart-grid": "#F0F1F4", "chart-axis": "#9CA3AF",
    "status-ok": "#0D9F61", "status-ok-dim": "rgba(13,159,97,0.08)",
    "status-ok-medium": "rgba(13,159,97,0.15)",
    "status-warn": "#D97706", "status-warn-dim": "rgba(217,119,6,0.07)",
    "status-warn-medium": "rgba(217,119,6,0.14)",
    "status-fail": "#C026D3", "status-fail-dim": "rgba(192,38,211,0.06)",
    "status-fail-medium": "rgba(192,38,211,0.12)",
    "status-inactive": "#9CA3AF",
}
THEME_DARK = {
    "bg-base": "#0F1115", "bg-surface": "#181A20", "bg-elevated": "#1E2028",
    "bg-tile": "#22242C", "bg-hover": "#282A34",
    "text-primary": "#F0F1F4", "text-secondary": "#C2C5CC",
    "text-tertiary": "#818690", "text-quaternary": "#555962",
    "border-subtle": "#2A2D38", "border-muted": "#363944",
    "chart-up": "#EF5350", "chart-up-bg": "rgba(239,83,80,0.10)",
    "chart-down": "#5B9CF6", "chart-down-bg": "rgba(91,156,246,0.10)",
    "chart-grid": "#1E2028", "chart-axis": "#555962",
    "status-ok": "#2DD882", "status-ok-dim": "rgba(45,216,130,0.10)",
    "status-ok-medium": "rgba(45,216,130,0.18)",
    "status-warn": "#F5A623", "status-warn-dim": "rgba(245,166,35,0.10)",
    "status-warn-medium": "rgba(245,166,35,0.18)",
    "status-fail": "#D964E7", "status-fail-dim": "rgba(217,100,231,0.08)",
    "status-fail-medium": "rgba(217,100,231,0.15)",
    "status-inactive": "#555962",
}
```

---

## 5. Window1: BTC + ETH (50:50)

```
┌──────────────────────────────────────────────────────────────────┐
│ [경고 스트립] 조건부 32px                                        │
├──────────────────────────────┬───────────────────────────────────┤
│ [로고img] Monitor ●LIVE ●WS │  ●LIVE ●WS      LIGHT THEME · ⚙ │ 48px
├──────────────────────────────┼───────────────────────────────────┤
│ BTC / KRW · 1분봉            │ ETH / KRW · 1분봉                │
│ 114,451,000 ▲909K (+0.80%) │ 3,432,000 ▲19,500 (+0.57%)      │
│ [타임프레임]                 │ [타임프레임]                      │
│                              │                                  │
│     BTC 캔들 차트             │     ETH 캔들 차트                │
│                              │                                  │
│     BTC 거래량                │     ETH 거래량                   │
├──────────────────────────────┴───────────────────────────────────┤
│ ● Last Tick 0.1s │ Reconnects 0 │ DB Lag 0ms │ Uptime 2m09s    │ 28px
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Window2: XRP (65%) + Dashboard (35%)

```
┌──────────────────────────────────────────────────────────────────┐
│ [경고 스트립] 조건부 32px                                        │
├──────────────────────────────────────────────────────────────────┤
│ [로고img] Monitor ●LIVE ●WS │ ETH 3,432,000 +0.57%            │
│                    ●DB LAG  │ XRP 2,364    −0.26%  ← 선택      │ 48px
│                              │ BTC 114,451K +0.80%             │
│                              │                          ⚙      │
├─────────────────────────────────┬────────────────────────────────┤
│ XRP / KRW · 1분봉               │  상태 요약 KPI 2×3             │
│ 2,364  ▼6 (-0.26%)             │  WS연결·DBLag·수신·Reconn     │
│ [타임프레임]                     │  수신율·에러율                 │
│                                 ├────────────────────────────────┤
│     XRP 캔들 차트                │  커넥션 상세 4행               │
│                                 │  WS ETH/XRP/BTC + DB Write   │
│                                 ├────────────────────────────────┤
│     XRP 거래량                   │  이벤트 타임라인 5건 + 범례   │
├─────────────────────────────────┴────────────────────────────────┤
│ ● Last Tick 0.3s │ Reconnects 0 │ DB Lag 0ms │ Uptime 2m09s     │ 28px
└──────────────────────────────────────────────────────────────────┘
```

W2 코인탭: 기본 선택 = XRP. 탭 클릭 시 좌측 차트 코인 전환.

---

## 7. 로고 로딩 코드

```python
def _load_logo() -> Optional[QtGui.QPixmap]:
    logo_path = Path(__file__).resolve().parent / "assets" / "upbit_logo.png"
    if logo_path.exists():
        px = QtGui.QPixmap(str(logo_path))
        if not px.isNull():
            return px.scaledToHeight(20, QtCore.Qt.SmoothTransformation)
    return None
```

---

## 8. 공통: AlertStrip, FooterBar, Chart 토큰화, 이벤트

AlertStrip: 32px 조건부, 양쪽 동시 표시.
FooterBar: 28px, Last Tick / Reconnects / DB Lag / Uptime.
CandleChart/VolumeChart: 기존 재활용, 색상만 theme.t() 토큰화.
EventStore: WS 상태 변화 감지 → 이벤트 생성, 최근 5건 표시.

---

## 9. pc_app_main.py 변경

```python
def _update_ui(engine, window1, window2):
    window1.btc_area.update_snapshot(engine.get_snapshot("KRW-BTC"))
    window1.eth_area.update_snapshot(engine.get_snapshot("KRW-ETH"))
    window2.xrp_area.update_snapshot(engine.get_snapshot("KRW-XRP"))
    all_snaps = {s: engine.get_snapshot(s) for s in engine.symbols}
    window2.update_dashboard(engine.get_diagnostics(), all_snaps)
    for w in (window1, window2):
        w.footer.update_status(engine.get_diagnostics(), all_snaps)
        w.alert.check_and_update(engine.get_diagnostics())
```

---

## 10. 클래스 구조 / 삭제 대상 / 색 규칙 / 타이포 / 여백

**클래스:** ThemeManager, AlertStrip, HeaderBar, CandleChartWidget, VolumeChartWidget, ChartArea, KpiTile, KpiGrid, ConnectionCard/Section, EventRow/Timeline, DashboardPanel, FooterBar, EventStore, Window1, Window2
**삭제:** TopNavBar, ScrollingTicker, DiagnosticPanel, ChartPanel
**색 규칙:** chart-up/down → 가격만. status-ok/warn/fail → 시스템만. 절대 혼용 금지.
**타이포:** Display 24-34px Bold Mono / Title 14px Semi Sans / Body 12px / Caption 11px Mono
**여백:** 헤더 48px, 하단 28px, 스트립 32px, W1 50:50, W2 65:35, 타일갭 8px 패딩 14px

---

## 11. Done 기준

1. ✅ Window1 = **BTC + ETH** 듀얼 차트
2. ✅ Window2 = **XRP** + Dashboard
3. ✅ 헤더에 **upbit_logo.png 이미지** (텍스트 아님)
4. ✅ Light 기본, ⚙ 클릭 시 양쪽 동시 Dark 전환
5. ✅ W2 코인탭 기본 XRP, 클릭 시 차트 전환
6. ✅ KPI 6개 + 커넥션 4행 + 이벤트 5건 + 범례
7. ✅ 하단 바 + 경고 스트립 양쪽
8. ✅ engine.py 미변경, 차트색 ≠ 시스템색

---

## 12. rgba 헬퍼

```python
import re
def parse_color(s: str) -> QtGui.QColor:
    if s.startswith("rgba("):
        m = re.match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", s.replace(" ",""))
        if m: return QtGui.QColor(int(m[1]),int(m[2]),int(m[3]),int(float(m[4])*255))
    return QtGui.QColor(s)
```
