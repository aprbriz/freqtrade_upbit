# WebSocket 구독 전략 - 최적화 버전 (Raw Trade)

## 날짜: 2026-01-28
## 버전: v2.0 (최적화)
## 대상: PC 차트 앱 (XRP, BTC, ETH 3개 심볼)

---

## ⚠️ 중요: 전략 변경

**기존 v1.0**: 타임프레임별 구독 (비효율, 최대 6개)
**새 v2.0**: Raw trade 단일 구독 (효율, 항상 3개) ✅ 채택

**상세**: `WEBSOCKET_OPTIMIZATION.md` 참조

---

## 1. 핵심 전략: Raw Trade 단일 구독

### 1.1 개념
```
WebSocket: 3개 심볼의 raw trade만 구독
├─ XRP/KRW: trade 이벤트 스트림
├─ BTC/KRW: trade 이벤트 스트림
└─ ETH/KRW: trade 이벤트 스트림

로컬 Aggregation: PC 앱에서 타임프레임 생성
└─ MultiAggregator → 1m/5m/15m/1h/일봉...
```

### 1.2 장점
- ✅ **구독 수 고정**: 항상 3개 (심볼당 1개)
- ✅ **타임프레임 무제한**: 로컬에서 자유롭게
- ✅ **전환 즉시**: 0.1초 (WS 재구독 불필요)
- ✅ **Upbit API 부담 최소**
- ✅ **Cloud 로직 재사용**: common/aggregator

---

## 2. 데이터 흐름

```
[Upbit WebSocket]
    ↓ raw trade events (3개 심볼)
[WebSocketManager]
    ↓
[Trade Buffer] (중복 제거)
    ↓
[MultiAggregator] (심볼별)
    ├─ TimeframeAggregator(1m)
    ├─ TimeframeAggregator(5m)
    ├─ TimeframeAggregator(1h)
    └─ TickAggregator(3tick)
    ↓
[Chart UI] (선택된 타임프레임만 표시)
```

---

## 3. 타임프레임 변경

### 3.1 기존 방식 (v1.0, 비효율)
```
BTC 1시간 → 5분 변경:
1. BTC 5분봉 WS 구독 시작 (Active)
2. BTC 1시간봉 WS 유지 (Previous, TTL)
3. DB historical 로드
4. 30초 후 1시간봉 구독 해제
→ 구독 수 증가, 복잡한 전환 로직
```

### 3.2 새 방식 (v2.0, 효율)
```
BTC 1시간 → 5분 변경:
1. active_timeframes['BTC'] = 300000
2. DB historical 로드
3. UI 즉시 업데이트
4. Aggregator는 이미 5분봉 생성 중
→ WS 구독 변경 없음, 0.1초 전환
```

---

## 4. 구현 핵심

### 4.1 WebSocketManager (간소화)
```python
class WebSocketManager:
    def __init__(self, symbols=['KRW-XRP', 'KRW-BTC', 'KRW-ETH']):
        self.symbols = symbols
        self.connection = None  # 단일 연결
    
    def connect(self):
        # 3개 심볼, raw trade만 구독
        subscribe_msg = [{
            "type": "trade",
            "codes": self.symbols
        }]
```

### 4.2 LiveEngine
```python
class LiveEngine:
    def __init__(self):
        # WS: raw trade 3개만
        self.ws_manager = WebSocketManager()
        
        # Aggregator: 모든 타임프레임 동시 생성
        self.aggregators = {
            symbol: MultiAggregator(
                timeframes_ms=[60000, 300000, 3600000]
            ) for symbol in symbols
        }
        
        # UI 표시용 선택
        self.active_timeframes = {
            'KRW-XRP': 3600000  # 1h
        }
    
    def change_timeframe(self, symbol, new_tf):
        # WS 구독 변경 없음!
        self.active_timeframes[symbol] = new_tf
        self.render_chart(symbol, new_tf)
```

---

## 5. 메모리 관리

### 5.1 메모리 계산
```
1개 캔들: ~100 bytes
1000개 캔들: ~100 KB
3 심볼 × 5 타임프레임 × 1000개: ~1.5 MB
→ 무시 가능한 수준
```

### 5.2 전략
- **권장**: 모든 타임프레임 항상 생성
- **메모리 제약 시**: 선택된 타임프레임만 생성

---

## 6. Cloud Collector와 비교

| 항목 | Cloud Collector | PC App |
|------|----------------|--------|
| 목적 | 24/7 데이터 수집 | 실시간 차트 표시 |
| WS 구독 | Collector별 독립 | 3개 raw trade 고정 |
| Aggregation | 서버에서 (DB 저장) | 로컬에서 (메모리) |
| 타임프레임 | 고정 (short/mid/long) | 자유 변경 |
| 공통점 | common/aggregator 로직 동일 ✅ |

---

## 7. 성능 비교

