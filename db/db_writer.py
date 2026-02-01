"""
Асинхронный writer для операций записи в БД через очередь.
Предотвращает блокировку event loop при записи в SQLite.
"""
import asyncio
import logging
from typing import Callable, Any
import sqlite3

logger = logging.getLogger(__name__)


class DBWriter:
    """
    Асинхронный writer для БД через очередь.
    Один worker thread читает задачи из очереди и выполняет их синхронно.
    """
    
    def __init__(self, db_path: str, worker_count: int = 1, queue_size: int = 1000):
        """
        Args:
            db_path: путь к БД
            worker_count: количество worker-потоков (рекомендуется 1 для SQLite)
            queue_size: размер очереди
        """
        self.db_path = db_path
        self.worker_count = worker_count
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.workers = []
        self._stop_event = asyncio.Event()
    
    async def start(self):
        """Запустить workers"""
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker(f"DBWriter-{i}"))
            self.workers.append(worker)
            logger.info(f"Started DBWriter worker {i}")
    
    async def stop(self):
        """Остановить workers и дождаться завершения очереди"""
        logger.info("Stopping DBWriter...")
        
        # Дождёмся пока очередь опустеет
        await self.queue.join()
        
        # Сигнализируем workers остановиться
        self._stop_event.set()
        
        # Дождёмся завершения всех workers
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        logger.info("DBWriter stopped")
    
    async def execute(self, sql: str, params: tuple = (), fetch: bool = False) -> Any:
        """
        Поставить задачу в очередь на выполнение (без ожидания результата).
        Для операций SELECT используйте fetch=True для получения результата.
        """
        result_future = asyncio.Future()
        
        task = {
            'sql': sql,
            'params': params,
            'fetch': fetch,
            'future': result_future
        }
        
        try:
            await asyncio.wait_for(self.queue.put(task), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error(f"Queue timeout when adding task: {sql[:50]}")
            raise
        
        # Если нужен результат - ждём
        if fetch:
            try:
                result = await asyncio.wait_for(result_future, timeout=10.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"Result timeout for query: {sql[:50]}")
                raise
        else:
            # Для INSERT/UPDATE/DELETE можем вернуться сразу
            # но результат всё ещё будет установлен в future
            task_done_future = asyncio.Future()
            
            # Проверяем результат с небольшим таймаутом для ошибок
            try:
                result = await asyncio.wait_for(result_future, timeout=1.0)
                if isinstance(result, Exception):
                    raise result
            except asyncio.TimeoutError:
                pass  # Ignore timeout for fire-and-forget operations
            
            return None
    
    async def _worker(self, name: str):
        """Worker task, выполняет SQL команды"""
        logger.info(f"Worker {name} started")
        
        # Создаём собственное соединение для этого потока
        try:
            conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
        except Exception as e:
            logger.error(f"Worker {name} failed to connect to DB: {e}")
            return
        
        try:
            while not self._stop_event.is_set():
                try:
                    # Получаем задачу с таймаутом чтобы проверять stop_event
                    task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    
                    try:
                        sql = task['sql']
                        params = task.get('params', ())
                        fetch = task.get('fetch', False)
                        future = task['future']
                        
                        cursor = conn.cursor()
                        cursor.execute(sql, params)
                        
                        if fetch:
                            result = cursor.fetchall()
                            if not future.done():
                                future.set_result(result)
                        else:
                            conn.commit()
                            if not future.done():
                                future.set_result(None)
                        
                        logger.debug(f"Worker {name} executed: {sql[:50]}")
                        
                    except Exception as e:
                        logger.error(f"Worker {name} error: {e}", exc_info=False)
                        if not task['future'].done():
                            task['future'].set_exception(e)
                    
                    finally:
                        self.queue.task_done()
                
                except asyncio.TimeoutError:
                    # Taimeout от queue.get - нормально, проверяем stop_event
                    continue
        
        finally:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Worker {name} error closing connection: {e}")
            logger.info(f"Worker {name} stopped")
