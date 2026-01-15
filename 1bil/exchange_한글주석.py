    def _try_build_from_websocket(
        self, pair: str, timeframe: str, candle_type: CandleType
    ) -> Coroutine[Any, Any, OHLCVResponse] | None:
        """
        웹소켓(실시간 통신)에 이미 저장된 데이터를 재사용할 수 있는지 시도하는 함수입니다.
        성공하면 데이터를 가져오는 코루틴(작업)을 반환하고, 실패하면 None을 반환하여 REST API를 쓰게 합니다.
        """
        # 1. 웹소켓 사용이 가능한 상태인지 먼저 체크 (통행증 검사)
        if self._can_use_websocket(self._exchange_ws, pair, timeframe, candle_type):
            # 현재 봉의 시작 시간과 바로 이전 봉의 시작 시간을 계산
            candle_ts = dt_ts(timeframe_to_prev_date(timeframe))
            prev_candle_ts = dt_ts(date_minus_candles(timeframe, 1))
            
            # 웹소켓 메모리에 쌓여있는 봉(candle) 데이터를 가져옴
            candles = self._exchange_ws.ohlcvs(pair, timeframe)
            
            # 캔들 간격의 절반 시간을 계산 (데이터가 너무 오래되었는지 확인용)
            half_candle = int(candle_ts - (candle_ts - prev_candle_ts) * 0.5)
            
            # 웹소켓 데이터가 마지막으로 서버에서 업데이트된 시각을 확인
            last_refresh_time = int(
                self._exchange_ws.klines_last_refresh.get((pair, timeframe, candle_type), 0)
            )

            # 2. 웹소켓 데이터를 그대로 써도 될 만큼 '충분하고 신선한지' 검사
            if (
                candles and (
                    # 조건 A: 데이터가 여러 개 있고, 마지막 봉이 이전 봉 시간보다 같거나 최신일 때
                    (len(candles) > 1 and candles[-1][0] >= prev_candle_ts)
                    # 조건 B: 데이터가 1개뿐이라면 현재 봉 시간보다는 이전이어야 함 (재연결 시 예외 처리)
                    or (len(candles) == 1 and candles[-1][0] < candle_ts)
                )
                # 조건 C: 마지막 갱신 시각이 봉 시간의 절반보다는 최신이어야 함 (신선도 체크)
                and last_refresh_time >= half_candle
            ):
                # 모든 조건이 맞으면: API 호출 대신 웹소켓에 있는 데이터를 가져오도록 설정
                logger.debug(f"reuse watch result for {pair}, {timeframe}, {last_refresh_time}")
                return self._exchange_ws.get_ohlcv(pair, timeframe, candle_type, candle_ts)

        # 위 조건에 맞지 않으면 웹소켓 대신 REST API를 쓰도록 로그를 남기고 종료
        logger.info(
            f"Couldn't reuse watch for {pair}, {timeframe}, falling back to REST api. "
            f"{candle_ts < last_refresh_time}, {candle_ts}, {last_refresh_time}, "
            f"{format_ms_time(candle_ts)}, {format_ms_time(last_refresh_time)} "
        )
        return None

    def _can_use_websocket(
        self, exchange_ws: ExchangeWS | None, pair: str, timeframe: str, candle_type: CandleType
    ) -> TypeGuard[ExchangeWS]:
        """
        웹소켓을 사용할 수 있는 환경(설정 및 코인 타입)인지 확인하는 함수입니다.
        """
        # 웹소켓 객체가 존재하고, 거래 타입이 현물(SPOT) 또는 선물(FUTURES)일 때만 활성화
        if exchange_ws and candle_type in (CandleType.SPOT, CandleType.FUTURES):
            return True
        return False

    def _build_coroutine(
        self, pair: str, timeframe: str, candle_type: CandleType, since_ms: int | None, cache: bool,
    ) -> Coroutine[Any, Any, OHLCVResponse]:
        """
        데이터를 가져올 최적의 방법(웹소켓 또는 API)을 결정하여 실행 계획을 세우는 함수입니다.
        """
        not_all_data = cache and self.required_candle_call_count > 1
        if cache:
            # 웹소켓 사용이 가능하다면, 해당 코인 정보를 실시간으로 받겠다고 '구독 신청(schedule)' 함
            if self._can_use_websocket(self._exchange_ws, pair, timeframe, candle_type):
                # Subscribe to websocket
                self._exchange_ws.schedule_ohlcv(pair, timeframe, candle_type)

        # 이미 가지고 있는 메모리(캐시) 데이터가 있는지 확인
        if cache and (pair, timeframe, candle_type) in self._klines:
            candle_limit = self.ohlcv_candle_limit(timeframe, candle_type)
            min_ts = dt_ts(date_minus_candles(timeframe, candle_limit - 5))
            
            # ★ 핵심: 웹소켓을 통해 데이터를 가져올 수 있는지 먼저 시도
            if ws_resp := self._try_build_from_websocket(pair, timeframe, candle_type):
                # 웹소켓 데이터가 사용 가능하면 즉시 반환 (REST API 호출 생략)
                return ws_resp

            # 만약 웹소켓을 못 쓰더라도 기존 캐시가 유효한지 확인
            if min_ts < self._pairs_last_refresh_time.get((pair, timeframe, candle_type), 0):
                # 캐시 사용 가능 - 한 번만 호출해서 업데이트
                not_all_data = False
            else:
                # 데이터에 공백(Time jump)이 생겼다면 캐시를 삭제하고 새로 받아야 함
                logger.info(
                    f"Time jump detected. Evicting cache for {pair}, {timeframe}, {candle_type}"
                )
                del self._klines[(pair, timeframe, candle_type)]

        # 이후부터는 REST API를 사용하여 과거 데이터를 채우는 로직으로 이어짐
        if not since_ms and (self._ft_has["ohlcv_require_since"] or not_all_data):
            one_call = timeframe_to_msecs(timeframe) * self.ohlcv_candle_limit(
                timeframe, candle_type, since_ms
            )
            move_to = one_call * self.required_candle_call_count
            now = timeframe_to_next_date(timeframe)
            since_ms = dt_ts(now - timedelta(seconds=move_to // 1000))

        if since_ms:
            # 과거 데이터가 많이 필요하면 역사적 데이터 다운로드 함수 호출
            return self._async_get_historic_ohlcv(
                pair, timeframe, since_ms=since_ms, raise_=True, candle_type=candle_type
            )
        else:
            # 일반적인 상황에서는 한 번의 API 호출로 데이터 갱신
            return self._async_get_candle_history(
                pair, timeframe, since_ms=since_ms, candle_type=candle_type
            )
