# WebSocket 구독 최적화 - Raw Trade 전략

## 날짜: 2026-01-28
## 목적: 구독 수 최소화 (3개 고정) + 타임프레임 자유 변경

---

## 1. 기존 방식의 문제점

### 1.1 문제
```
타임프레임별 구독 (비효율):
- XRP 1시간봉 구독
- XRP 5분봉 구독 (타임프레임 변경 시)
→ 동일 심볼을 2번 구독 (불필요)
```

**문제점**:
- 구독 수 증가 (3개 → 최대 6개)
- Upbit API 부담
- Previous/Active 전환 복잡성
- TTL 관리 필요

---

## 2. 새로운 방식: Raw Trade 단일 구독

### 2.1 개념

```
WebSocket은 raw trade만 구독:
- XRP/KRW: trade 이벤트 스트림 (가격, 거래량, 시간)
- BTC/KRW: trade 이벤트 스트림
- ETH/KRW: trade 이벤트 스트림

PC 앱에서 로컬 aggregation:
- trade → TimeframeAggregator → 1분/5분/1시간/일봉...
- 사용자가 타임프레임 변경 시 aggregator만 재설정
- WS 구독은 그대로 유지
```

### 2.2 장점
- ✅ **구독 수 고정**: 항상 3개만 (XRP, BTC, ETH)
- ✅ **타임프레임 무제한**: 로컬에서 자유롭게 생성
- ✅ **Previous/Active 불필요**: 전환 로직 단순화
- ✅ **Cloud와 동일 로직**: common/aggregator 재사용
- ✅ **Upbit API 부담 최소**

---

## 3. 아키텍처

### 3.1 데이터 흐름

```
[Upbit WebSocket]
    ↓ raw trade events
[WS Manager] (3개 구독 고정)
    ↓
[Trade Buffer] (심볼별, 메모리)
    ↓
[MultiAggregator] (심볼별)
    ├─ TimeframeAggregator(1m)   ──→ UI (사용자 선택)
    ├─ TimeframeAggregator(5m)   ──→ UI (사용자 선택)
    ├─ TimeframeAggregator(1h)   ──→ UI (사용자 선택)
    └─ TickAggregator(3tick)     ──→ UI (옵션)
    ↓
[Chart UI] (Window 1, 2)
```

### 3.2 코드 구조

```python
class LiveEngine:
    def __init__(self):
        # WS는 raw trade만
        self.ws_manager = WebSocketManager()
        
        # 심볼별 aggregator
        self.aggregators = {
            'XRP/KRW': MultiAggregator(
                timeframes=[60000, 300000, 3600000],  # 1m, 5m, 1h
                ticks=[3]
            ),
            'BTC/KRW': MultiAggregator(...),
            'ETH/KRW': MultiAggregator(...)
        }
        
        # 현재 선택된 타임프레임 (UI 표시용)
        self.selected_timeframes = {
            'XRP/KRW': 3600000,  # 1h
            'BTC/KRW': 3600000,
            'ETH/KRW': 3600000
        }
    
    def on_trade(self, symbol, trade_data):
        """WS에서 raw trade 수신"""
        # 해당 심볼의 모든 aggregator에 입력
        self.aggregators[symbol].on_trade(trade_data)
    
    def on_candle_flush(self, symbol, timeframe_ms, candle):
        """Aggregator에서 봉 확정 시"""
        # 현재 선택된 타임프레임이면 UI 업데이트
        if timeframe_ms == self.selected_timeframes[symbol]:
            self.update_chart(symbol, candle)
    
    def change_timeframe(self, symbol, new_timeframe_ms):
        """타임프레임 변경 (WS 구독 변경 없음!)"""
        # 1. 선택 변경
        self.selected_timeframes[symbol] = new_timeframe_ms
        
        # 2. DB에서 historical 데이터 로드
        historical = self.db_reader.get_candles(
            symbol, new_timeframe_ms, limit=200
        )
        
        # 3. UI 업데이트
        self.render_chart(symbol, historical)
        
        # 4. 이후 LIVE는 on_candle_flush에서 자동 업데이트
```

---

## 4. 타임프레임 변경 시나리오

### 4.1 시나리오: BTC 1시간 → 5분 변경

**기존 방식** (비효율):
```
1. BTC 5분봉 WS 구독 시작 (Active)
2. BTC 1시간봉 WS 유지 (Previous, TTL 30초)
3. DB에서 5분봉 historical 로드
4. LIVE 5분봉 수신 시작
5. 30초 후 1시간봉 구독 해제
→ 총 2개 구독 (30초간)
```