| 방식 | 구독 수 | 전환 시간 | 메모리 |
|------|---------|----------|--------|
| v1.0 (타임프레임별) | 3~6개 | 1~2초 | 500 KB |
| **v2.0 (raw trade)** | **3개** | **0.1초** | **1.5 MB** |

---

## 8. 구현 우선순위

### Phase 1 (MVP)
- [ ] WebSocketManager (raw trade 3개)
- [ ] MultiAggregator 통합
- [ ] 기본 타임프레임 (1m, 5m, 1h)

### Phase 2 (완성)
- [ ] DB historical 조회
- [ ] LIVE overlay 전환
- [ ] 모든 타임프레임 지원

---

## 9. 참고 문서

- **상세 최적화**: `WEBSOCKET_OPTIMIZATION.md` ✅ 필독
- **듀얼 모니터 설계**: `DESIGN_DUAL_MONITOR.md`
- **전체 요구사항**: `phase2 작업지시서.md.md`

---

마지막 업데이트: 2026-01-28 (v2.0 최적화)
채택: Raw Trade 단일 구독 방식 ✅


---

## 1. 기본 구독 전략

### 1.1 시작 시 구독
```python
# PC App 시작 시 자동 구독
ws_subscriptions = {
    'XRP/KRW': {
        'connection': ws_conn_1,
        'timeframe': '1h',  # 사용자 설정값
        'context_id': 'xrp_001',
        'generation_id': 1
    },
    'BTC/KRW': {
        'connection': ws_conn_1,
        'timeframe': '1h',
        'context_id': 'btc_001',
        'generation_id': 1
    },
    'ETH/KRW': {
        'connection': ws_conn_1,
        'timeframe': '1h',
        'context_id': 'eth_001',
        'generation_id': 1
    }
}
```

**정상 상태**: 3개 구독 (1개 WebSocket 연결로 충분)

---

## 2. 타임프레임 변경 시

### 2.1 "Active + Previous" 정책 (심볼별 독립)

기존 phase2 작업지시서의 "2개 동시 구독" 정책을 심볼별로 적용:

```
사용자가 BTC 타임프레임 변경 (1h → 5m):

[변경 직후]
XRP: 1개 (1h-Active)
BTC: 2개 (1h-Previous + 5m-Active)  ← 전환 중
ETH: 1개 (1h-Active)
총: 4개 구독

[TTL 후 Previous 폐기]
XRP: 1개 (1h-Active)
BTC: 1개 (5m-Active)  ← Previous 폐기됨
ETH: 1개 (1h-Active)
총: 3개 구독 (정상 복귀)
```

### 2.2 TTL (Time To Live) 설정
- **기본 TTL**: 10~30초 (설정 가능)
- **목적**: 전환 시 차트가 깜빡이지 않고 부드럽게 이어짐
- **폐기 조건**:
  - TTL 시간 경과
  - 새 타임프레임(Active)의 데이터가 충분히 쌓임 (예: 최소 10개 봉)
  - 리소스 압력 시 즉시 폐기 (우선순위 5)

---

## 3. 최악의 경우: 동시 변경

### 3.1 시나리오
사용자가 3개 심볼을 거의 동시에 변경:

```
XRP: 1h → 5m
BTC: 1h → 15m
ETH: 1h → 1m

[변경 직후]
XRP: 2개 (1h-Previous + 5m-Active)
BTC: 2개 (1h-Previous + 15m-Active)
ETH: 2개 (1h-Previous + 1m-Active)
총: 6개 구독  ← Upbit 단일 연결 제한(5개) 초과!
```

### 3.2 대응 전략

**전략 A: 2개 WebSocket 연결 사용** (권장)
```python
ws_conn_1:  # 메인 연결
  - XRP-5m (Active)
  - BTC-15m (Active)
  - ETH-1m (Active)
  
ws_conn_2:  # 전환용 연결 (임시)
  - XRP-1h (Previous)
  - BTC-1h (Previous)
  - ETH-1h (Previous)
```
- TTL 후 ws_conn_2는 자동 종료
- 정상 상태에서는 ws_conn_1만 사용

**전략 B: Previous 즉시 폐기** (단순)
```python
# 타임프레임 변경 즉시 기존 구독 폐기
# "Active + Previous" 정책 포기
# → 전환 시 화면이 잠깐 비거나 깜빡일 수 있음
```

**전략 C: 순차 전환** (안전)
```python
# 동시 변경 요청을 순차 처리
# XRP 전환 완료 → BTC 전환 → ETH 전환
# → 사용자는 약간의 지연 체감 (1~2초)
```

---

## 4. Upbit WebSocket 제한 사항

### 4.1 공식 제한
- **하나의 연결당 최대 5개 심볼 구독**
- 초과 시 연결이 끊기거나 에러 발생

