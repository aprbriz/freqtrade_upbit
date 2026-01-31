# PC 차트 앱 - 듀얼 모니터 UI 설계

## 버전: v1.0
## 날짜: 2026-01-28
## 대상: 듀얼 모니터 트레이더 (기본값)

---

## 1. 개요

### 목적
- **Windows PC 듀얼 모니터 환경 최적화**
- BTC, ETH, XRP 3개 심볼 동시 모니터링
- 폭주 시 실시간 대응 극대화

### 원칙
- 듀얼 모니터를 **기본(default)** 전제
- 단일 프로세스에서 2개 창 관리
- 창 간 데이터 동기화 (context_id 기반)
- UI 프리징 0, 리소스 누수 0

---

## 2. 듀얼 모니터 레이아웃

### 2.1 전체 구성

```
[모니터 1 - 메인 트레이딩]    [모니터 2 - ETH + 진단]
┌────────────┬────────────┐   ┌────────────┬────────────┐
│            │            │   │            │            │
│    XRP     │    BTC     │   │    ETH     │   진단     │
│   차트     │   차트     │   │   차트     │   패널     │
│            │            │   │            │            │
│            │            │   │            │            │
└────────────┴────────────┘   └────────────┴────────────┘
   하단 티커 (공통)               하단 티커 (공통)
```

### 2.2 모니터 1 (메인 트레이딩 창)

**크기**: 1920x1080 (Full HD)
**심볼**: XRP, BTC (좌우 50:50 분할)

**각 차트 구성**:
- 상단: 심볼 헤더 (가격, 등락률, Upbit 로고)
- 컨트롤 바:
  - 타임프레임 드롭다운
  - 틱 레이어 ON/OFF
  - 상태 칩 3개: MODE, WS, BURST
- 차트 영역: 캔들스틱 + 가격 레이블
- 하단: 거래량 차트

**하단 티커**:
- Coalesce, 틱 드랍, Overlay 축소, DB 강등 안내

### 2.3 모니터 2 (ETH + 진단 패널)

**크기**: 1920x1080 (Full HD)
**레이아웃**: ETH 차트 (좌 60%) + 진단 패널 (우 40%)

**ETH 차트 (좌측)**:
- 모니터 1의 차트와 동일 구성
- 독립적인 타임프레임 선택 가능

**통합 진단 패널 (우측)**:
- **현재 컨텍스트**: 3개 심볼 모두의 상태 요약
- **타임스탬프 정보**:
  - Now (KST)
  - last_tick_trade_ts (심볼별, KST)
  - last_message_age (심볼별)
- **오버레이 정보**:
  - cutover_ts (KST)
  - overlay 범위 (start/end, horizon, max_candles)
  - DB catch-up 상태 (db_latest_ts vs overlay_latest_final_ts)
- **데이터 정합성**:
  - invalid_trades (심볼별)
  - ooo_corrected / ooo_dropped (심볼별)
- **WS 연결 상태**:
  - connected_since (심볼별)
  - 최근 에러 1줄 (심볼별)
  - reconnect_attempts_in_window (심볼별)
- **재연결/쿨다운 타이머**:
  - 대기 남은 시간
  - 상태 이유 1줄
- **BURST 지표** (심볼별):
  - tick_rate, notional_rate, abs_return_rate
  - gate pass/fail 상태
- **최근 갭 이벤트**: 3개 (있으면)

**행동 버튼 3개**:
1. `LIVE 시작/유지` (심볼 선택 가능)
2. `DB로 전환(안정)` (심볼 선택 가능)
3. `BURST 알림 ACK` (전체)

---

## 3. 기술 아키텍처

### 3.1 프로세스 구조

```
단일 Python 프로세스
├─ MainEngine (공유 데이터 레이어)
│   ├─ DB Reader (SQLite 읽기)
│   ├─ WS Manager (Upbit WebSocket)
│   │   ├─ Primary Connection (3~5개 심볼)
│   │   └─ Secondary Connection (전환용, 임시)
│   ├─ BURST Detector (심볼별 독립)
│   ├─ Overlay Manager (심볼별 메모리)
│   └─ State Machine (심볼별 + 전역)
│
├─ Window1 (메인 트레이딩)
│   ├─ XRP Chart UI
│   └─ BTC Chart UI
│
└─ Window2 (ETH + 진단)
    ├─ ETH Chart UI
    └─ Diagnostic Panel UI
```

### 3.2 WebSocket 구독 전략

**기본 구독** (정상 상태):
- XRP/KRW, BTC/KRW, ETH/KRW (3개 심볼)
- 1개 WebSocket 연결로 충분
- 각 심볼은 독립적인 context_id, generation_id

