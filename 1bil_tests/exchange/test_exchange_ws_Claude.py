import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Set
import ccxt.pro as ccxtpro

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BinanceWSCollector:
    """
    Binance WebSocket OHLCV data collector that:
    - Connects via ccxt.pro websocket
    - Saves tick-by-tick data to CSV
    - Records both data_time and save_time
    - Runs independently per trading pair
    - Handles errors gracefully without affecting other pairs
    """
    
    def __init__(self, pairs: list[str], timeframe: str = '1m', data_dir: str = 'ohlcv_data'):
        self.pairs = pairs
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.exchange = ccxtpro.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        
        self._tasks: Set[asyncio.Task] = set()
        self._running = True
        
    def _get_csv_path(self, pair: str) -> Path:
        """Get CSV file path for a trading pair"""
        safe_pair = pair.replace('/', '_')
        return self.data_dir / f"{safe_pair}_{self.timeframe}.csv"
    
    def _format_time(self, timestamp_ms: int) -> str:
        """Format timestamp to required format: 2026/01/11 15:01:03"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y/%m/%d %H:%M:%S')
    
    def _init_csv_file(self, pair: str):
        """Initialize CSV file with headers if it doesn't exist"""
        csv_path = self._get_csv_path(pair)
        if not csv_path.exists():
            with open(csv_path, 'w') as f:
                f.write('data_time,save_time,open,high,low,close,volume\n')
            logger.info(f"Created CSV file: {csv_path}")
    
    def _save_ohlcv(self, pair: str, ohlcv: list):
        """
        Save OHLCV data to CSV
        ohlcv format: [timestamp, open, high, low, close, volume]
        """
        try:
            csv_path = self._get_csv_path(pair)
            data_time = self._format_time(ohlcv[0])
            save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            
            with open(csv_path, 'a') as f:
                line = f"{data_time},{save_time},{ohlcv[1]},{ohlcv[2]},{ohlcv[3]},{ohlcv[4]},{ohlcv[5]}\n"
                f.write(line)
                
            logger.debug(f"[{pair}] Saved: {data_time} -> {save_time}")
            
        except Exception as e:
            logger.error(f"[{pair}] Error saving to CSV: {e}")
    
    async def _watch_ohlcv_for_pair(self, pair: str):
        """
        Watch OHLCV for a single pair - runs independently
        This method continuously watches and saves tick-by-tick data
        """
        logger.info(f"[{pair}] Starting WebSocket connection...")
        self._init_csv_file(pair)
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # Watch OHLCV via WebSocket - this returns immediately when new data arrives
                ohlcvs = await self.exchange.watch_ohlcv(pair, self.timeframe)
                
                if ohlcvs and len(ohlcvs) > 0:
                    # Get the latest candle
                    latest_ohlcv = ohlcvs[-1]
                    self._save_ohlcv(pair, latest_ohlcv)
                    consecutive_errors = 0  # Reset error counter on success
                    
            except asyncio.CancelledError:
                logger.info(f"[{pair}] Task cancelled, shutting down...")
                break
                
            except ccxtpro.NetworkError as e:
                consecutive_errors += 1
                logger.warning(f"[{pair}] Network error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[{pair}] Too many consecutive errors, stopping this pair")
                    break
                await asyncio.sleep(5)  # Wait before reconnecting
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[{pair}] Unexpected error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[{pair}] Too many consecutive errors, stopping this pair")
                    break
                await asyncio.sleep(5)
        
        logger.info(f"[{pair}] WebSocket connection closed")
    
    async def start(self):
        """Start watching all pairs - each pair runs independently"""
        logger.info(f"Starting collector for {len(self.pairs)} pairs: {', '.join(self.pairs)}")
        
        # Create independent task for each pair
        for pair in self.pairs:
            task = asyncio.create_task(self._watch_ohlcv_for_pair(pair))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        
        # Wait for all tasks to complete (or until interrupted)
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("All tasks cancelled")
    
    async def stop(self):
        """Stop all watching tasks and cleanup"""
        logger.info("Stopping collector...")
        self._running = False
        
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Close exchange connection
        try:
            await self.exchange.close()
            logger.info("Exchange connection closed")
        except Exception as e:
            logger.error(f"Error closing exchange: {e}")
    
    def run(self):
        """Main entry point - runs the event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            logger.info("\nReceived interrupt signal (Ctrl+C), shutting down...")
            loop.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        finally:
            # Ensure cleanup
            loop.run_until_complete(self.stop())
            loop.close()
            logger.info("Collector stopped successfully")


def main():
    """
    Main function to run the collector
    
    Usage:
        python binance_ws_collector.py
    """
    # Configure pairs to watch
    pairs = [
        'BTC/USDT',
        'ETH/USDT',
        'BNB/USDT',
    ]
    
    # You can also specify custom timeframe and data directory
    collector = BinanceWSCollector(
        pairs=pairs,
        timeframe='1m',
        data_dir='ohlcv_data'
    )
    
    logger.info("=" * 60)
    logger.info("Binance WebSocket OHLCV Collector")
    logger.info("=" * 60)
    logger.info(f"Pairs: {', '.join(pairs)}")
    logger.info(f"Timeframe: 1m")
    logger.info(f"Data directory: ohlcv_data/")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Run the collector
    collector.run()


if __name__ == '__main__':
    main()