# my_agent/memory/summarizer_tool.py
"""
Tool để tự động tóm tắt hội thoại định kỳ, giúp giảm token context window.
"""
import os
import google.generativeai as genai
from typing import Dict, Any, List, Optional
import sys
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# ============================================================
# IMPORTS - Đổi sang absolute import để tương thích MCP
# ============================================================
try:
    from ..cache import get_session_state, set_session_state
    print("✅ Summarizer tool đã import cache thành công.")
except ImportError as e:
    try:
        from my_agent.cache import get_session_state, set_session_state
        print("✅ Summarizer tool đã import cache (absolute) thành công.", file=sys.stderr)
    except ImportError:
        print(f"⚠️ Lỗi import cache: {e}. Summarizer tool sẽ chạy không có cache.", file=sys.stderr)
        def get_session_state(key: str) -> Dict: return {}
        def set_session_state(key: str, value: Dict): pass

try:
    from ..database.chat_store import chat_store
    print("✅ Summarizer tool đã import chat_store thành công.")
except ImportError as e:
    try:
        from my_agent.database.chat_store import chat_store
        print("✅ Summarizer tool đã import chat_store (absolute) thành công.", file=sys.stderr)
    except ImportError as e:
        print(f"⚠️ Lỗi import chat_store: {e}...", file=sys.stderr)
        class FakeChatStore:
            def get_messages(self, user_id: int, limit: int = 50) -> List:
                return []
            def get_message_count(self, user_id: int) -> int:
                return 0
        chat_store = FakeChatStore()


# ============================================================
# CẤU HÌNH
# ============================================================
SUMMARY_TRIGGER_COUNT = 10  # Tóm tắt sau mỗi 10 tin nhắn mới
GEMINI_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.0-flash-exp")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

# Cấu hình Gemini API (nếu chưa được cấu hình)
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ Gemini API đã được cấu hình cho summarizer.")
    except Exception as e:
        print(f"⚠️ Lỗi cấu hình Gemini API: {e}")
else:
    print("⚠️ Thiếu GEMINI_API_KEY, summarizer sẽ không hoạt động.")


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def _format_messages_for_summary(messages: List[Dict]) -> str:
    """
    Chuyển đổi danh sách message dict thành chuỗi text dễ đọc.
    
    Input message format (từ chat_store):
    {
        'message': {
            'role': 'user' hoặc 'model',
            'content': 'nội dung tin nhắn'
        },
        'timestamp': '2025-11-16T10:30:00'
    }
    """
    formatted_lines = []
    
    for msg in messages:
        try:
            role = msg.get('message', {}).get('role', 'unknown')
            content = msg.get('message', {}).get('content', '')
            timestamp = msg.get('timestamp', '')
            
            # Chuyển role thành tên dễ hiểu
            speaker = "User" if role == "user" else "Assistant"
            
            # Rút gọn nội dung nếu quá dài (giữ 500 ký tự đầu)
            if len(content) > 500:
                content = content[:500] + "..."
            
            formatted_lines.append(f"[{speaker}]: {content}")
            
        except Exception as e:
            print(f"⚠️ Lỗi format message: {e}")
            continue
    
    return "\n".join(formatted_lines)