**타임프레임 변경 시** ("Active + Previous" 정책):
- 변경된 심볼만 일시적으로 2개 구독
- 예: BTC 타임프레임 변경 → XRP(1), BTC(2), ETH(1) = 총 4개
- TTL 후 Previous 자동 폐기 → 3개로 복귀

**최악의 경우** (3개 심볼 동시 변경):
- 최대 6개 구독 (각 심볼당 Active + Previous)
- Upbit 제한(연결당 5개) 초과 → 2개 연결 사용
- 또는 Previous 즉시 폐기로 대응

**상세**: `pc_app/WEBSOCKET_STRATEGY.md` 참조

### 3.2 창 관리

**멀티 윈도우 프레임워크**:
- PyQt5/PySide6 또는 Tkinter (멀티 윈도우 지원)
- 각 창은 독립 QMainWindow/Toplevel

**창 간 통신**:
- 공유 메모리: MainEngine의 데이터 스냅샷
- Qt Signals/Slots 또는 threading.Event
- 갱신 주기: 20~60Hz (UI 렌더링 주기)

**창 위치 저장**:
- 설정 파일에 각 창의 위치/크기 저장
- 앱 시작 시 자동으로 듀얼 모니터 배치
- 단일 모니터 환경 시 자동 폴백 (탭/스택 모드)

### 3.3 데이터 동기화

**context_id 기반 격리**:
- 각 심볼은 독립 context_id
- 심볼/타임프레임 변경 시 새 context_id 발급
- UI는 Active context_id만 렌더

**generation_id 관리**:
- WS 재연결 시 generation_id 증가
- Overlay/Aggregator는 현재 generation만 처리
- generation 변경 시 자동 reset

**스냅샷 coalesce**:
- 백그라운드: 최신 스냅샷 계속 갱신
- UI: 최신 1개만 소비 (중간 프레임 버림)
- coalesce 발생 시 티커 안내

---

## 4. 창별 상세 설계

### 4.1 Window 1 - 메인 트레이딩 창

**제목**: `Upbit Monitor - XRP & BTC`

**레이아웃**:
```
┌─────────────────────────────────────────┐
│ [×] XRP (2,338원)    │ [×] BTC (137,845,000원)
├───────────────────────┼─────────────────┤
│ [1시간] [✓틱]        │ [1시간] [✓틱]   │
│ [LIVE][WS:OK][NORMAL]│ [LIVE][WS:OK].. │
├───────────────────────┼─────────────────┤
│                       │                 │
│   XRP 차트 영역       │  BTC 차트 영역  │
│                       │                 │
│   (캔들스틱)          │  (캔들스틱)     │
│                       │                 │
├───────────────────────┼─────────────────┤
│   거래량              │  거래량         │
└───────────────────────┴─────────────────┘
│ [!] 시스템 정상 작동 중 | Coalesce: 0  │
└─────────────────────────────────────────┘
```

**특징**:
- XRP, BTC 동시 모니터링
- 폭주 시 즉시 대응 가능
- 각 차트는 독립적인 타임프레임

### 4.2 Window 2 - ETH + 진단 패널

**제목**: `Upbit Monitor - ETH & Diagnostics`

**레이아웃**:
```
┌──────────────────────────┬────────────────┐
│ [×] ETH (3,421,000원)    │  진단 패널     │
├──────────────────────────┤                │
│ [1시간] [✓틱]            │ ▼ 현재 컨텍스트│
│ [LIVE][WS:OK][NORMAL]    │ XRP: LIVE/OK   │
├──────────────────────────┤ BTC: LIVE/OK   │
│                          │ ETH: LIVE/OK   │
│   ETH 차트 영역          │                │
│                          │ ▼ 시간 정보    │
│   (캔들스틱)             │ Now: 16:30:45  │
│                          │ XRP age: 0.3s  │
│                          │ BTC age: 0.1s  │
├──────────────────────────┤ ETH age: 0.2s  │
│   거래량                 │                │
│                          │ ▼ BURST 지표   │
│                          │ XRP: NORMAL    │
│                          │ BTC: CANDIDATE │
│                          │ ETH: NORMAL    │
│                          │                │
│                          │ ▼ 행동 버튼    │
│                          │ [LIVE 시작]    │
│                          │ [DB 전환]      │
│                          │ [ACK]          │
└──────────────────────────┴────────────────┘
│ [!] 시스템 정상 작동 중                   │
└───────────────────────────────────────────┘
```

**특징**:
- ETH 차트 + 통합 진단 패널
- 3개 심볼 전체 상태 한눈에 파악
- 즉시 행동 가능 (버튼 제공)

---

## 5. UI 렌더링 규칙

### 5.1 렌더링 주기

**백그라운드 (MainEngine)**:
- Every tick으로 데이터 갱신
- 스냅샷 생성: 최신 상태만 유지

**UI 렌더링**:
- 고정 주기: 20~60Hz
- 최신 스냅샷 1개만 소비
- 중간 프레임 coalesce (버림)

