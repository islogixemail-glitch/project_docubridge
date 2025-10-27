"""
db.py — работа с PostgreSQL: пул соединений и CRUD для истории, состояний и лидов.
Зависит от config.DB_URL
"""

from contextlib import contextmanager
import json
from typing import Optional, Dict, Any, Iterator
import time

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from config import DB_URL

_connection_pool: Optional[pool.SimpleConnectionPool] = None


def init_db_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """Инициализирует модульный пул соединений (вызывать при старте приложения)."""
    global _connection_pool
    if not DB_URL:
        print("[DB] init_db_pool: DB_URL не задан — база отключена")
        return
    if _connection_pool:
        return
    try:
        _connection_pool = pool.SimpleConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            dsn=DB_URL,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        print("[DB] Connection pool created")
    except Exception as e:
        print(f"[DB] Pool creation error: {e}")
        _connection_pool = None


def _direct_connect():
    """Открыть прямое соединение (без пула) — используется как fallback."""
    return psycopg2.connect(
        DB_URL,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def get_conn(max_retries: int = 3):
    """
    Получить соединение; при падении соединения пытается переподключиться.
    Возвращает psycopg2 connection или None (если DB_URL не задан или все попытки неудачны).
    """
    if not DB_URL:
        return None

    last_exc = None
    for attempt in range(max_retries):
        try:
            if not _connection_pool:
                # если пул не инициализирован — создаём прямое соединение
                conn = _direct_connect()
                return conn

            conn = _connection_pool.getconn()
            try:
                # тест запроса, чтобы убедиться, что соединение живое
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                return conn
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as conn_err:
                print(f"[DB] Dead connection detected: {conn_err}")
                try:
                    _connection_pool.putconn(conn, close=True)
                except Exception:
                    pass
                last_exc = conn_err
                # небольшой бэкофф
                time.sleep(0.1 * (attempt + 1))
                continue
        except Exception as e:
            print(f"[DB] get_conn error (attempt {attempt + 1}/{max_retries}): {e}")
            last_exc = e
            time.sleep(0.1 * (attempt + 1))
            continue

    print("[DB] All connection attempts failed")
    if last_exc:
        print(f"[DB] last exception: {last_exc}")
    return None


def return_conn(conn) -> None:
    """Возвращает соединение в пул или закрывает прямое соединение."""
    if not conn:
        return
    try:
        if _connection_pool:
            try:
                _connection_pool.putconn(conn)
            except Exception as e:
                print(f"[DB] return_conn putconn error: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            try:
                conn.close()
            except Exception as e:
                print(f"[DB] return_conn close error: {e}")
    except Exception as e:
        print(f"[DB] return_conn unexpected error: {e}")


@contextmanager
def db_connection():
    """
    Контекст-менеджер для безопасной работы с соединением:
        with db_connection() as conn:
            cur = conn.cursor()
            ...
    Автоматически возвращает соединение в пул.
    """
    conn = None
    try:
        conn = get_conn()
        yield conn
    finally:
        if conn:
            return_conn(conn)


def ensure_tables() -> None:
    """Создаёт необходимые таблицы, если их отсутствуют."""
    if not DB_URL:
        return
    sql = """
    CREATE TABLE IF NOT EXISTS chat_history (
      id BIGSERIAL PRIMARY KEY,
      chat_id BIGINT NOT NULL,
      user_message TEXT,
      bot_reply TEXT,
      timestamp TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS user_state (
      chat_id BIGINT PRIMARY KEY,
      state TEXT NOT NULL DEFAULT 'greeting',
      data JSONB DEFAULT '{}'::jsonb,
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS leads (
      id BIGSERIAL PRIMARY KEY,
      chat_id BIGINT NOT NULL,
      payload JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS processed_updates (
      update_id BIGINT PRIMARY KEY,
      processed_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_processed_updates_time
      ON processed_updates (processed_at);

    CREATE INDEX IF NOT EXISTS chat_history_ts_idx
      ON chat_history (timestamp DESC);
    """
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] ensure_tables: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        cur.close()
        print("[DB] ensure_tables OK")
    except Exception as e:
        print(f"[DB] ensure_tables error: {e}")
    finally:
        if conn:
            return_conn(conn)


# ------------------------------
# processed_updates helpers
# ------------------------------
def is_update_processed(update_id: int) -> bool:
    """Проверяет, было ли обновление уже обработано."""
    if not DB_URL:
        return False
    conn = None
    try:
        conn = get_conn()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_updates WHERE update_id = %s", (int(update_id),))
        exists = cur.fetchone() is not None
        cur.close()
        return exists
    except Exception as e:
        print(f"[DB] is_update_processed error: {e}")
        return False
    finally:
        if conn:
            return_conn(conn)


def mark_update_processed(update_id: int) -> None:
    """Отмечает update_id как обработанное."""
    if not DB_URL:
        return
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] mark_update_processed: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO processed_updates (update_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (int(update_id),),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[DB] mark_update_processed error: {e}")
    finally:
        if conn:
            return_conn(conn)


def cleanup_old_updates(days: int = 7) -> None:
    """Удаляет записи старше N дней из processed_updates."""
    if not DB_URL:
        return
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] cleanup_old_updates: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM processed_updates WHERE processed_at < NOW() - INTERVAL %s",
            (f"{days} days",),
        )
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        print(f"[DB] Cleaned up {deleted} old update records")
    except Exception as e:
        print(f"[DB] cleanup_old_updates error: {e}")
    finally:
        if conn:
            return_conn(conn)