### 4.2 PC 앱의 대응
```python
MAX_SYMBOLS_PER_CONNECTION = 5

def check_subscription_limit(active_subs, pending_subs):
    total = len(active_subs) + len(pending_subs)
    
    if total > MAX_SYMBOLS_PER_CONNECTION:
        # 전략 A: 2번째 연결 사용
        if total <= MAX_SYMBOLS_PER_CONNECTION * 2:
            return 'use_secondary_connection'
        
        # 초과: Previous 즉시 폐기
        else:
            return 'drop_previous_immediately'
    
    return 'ok'
```

---

## 5. 권장 구현 방안

### 5.1 기본 정책
- **정상 상태**: 3개 구독 (XRP, BTC, ETH)
- **전환 중**: 최대 4~5개 (하나씩 순차 전환)
- **비상 시**: Previous 즉시 폐기

### 5.2 코드 구조
```python
class WebSocketManager:
    def __init__(self):
        self.primary_conn = None    # 메인 연결 (최대 5개)
        self.secondary_conn = None  # 전환용 연결 (임시)
        self.subscriptions = {}     # symbol → sub_info
        
    def subscribe(self, symbol, timeframe, is_previous=False):
        # 1. 현재 구독 수 체크
        active_count = len([s for s in self.subscriptions.values() 
                           if not s['is_previous']])
        previous_count = len([s for s in self.subscriptions.values() 
                             if s['is_previous']])
        
        # 2. 제한 체크
        if active_count + previous_count >= 5:
            if is_previous:
                # Previous는 secondary 연결 사용
                return self._subscribe_secondary(symbol, timeframe)
            else:
                # Active는 Previous 즉시 폐기 후 구독
                self._drop_all_previous()
                return self._subscribe_primary(symbol, timeframe)
        
        # 3. 정상 구독
        return self._subscribe_primary(symbol, timeframe)
    
    def _schedule_previous_cleanup(self, symbol, ttl_seconds=30):
        # TTL 후 Previous 자동 폐기
        timer = threading.Timer(ttl_seconds, 
                                self._cleanup_previous, 
                                args=[symbol])
        timer.start()
```

---

## 6. 진단 패널 표시

### 6.1 WebSocket 연결 상태
```
┌─ WebSocket 연결 ─────────────┐
│ Primary:   OK (3/5)          │  ← 3개 구독 중 / 최대 5개
│ Secondary: IDLE              │  ← 전환 시에만 활성화
│                              │
│ Active 구독:                 │
│  • XRP/KRW (5m)  [gen:1]    │
│  • BTC/KRW (15m) [gen:1]    │
│  • ETH/KRW (1m)  [gen:1]    │
│                              │
│ Previous 구독 (TTL):         │
│  (없음)                      │
└──────────────────────────────┘
```

### 6.2 전환 중 표시
```
┌─ WebSocket 연결 ─────────────┐
│ Primary:   OK (3/5)          │
│ Secondary: OK (2/5) [TEMP]   │  ← 전환용 임시 연결
│                              │
│ Active 구독:                 │
│  • XRP/KRW (5m)  [gen:2]    │  ← 새 generation
│  • BTC/KRW (15m) [gen:1]    │
│  • ETH/KRW (1m)  [gen:1]    │
│                              │
│ Previous 구독 (TTL):         │
│  • XRP/KRW (1h) [23s 남음]  │  ← 곧 폐기 예정
│  • BTC/KRW (1h) [18s 남음]  │
└──────────────────────────────┘
```

---

## 7. 테스트 시나리오

### 7.1 정상 시나리오
1. ✅ 앱 시작 → 3개 구독 (XRP, BTC, ETH)
2. ✅ BTC 타임프레임 변경 → 4개 구독 (일시적)
3. ✅ TTL 후 → 3개 구독 (복귀)

### 7.2 스트레스 시나리오
1. ✅ 3개 심볼 동시 변경 → 6개 구독 (2개 연결)
2. ✅ 5초 내 다시 변경 → Previous 즉시 폐기
3. ✅ 연결 1 장애 → 연결 2로 failover

### 7.3 리소스 압력 시나리오
1. ✅ 메모리 압력 → Previous 즉시 폐기
2. ✅ CPU 압력 → 진단 패널 갱신 빈도 다운
3. ✅ 네트워크 지연 → reconnect (generation 증가)

---

## 8. 관련 정책

### 8.1 phase2 작업지시서 참조
- 섹션 G: "심볼/타임프레임 변경 시 2개 동시 구독"
- 섹션 H: "TTL 기반 자동 폐기 트리거"
- 섹션 5: "context_id/generation_id 섞임 방지"

### 8.2 Cloud Collector와의 차이
- **Cloud**: 3개 Collector, 각 독립 WS, 항상 구독 유지
- **PC App**: 1개 프로세스, 1~2개 WS 연결, 타임프레임 동적 변경

---

마지막 업데이트: 2026-01-28
다음 단계: WebSocketManager 클래스 구현