### 5.2 성능 디그레이드

**폭주 시 우선순위**:
1. 표시용 틱 레이어 드랍 (시각화 희생)
2. 중간 스냅샷 coalesce (프레임 생략)
3. 진단 패널 갱신 빈도 다운 (60Hz→30Hz→10Hz)
4. 오버레이 범위 축소 (최근 구간만)
5. Previous-WARM 구독 해제 (리소스 압력 시)

**캔들(OHLCV) 자체는 최후까지 유지** (트레이딩 핵심)

### 5.3 하단 티커 안내

**표시 우선순위** (높은 것 우선):
1. 비상전환 (DB 강등)
2. 오버레이 축소
3. 스냅샷 coalesce
4. 표시용 틱 드랍

**표시 방식**:
- 좌→우 스크롤
- 1줄 유지 (누적 금지)
- 연속 발생은 카운트로 흡수

---

## 6. 상태 동기화

### 6.1 공유 상태

**MainEngine이 관리**:
- `symbol_states`: XRP, BTC, ETH 각각의 DataSourceMode
- `ws_connections`: 3개 심볼의 WS 연결 상태
- `burst_detectors`: 3개 심볼의 BURST 상태
- `overlay_managers`: 3개 심볼의 메모리 오버레이
- `db_reader`: 공유 SQLite 읽기 전용 연결

### 6.2 창 간 동기화

**갱신 트리거**:
- MainEngine → Signals/Events 발생
- 각 창은 Signals 구독
- 최신 스냅샷 fetch → UI 갱신

**예시 (PyQt5)**:
```python
class MainEngine(QObject):
    snapshot_updated = pyqtSignal(str, dict)  # (symbol, snapshot)
    
    def update_snapshot(self, symbol):
        snapshot = self._get_latest_snapshot(symbol)
        self.snapshot_updated.emit(symbol, snapshot)

class Window1(QMainWindow):
    def __init__(self, engine):
        self.engine = engine
        self.engine.snapshot_updated.connect(self.on_snapshot)
    
    def on_snapshot(self, symbol, snapshot):
        if symbol == 'XRP':
            self.xrp_chart.update(snapshot)
        elif symbol == 'BTC':
            self.btc_chart.update(snapshot)
```

---

## 7. 창 위치 관리

### 7.1 설정 파일 (config.yml)

```yaml
windows:
  window1:
    x: 0
    y: 0
    width: 1920
    height: 1080
    monitor: 0  # 메인 모니터
  
  window2:
    x: 1920
    y: 0
    width: 1920
    height: 1080
    monitor: 1  # 서브 모니터

charts:
  window1:
    - symbol: XRP
      position: left
      timeframe: 1h
    - symbol: BTC
      position: right
      timeframe: 1h
  
  window2:
    - symbol: ETH
      position: left
      timeframe: 1h
```

### 7.2 단일 모니터 폴백

**자동 감지**:
- 시스템 모니터 수 체크 (PyQt: QApplication.screens())
- 단일 모니터 시 자동 폴백 모드

**폴백 모드 옵션**:
1. **탭 모드**: Window1과 Window2를 탭으로 전환
2. **스택 모드**: 상하 배치 (Window1 위, Window2 아래)
3. **오버랩 모드**: 창 겹치기 (Alt+Tab으로 전환)

---

## 8. 구현 우선순위

### Phase 1 (MVP)
- [ ] MainEngine 기본 구조 (DB 읽기, WS 구독)
- [ ] Window1 구현 (XRP, BTC 듀얼 차트)
- [ ] 기본 상태 칩 (MODE, WS, BURST)
- [ ] 하단 티커 구현

### Phase 2 (진단 패널)
- [ ] Window2 구현 (ETH 차트)
- [ ] 통합 진단 패널 (우측)
- [ ] 행동 버튼 3개
- [ ] 창 간 동기화 완성

### Phase 3 (고급 기능)
- [ ] BURST 감지 완성 (2단계 게이트)
- [ ] LIVE 오버레이 범위 최적화
- [ ] 표시용 틱 레이어 decimation
- [ ] 성능 디그레이드 정책

### Phase 4 (안정화)
- [ ] 24시간 테스트
- [ ] 메모리 누수 제거
- [ ] 창 위치 저장/복원
- [ ] 단일 모니터 폴백 구현

---

## 9. 참고 문서

- **WebSocket 구독 전략**: `pc_app/WEBSOCKET_STRATEGY.md` ✅ 신규
- **전체 요구사항**: `phase2 작업지시서.md.md`
- **UI 프로토타입**: `dual-chart-monitor.html`
- **SSOT**: Cloud Collector 정책 (공유)

---

마지막 업데이트: 2026-01-28
다음 단계: Phase 1 MVP 구현