**새 방식** (효율):
```
1. selected_timeframes['BTC/KRW'] = 300000 (5분)
2. DB에서 5분봉 historical 로드
3. UI 즉시 업데이트
4. Aggregator는 이미 5분봉도 생성 중 → 다음 flush 시 UI 업데이트
→ WS 구독 변경 없음, 0.1초 만에 전환
```

### 4.2 MultiAggregator 활용

```python
# Cloud collector의 common/multi_aggregator.py 재사용
class MultiAggregator:
    def __init__(self, timeframes_ms, tick_sizes):
        # 모든 타임프레임 aggregator 동시 생성
        self.timeframe_aggs = {
            tf: TimeframeAggregator(tf) for tf in timeframes_ms
        }
        self.tick_aggs = {
            tick: TickAggregator(tick) for tick in tick_sizes
        }
    
    def on_trade(self, trade):
        # 모든 aggregator에 동일한 trade 입력
        for agg in self.timeframe_aggs.values():
            agg.on_trade(trade)
        for agg in self.tick_aggs.values():
            agg.on_trade(trade)
```

**장점**:
- 타임프레임 추가 시 aggregator만 추가
- WS 구독 변경 불필요
- Cloud와 동일한 로직 (검증됨)

---

## 5. 메모리 관리

### 5.1 우려: 모든 타임프레임을 동시 생성하면 메모리 증가?

**답**: 제한적 증가, 관리 가능

```python
class TimeframeAggregator:
    def __init__(self, timeframe_ms, max_store=1000):
        self.candles = {}  # pair → deque(maxlen=max_store)
        self.max_store = max_store
```

**메모리 계산**:
- 1개 캔들: ~100 bytes (OHLCV + 메타데이터)
- 1000개 캔들: ~100 KB
- 3개 심볼 × 5개 타임프레임 × 1000개: ~1.5 MB
→ **매우 작음, 무시 가능**

### 5.2 최적화 전략

**옵션 A: 모든 타임프레임 항상 생성** (권장)
- 장점: 타임프레임 변경 즉시 (0초)
- 단점: 메모리 약간 증가 (~1.5 MB)
- 적용: 메모리 충분한 환경 (보통 8GB+)

**옵션 B: 선택된 타임프레임만 생성**
- 장점: 메모리 최소화
- 단점: 타임프레임 변경 시 약간 지연 (1~2초)
- 적용: 메모리 제약 환경 (드물음)

**옵션 C: 하이브리드**
```python
# 자주 쓰는 타임프레임만 사전 생성
PRELOAD_TIMEFRAMES = [60000, 300000, 3600000]  # 1m, 5m, 1h
ON_DEMAND_TIMEFRAMES = [86400000]  # 일봉 (요청 시 생성)
```

---

## 6. DB 조회 전략

### 6.1 타임프레임 변경 시

```python
def change_timeframe(self, symbol, new_tf_ms):
    # 1. DB에서 historical 로드
    #    (Cloud collector가 이미 해당 타임프레임 저장 중)
    candles = self.db_reader.get_candles(
        symbol=symbol,
        timeframe_ms=new_tf_ms,
        limit=200,  # 차트에 표시할 개수
        end_ts=now_ms()
    )
    
    # 2. UI 렌더링
    self.render_chart(symbol, candles)
    
    # 3. LIVE 오버레이 활성화
    #    (Aggregator가 이미 생성 중인 봉을 overlay)
    self.enable_live_overlay(symbol, new_tf_ms)
```

### 6.2 DB vs LIVE 우선순위

```
[DB] ─────────────────────────┐
                               ↓ (historical, closed candles)
                            [Chart]
                               ↑ (real-time, last candle)
[LIVE Aggregator] ────────────┘
```

- **과거 봉**: DB에서 (확정된 데이터)
- **마지막 봉**: LIVE Aggregator에서 (실시간 업데이트)
- **전환 지점**: cutover_ts로 명확히 구분

---

## 7. Cloud Collector와의 차이

### 7.1 Cloud Collector (현재)
```
목적: 24/7 데이터 수집 및 저장
구조:
- ShortCollector: 0.5s, 1s, 3tick → DB
- MidCollector: 10s, 1m → DB
- LongCollector: 10m → DB
각 Collector는 독립 WS
```

### 7.2 PC App (새 설계)
```
목적: 실시간 차트 표시
구조:
- 3개 WS: raw trade만 (XRP, BTC, ETH)
- MultiAggregator: 로컬에서 모든 타임프레임 생성
- DB: historical 조회 전용
타임프레임은 로컬에서 자유롭게 변경
```

### 7.3 공통점
- ✅ `common/timeframe_aggregator.py` 재사용
- ✅ `common/tick_aggregator.py` 재사용
- ✅ `common/dedup_cache.py` 재사용
- ✅ 동일한 aggregation 로직 (검증됨)