def _call_gemini_summarizer(messages_to_summarize: List[Dict], old_summary: str) -> str:
    """
    Gọi Gemini API để tạo/cập nhật tóm tắt hội thoại.
    
    Args:
        messages_to_summarize: Danh sách tin nhắn mới cần tóm tắt
        old_summary: Bản tóm tắt cũ (nếu có)
    
    Returns:
        Bản tóm tắt mới (hoặc tóm tắt cũ nếu lỗi)
    """
    if not GEMINI_API_KEY:
        print("⚠️ Thiếu API key, không thể gọi Gemini summarizer.")
        return old_summary
    
    print(f"📝 SUMMARIZER: Đang gọi Gemini để tóm tắt {len(messages_to_summarize)} tin nhắn mới...")
    
    # Format messages thành text
    chat_text = _format_messages_for_summary(messages_to_summarize)
    
    if not chat_text.strip():
        print("⚠️ Không có nội dung để tóm tắt.")
        return old_summary
    
    # Tạo prompt
    if old_summary:
        prompt = (
            "Bạn là một trợ lý chuyên nghiệp. Nhiệm vụ của bạn là CẬP NHẬT bản tóm tắt cuộc hội thoại.\n\n"
            f"📋 BẢN TÓM TẮT CŨ:\n{old_summary}\n\n"
            f"💬 TIN NHẮN MỚI (theo thứ tự thời gian):\n{chat_text}\n\n"
            "📝 YÊU CẦU:\n"
            "- Viết bản tóm tắt CẬP NHẬT khoảng 3-5 câu\n"
            "- Bao gồm: Mục tiêu chính, các mã cổ phiếu đã thảo luận, insight quan trọng\n"
            "- Loại bỏ thông tin lỗi thời, giữ lại điểm mấu chốt\n"
            "- Chỉ trả về nội dung tóm tắt, không thêm lời mở đầu hay kết thúc\n"
        )
    else:
        prompt = (
            "Bạn là một trợ lý chuyên nghiệp. Nhiệm vụ của bạn là TẠO bản tóm tắt cuộc hội thoại.\n\n"
            f"💬 CUỘC HỘI THOẠI:\n{chat_text}\n\n"
            "📝 YÊU CẦU:\n"
            "- Viết bản tóm tắt khoảng 3-5 câu\n"
            "- Bao gồm: Mục tiêu chính, các mã cổ phiếu đã thảo luận, insight quan trọng\n"
            "- Tập trung vào thông tin có giá trị nhất\n"
            "- Chỉ trả về nội dung tóm tắt, không thêm lời mở đầu hay kết thúc\n"
        )
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Gọi API với timeout và retry
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # Thấp để có kết quả nhất quán
                max_output_tokens=300,  # Giới hạn độ dài tóm tắt
            )
        )
        
        new_summary = response.text.strip()
        
        if not new_summary:
            print("⚠️ Gemini trả về kết quả rỗng.")
            return old_summary
        
        print(f"✅ SUMMARIZER: Tóm tắt mới được tạo ({len(new_summary)} ký tự)")
        print(f"📄 Nội dung: {new_summary[:100]}...")
        
        return new_summary
        
    except Exception as e:
        print(f"❌ LỖI SUMMARIZER: {e}")
        return old_summary  # Fallback về tóm tắt cũ


