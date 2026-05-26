# my_agent/cache.py
import redis
import json
from typing import Dict, Any, Optional
import sys

def _log(msg: str) -> None:
    """Ghi log ra stderr để không làm bẩn STDOUT (dùng cho MCP)."""
    print(msg, file=sys.stderr, flush=True)

try:
    # Kết nối tới Redis server đang chạy trên localhost, cổng 6379
    # decode_responses=True giúp tự động giải mã từ bytes sang string (utf-8)
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

    # Thử kết nối
    redis_client.ping()
    _log("✅ Kết nối Redis thành công!")

except redis.exceptions.ConnectionError as e:
    _log("LỖI: Không thể kết nối tới Redis. Bạn đã chạy Redis Server chưa?")
    _log(f"Lỗi chi tiết: {e}")
    redis_client = None
except Exception as e:
    _log(f"LỖI: Lỗi không xác định khi khởi tạo Redis: {e}")
    redis_client = None

def get_cache(key: str) -> Optional[Any]:
    """Lấy dữ liệu từ cache bằng key."""
    if not redis_client:
        return None

    try:
        cached_data = redis_client.get(key)
        if cached_data:
            _log(f"CACHE HIT: Tìm thấy dữ liệu cho key '{key}'")
            return json.loads(cached_data)  # Giải mã JSON

        _log(f"CACHE MISS: Không tìm thấy key '{key}'")
        return None
    except Exception as e:
        _log(f"Lỗi khi lấy cache: {e}")
        return None

def set_cache(key: str, value: Any, expiration_sec: int = 300):
    """Lưu dữ liệu vào cache với thời gian hết hạn (tính bằng giây)."""
    if not redis_client:
        return

    try:
        # Chuyển dict/list thành chuỗi JSON trước khi lưu
        redis_client.setex(key, expiration_sec, json.dumps(value))
        _log(f"CACHE SET: Đã lưu key '{key}' (hết hạn sau {expiration_sec}s)")
    except Exception as e:
        _log(f"Lỗi khi set cache: {e}")

def set_session_state(
    session_id: str, state_data: Dict[str, Any], expiration_sec: int = 3600
):
    """
    Lưu trạng thái hội thoại (ví dụ: current_symbol) vào Redis.
    Chúng ta dùng session_id (ví dụ 'user') làm key. Hết hạn sau 1 giờ.
    """
    if not redis_client:
        return
    try:
        key = f"session:{session_id}"
        redis_client.setex(key, expiration_sec, json.dumps(state_data))
        _log(f"SESSION SET: Đã lưu trạng thái cho session '{session_id}'")
    except Exception as e:
        _log(f"Lỗi khi set session state: {e}")

def get_session_state(session_id: str) -> Dict[str, Any]:
    """
    Lấy trạng thái hội thoại từ Redis.
    """
    if not redis_client:
        return {}

    try:
        key = f"session:{session_id}"
        cached_data = redis_client.get(key)
        if cached_data:
            _log(f"SESSION HIT: Tìm thấy trạng thái cho session '{session_id}'")
            return json.loads(cached_data)

        _log(f"SESSION MISS: Không tìm thấy trạng thái cho session '{session_id}'")
        return {}  # Trả về dict rỗng nếu không có gì
    except Exception as e:
        _log(f"Lỗi khi lấy session state: {e}")
        return {}