---

## 8. 구현 예시

### 8.1 WebSocketManager (간소화)

```python
class WebSocketManager:
    def __init__(self, symbols):
        self.symbols = symbols  # ['XRP/KRW', 'BTC/KRW', 'ETH/KRW']
        self.connection = None
        self.on_trade_callback = None
    
    def connect(self):
        """단일 연결, 3개 심볼 구독"""
        self.connection = websocket.WebSocketApp(
            "wss://api.upbit.com/websocket/v1",
            on_message=self._on_message
        )
        
        # 구독 메시지 전송
        subscribe_msg = [
            {"ticket": "UNIQUE_TICKET"},
            {
                "type": "trade",
                "codes": self.symbols,
                "isOnlyRealtime": True
            }
        ]
        self.connection.send(json.dumps(subscribe_msg))
    
    def _on_message(self, ws, message):
        """Raw trade 수신"""
        data = json.loads(message)
        symbol = data['code']
        
        # Callback으로 전달
        if self.on_trade_callback:
            self.on_trade_callback(symbol, data)
```

### 8.2 LiveEngine

```python
class LiveEngine:
    def __init__(self):
        self.symbols = ['KRW-XRP', 'KRW-BTC', 'KRW-ETH']
        
        # WS Manager (3개 심볼, raw trade만)
        self.ws_manager = WebSocketManager(self.symbols)
        self.ws_manager.on_trade_callback = self.on_trade
        
        # MultiAggregator (심볼별)
        self.aggregators = {}
        for symbol in self.symbols:
            self.aggregators[symbol] = MultiAggregator(
                timeframes_ms=[60000, 300000, 900000, 3600000],  # 1m, 5m, 15m, 1h
                tick_sizes=[3, 10],
                on_candle_callback=lambda s, tf, c: self.on_candle(s, tf, c)
            )
        
        # 현재 UI 표시 중인 타임프레임
        self.active_timeframes = {
            'KRW-XRP': 3600000,  # 1h
            'KRW-BTC': 3600000,
            'KRW-ETH': 3600000
        }
    
    def on_trade(self, symbol, trade_data):
        """WS로부터 raw trade 수신"""
        # 중복 제거
        if self.dedup_cache.is_duplicate(symbol, trade_data):
            return
        
        # 해당 심볼의 모든 aggregator에 입력
        self.aggregators[symbol].on_trade(trade_data)
    
    def on_candle(self, symbol, timeframe_ms, candle):
        """Aggregator로부터 봉 확정"""
        # 현재 활성화된 타임프레임인 경우에만 UI 업데이트
        if timeframe_ms == self.active_timeframes.get(symbol):
            self.ui_manager.update_chart(symbol, candle)
    
    def change_timeframe(self, symbol, new_timeframe_ms):
        """타임프레임 변경 (WS 구독 변경 없음!)"""
        # 1. 활성 타임프레임 변경
        self.active_timeframes[symbol] = new_timeframe_ms
        
        # 2. DB에서 historical 로드
        historical = self.db_reader.get_candles(
            symbol, new_timeframe_ms, limit=200
        )
        
        # 3. UI 전체 재렌더링
        self.ui_manager.render_full_chart(symbol, historical)
        
        # 4. 이후 LIVE 업데이트는 on_candle에서 자동
```

---

## 9. 성능 비교

### 9.1 구독 수
| 방식 | 정상 | 변경 중 | 최악 |
|------|------|---------|------|
| 기존 (타임프레임별) | 3개 | 4~5개 | 6개 |
| **새 방식 (raw trade)** | **3개** | **3개** | **3개** |

### 9.2 전환 속도
| 방식 | 타임프레임 변경 시간 |
|------|----------------------|
| 기존 | 1~2초 (WS 재구독) |
| **새 방식** | **0.1초 (즉시)** |

### 9.3 메모리
| 방식 | 메모리 사용 |
|------|------------|
| 기존 | ~500 KB |
| **새 방식** | **~1.5 MB** (+1 MB) |

---

## 10. 권장 사항

### ✅ 채택: Raw Trade 단일 구독 방식

**이유**:
1. 구독 수 최소화 (3개 고정)
2. Upbit API 부담 최소
3. 타임프레임 변경 즉시 (0.1초)
4. Cloud와 동일 로직 재사용
5. 메모리 증가 미미 (+1 MB)

**구현 우선순위**:
- Phase 1: WebSocketManager (raw trade 3개만)
- Phase 1: MultiAggregator 통합
- Phase 2: DB historical 조회
- Phase 2: LIVE overlay 전환

---

마지막 업데이트: 2026-01-28
다음 단계: WEBSOCKET_STRATEGY.md 교체