# ------------------------------
# chat_history helpers
# ------------------------------
def save_message(chat_id: int, user_text: Optional[str], bot_reply: Optional[str]) -> None:
    """Сохраняет пару (user -> bot) в chat_history."""
    if not DB_URL:
        return
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] save_message: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chat_history (chat_id, user_message, bot_reply) VALUES (%s, %s, %s)",
            (int(chat_id), user_text, bot_reply),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[DB] save_message error: {e}")
    finally:
        if conn:
            return_conn(conn)


# ------------------------------
# user_state helpers
# ------------------------------
def get_state(chat_id: int) -> (str, Dict):
    """
    Возвращает (state, data) для chat_id.
    Если не найдено — возвращает ("greeting", {}).
    """
    if not DB_URL:
        return ("greeting", {})
    conn = None
    try:
        conn = get_conn()
        if not conn:
            return ("greeting", {})
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT state, data FROM user_state WHERE chat_id = %s", (int(chat_id),))
        row = cur.fetchone()
        cur.close()
        if not row:
            return ("greeting", {})
        state = row.get("state", "greeting")
        data = row.get("data") or {}
        return (state, data)
    except Exception as e:
        print(f"[DB] get_state error: {e}")
        return ("greeting", {})
    finally:
        if conn:
            return_conn(conn)


def set_state(chat_id: int, state: str, data: Optional[Dict] = None) -> None:
    """
    Устанавливает/создаёт запись user_state.
    data хранится как JSONB.
    """
    if not DB_URL:
        return
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] set_state: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_state (chat_id, state, data, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE
              SET state = EXCLUDED.state,
                  data  = COALESCE(EXCLUDED.data, user_state.data),
                  updated_at = NOW()
            """,
            (int(chat_id), state, json.dumps(data or {})),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[DB] set_state error: {e}")
    finally:
        if conn:
            return_conn(conn)


def update_data(chat_id: int, new_data: Dict) -> None:
    """Обновляет поле data для user_state (заменяет содержимое)."""
    if not DB_URL:
        return
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] update_data: Failed to get connection")
            return
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_state SET data = %s, updated_at = NOW() WHERE chat_id = %s",
            (json.dumps(new_data), int(chat_id)),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[DB] update_data error: {e}")
    finally:
        if conn:
            return_conn(conn)


# ------------------------------
# leads helpers
# ------------------------------
def insert_lead(chat_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Ставит лид в таблицу leads. Возвращает id вставленной записи или None.
    """
    if not DB_URL:
        return None
    conn = None
    try:
        conn = get_conn()
        if not conn:
            print("[DB] insert_lead: Failed to get connection")
            return None
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO leads (chat_id, payload) VALUES (%s, %s) RETURNING id",
            (int(chat_id), psycopg2.extras.Json(payload)),
        )
        inserted_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return inserted_id
    except Exception as e:
        print(f"[DB] INSERT lead error: {e}")
        return None
    finally:
        if conn:
            return_conn(conn)