# ============================================================
# MAIN TOOL FUNCTION
# ============================================================
def get_or_update_summary(user_id_int: int, force_update: bool = False) -> str:
    """
    Kiểm tra và cập nhật tóm tắt hội thoại nếu cần thiết.
    
    Logic:
    1. Lấy tóm tắt cũ từ Redis cache
    2. Đếm số tin nhắn mới từ lần tóm tắt cuối
    3. Nếu đủ SUMMARY_TRIGGER_COUNT tin nhắn mới (hoặc force_update=True):
       → Gọi Gemini để tạo tóm tắt mới
       → Lưu vào Redis cache
    4. Trả về tóm tắt (cũ hoặc mới)
    
    Args:
        user_id_int: ID người dùng
        force_update: Bắt buộc tạo tóm tắt mới (bỏ qua check số tin nhắn)
    
    Returns:
        String tóm tắt với prefix "Tóm tắt bối cảnh: ..."
    """
    session_key = str(user_id_int)
    
    try:
        # =====================================================
        # BƯỚC 1: Lấy trạng thái hiện tại từ cache
        # =====================================================
        current_state = get_session_state(session_key)
        old_summary = current_state.get('summary', '')
        last_summary_count = current_state.get('last_summary_count', 0)
        
        # =====================================================
        # BƯỚC 2: Đếm tin nhắn hiện tại
        # =====================================================
        # Ưu tiên dùng get_message_count nếu có
        try:
            current_message_count = chat_store.get_message_count(user_id_int)
        except AttributeError:
            # Fallback: Lấy tất cả messages và đếm
            all_messages = chat_store.get_messages(user_id_int, limit=100)
            current_message_count = len(all_messages)
        
        messages_since_last_summary = current_message_count - last_summary_count
        
        print(f"📊 SUMMARIZER: User {user_id_int} - "
              f"Total: {current_message_count}, "
              f"New: {messages_since_last_summary}, "
              f"Threshold: {SUMMARY_TRIGGER_COUNT}")
        
        # =====================================================
        # BƯỚC 3: Quyết định có cần tóm tắt không
        # =====================================================
        
        # Case 1: Chưa có tin nhắn nào
        if current_message_count == 0:
            return "Tóm tắt bối cảnh: (Chưa có lịch sử hội thoại)"
        
        # Case 2: Tóm tắt còn "tươi" (chưa đủ tin nhắn mới)
        if messages_since_last_summary < SUMMARY_TRIGGER_COUNT and old_summary and not force_update:
            print(f"✅ SUMMARIZER: Tóm tắt còn tươi, sử dụng cache.")
            return f"Tóm tắt bối cảnh: {old_summary}"
        
        # Case 3: Chưa đủ tin nhắn để tóm tắt lần đầu
        if current_message_count < SUMMARY_TRIGGER_COUNT and not force_update:
            return "Tóm tắt bối cảnh: (Chưa đủ dữ liệu để tóm tắt)"
        
        # =====================================================
        # BƯỚC 4: CẦN TẠO TÓM TẮT MỚI
        # =====================================================
        print(f"🔄 SUMMARIZER: Bắt đầu tạo tóm tắt mới...")
        
        # Lấy tin nhắn cần tóm tắt
        if force_update or last_summary_count == 0:
            # Tóm tắt toàn bộ (lần đầu hoặc force)
            messages_to_summarize = chat_store.get_messages(user_id_int, limit=100)
        else:
            # Chỉ tóm tắt tin nhắn mới
            all_messages = chat_store.get_messages(user_id_int, limit=100)
            # Lấy tin nhắn từ vị trí last_summary_count trở đi
            messages_to_summarize = all_messages[last_summary_count:] if last_summary_count < len(all_messages) else all_messages
        
        if not messages_to_summarize:
            print("⚠️ Không có tin nhắn để tóm tắt.")
            return f"Tóm tắt bối cảnh: {old_summary}" if old_summary else "Tóm tắt bối cảnh: (Không có dữ liệu)"
        
        # Gọi Gemini để tóm tắt
        new_summary = _call_gemini_summarizer(messages_to_summarize, old_summary)
        
        # =====================================================
        # BƯỚC 5: Lưu tóm tắt mới vào cache
        # =====================================================
        current_state['summary'] = new_summary
        current_state['last_summary_count'] = current_message_count
        current_state['last_summary_time'] = __import__('datetime').datetime.now().isoformat()
        set_session_state(session_key, current_state)
        
        print(f"💾 SUMMARIZER: Đã lưu tóm tắt mới vào cache.")
        
        return f"Tóm tắt bối cảnh: {new_summary}"
    
    except Exception as e:
        error_msg = f"Lỗi khi cập nhật tóm tắt: {e}"
        print(f"❌ {error_msg}")
        
        # Fallback: Trả về tóm tắt cũ nếu có
        try:
            current_state = get_session_state(session_key)
            old_summary = current_state.get('summary', '')
            if old_summary:
                return f"Tóm tắt bối cảnh: {old_summary} (Cảnh báo: Không thể cập nhật)"
        except:
            pass
        
        return f"Tóm tắt bối cảnh: (Lỗi: {str(e)[:100]})"


# ============================================================
# OPTIONAL: Clear summary function
# ============================================================
def clear_summary(user_id_int: int) -> str:
    """Xóa tóm tắt và reset counter (dùng khi user muốn bắt đầu lại)"""
    session_key = str(user_id_int)
    try:
        current_state = get_session_state(session_key)
        current_state['summary'] = ''
        current_state['last_summary_count'] = 0
        set_session_state(session_key, current_state)
        return "Đã xóa tóm tắt và reset counter."
    except Exception as e:
        return f"Lỗi khi xóa tóm tắt: {e}"