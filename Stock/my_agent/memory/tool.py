# my_agent/memory/tool.py
from typing import Dict, Any, Literal, Optional
import sys

try:
    from ..cache import get_session_state, set_session_state
    print("✅ Memory tool đã import cache thành công.")
except ImportError:
    try:
        from my_agent.cache import get_session_state, set_session_state
        print("✅ Memory tool đã import cache (absolute) thành công.", file=sys.stderr)
    except ImportError as e:
        print(f"⚠️ Lỗi import cache: {e}. Memory tool sẽ chạy không có cache.", file=sys.stderr)
        def get_session_state(key: str) -> Dict: return {}
        def set_session_state(key: str, value: Dict): pass


def set_current_symbol(user_id_int: int, symbol: str) -> str:
    """
    GHI NHỚ mã cổ phiếu đang được nhắc đến.
    """
    session_key = str(user_id_int) 
    try:
        current_state = get_session_state(session_key)
        new_symbol = symbol.upper()
        current_state['current_symbol'] = new_symbol
        set_session_state(session_key, current_state)
        return f"Đã ghi nhớ: Mã cổ phiếu hiện tại là {new_symbol}"
    except Exception as e:
        return f"Lỗi khi set trí nhớ: {e}"


def get_current_symbol(user_id_int: int) -> str:
    """
    TRUY XUẤT mã cổ phiếu đã được ghi nhớ.
    """
    session_key = str(user_id_int) 
    try:
        current_state = get_session_state(session_key)
        current_symbol = current_state.get('current_symbol')
        
        if current_symbol:
            return f"Mã cổ phiếu đang được ghi nhớ là: {current_symbol}"
        else:
            return "Chưa có mã cổ phiếu nào được ghi nhớ."
    except Exception as e:
        return f"Lỗi khi get trí nhớ: {e}"