# my_agent/agent.py
"""
Root Agent (Orchestrator) - Điều phối tất cả các agent con và tools.
Version: CONTROLLED REPLY + DB LOGGING (fixed greeting behavior, no double reply)
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Import các agent con
from .price.agent import create_price_agent
from .news.agent import create_news_agent
from .sentiment.agent import create_sentiment_agent
from .financial.agent import create_financial_agent
from .technical_analysis.agent import create_ta_agent

# Import database tools
from .database.chat_store import chat_store

# Import memory tools
from .memory.tool import set_current_symbol, get_current_symbol
from .memory.summarizer_tool import get_or_update_summary

# ============================================================
# CONFIGURATION
# ============================================================
VENV_PYTHON = Path(sys.executable)
SERVER_PATH = Path(__file__).parent / "mcp_server.py"

# Load .env (trong thư mục my_agent)
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


# ============================================================
# CREATE MCP TOOLSET – SIMPLE
# ============================================================
def create_mcp_toolset() -> MCPToolset | None:
    """
    Tạo MCPToolset với cấu hình chuẩn và TIMEOUT CAO.
    """
    try:
        # Cấu hình Server
        server_params = StdioServerParameters(
            command=str(VENV_PYTHON),
            args=[str(SERVER_PATH)],
            cwd=str(Path(__file__).parent),
            env=None,
        )

        # Cấu hình Connection với Timeout cao
        connection_params = StdioConnectionParams(
            server_params=server_params,
            initialization_timeout=60.0,
            connection_timeout=600.0,
        )

        # Khởi tạo Toolset
        toolset = MCPToolset(connection_params=connection_params)
        print("✅ MCPToolset khởi tạo thành công")
        return toolset

    except Exception as e:
        print(f"❌ Không thể khởi tạo MCPToolset: {e}")
        import traceback
        traceback.print_exc()
        return None


# Khởi tạo MCP toolset một lần
_mcp_toolset = create_mcp_toolset()

# ============================================================
# CREATE ROOT AGENT
# ============================================================
def create_agent() -> Agent:
    print("Đang tạo các agent con...")

    # Tất cả sub-agent dùng chung 1 MCP toolset
    price_agent = create_price_agent(_mcp_toolset)
    news_agent = create_news_agent(_mcp_toolset)
    senti_agent = create_sentiment_agent(_mcp_toolset)
    financial_agent = create_financial_agent(_mcp_toolset)
    ta_agent = create_ta_agent(_mcp_toolset)

    print("Các agent con đã sẵn sàng")

    # Database tools – cho phép LLM tương tác với lịch sử.
    # add_user: có thể dùng nếu cần tạo user mới trong DB.
    # add_message: dùng để lưu toàn bộ hội thoại (user + model).
    db_tools = [
        chat_store.add_user,
        chat_store.get_relevant_history,
        chat_store.get_messages,
        chat_store.add_message,
    ]

    # Memory tools
    memory_tools = [
        set_current_symbol,
        get_current_symbol,
        get_or_update_summary,
    ]

    # Root cũng có MCP toolset
    root_tools = [_mcp_toolset] if _mcp_toolset else []

    instruction = (
        "Bạn là chuyên gia tư vấn chứng khoán.\n"
        "\n"
        "MỤC TIÊU CHÍNH:\n"
        "- Hiểu câu hỏi của người dùng về cổ phiếu, chỉ số, thị trường.\n"
        "- Khi cần, sử dụng sub-agent hoặc MCP tools để lấy dữ liệu (price, news, sentiment, TA, financial).\n"
        "- Luôn cố gắng lưu toàn bộ hội thoại (user + model) vào database thông qua công cụ add_message.\n"
        "- MỖI TIN NHẮN CỦA USER, BẠN CHỈ ĐƯỢC TRẢ LỜI MỘT CÂU TRẢ LỜI CUỐI CÙNG (một lượt message), "
        "KHÔNG ĐƯỢC TRẢ LỜI HAI LẦN.\n"
        "\n"
        "LUẬT TỔNG QUÁT (TUYỆT ĐỐI PHẢI TUÂN THỦ):\n"
        "1) Cho mỗi tin nhắn mới từ user:\n"
        "   - Hãy cố gắng gọi `add_message(role='user', content=<nguyên văn tin nhắn user>)` MỘT LẦN.\n"
        "   - Sau khi đã có câu trả lời CUỐI CÙNG (sau khi dùng sub-agent/tools nếu cần), "
        "     hãy gọi `add_message(role='model', content=<câu trả lời cuối cùng>)` MỘT LẦN.\n"
        "2) Sau khi đã gọi `add_message(role='model', ...)`, bạn chỉ được TRẢ VỀ "
        "CHÍNH câu trả lời đó cho người dùng MỘT LẦN duy nhất.\n"
        "   - KHÔNG ĐƯỢC sinh thêm một câu trả lời thứ hai (ví dụ: tóm tắt lại, comment thêm, "
        "     hay trả lời lần nữa từ summary).\n"
        "3) KHÔNG BAO GIỜ tạo message giả với vai trò 'user' bằng bất kỳ tool nào.\n"
        "4) KHÔNG dùng tool nào để ghi lại 'suy nghĩ trung gian' hay hội thoại mẫu.\n"
        "\n"
        "GHI LỊCH SỬ VÀO DATABASE (chat_store):\n"
        "- Mỗi lượt xử lý tin nhắn, mục tiêu là lưu lịch sử bằng add_message ĐÚNG 2 lần:\n"
        "  (a) Giai đoạn đầu: `add_message(role='user', content=<nguyên văn tin nhắn user>)`. \n"
        "  (b) Giai đoạn cuối: sau khi đã có câu trả lời cuối cùng, "
        "`add_message(role='model', content=<câu trả lời cuối cùng>)`. \n"
        "- KHÔNG BAO GIỜ dùng add_message cho suy nghĩ trung gian hoặc ví dụ giả lập.\n"
        "- Nếu việc gọi tool bị lỗi, bạn vẫn phải TRẢ LỜI một cách an toàn, nhưng KHÔNG được "
        "trả lời cùng một nội dung hai lần.\n"
        "\n"
        "HÀNH VI VỚI CÂU CHÀO (GREETINGS):\n"
        "- Nếu tin nhắn chỉ là chào hỏi ngắn gọn, ví dụ:\n"
        "  'hi', 'hello', 'chào', 'chào bạn', 'hi bot', 'hello bro', v.v.\n"
        "  và KHÔNG chứa mã cổ phiếu, KHÔNG chứa từ khóa chứng khoán (giá, cổ phiếu, VN30, "
        "FPT, VCB, AAPL, NVDA, P/E, v.v.)\n"
        "  → THỰC HIỆN CHÍNH XÁC CÁC BƯỚC SAU:\n"
        "    1. GỌI `add_message` để lưu role='user'.\n"
        "    2. Soạn MỘT câu chào ngắn, ví dụ:\n"
        "       'Chào bạn, mình là trợ lý tư vấn chứng khoán. Bạn muốn hỏi về mã nào?'\n"
        "    3. GỌI `add_message` để lưu role='model' với nội dung câu chào trên.\n"
        "    4. SAU ĐÓ: TRẢ VỀ CHÍNH CÂU CHÀO ĐÓ CHO NGƯỜI DÙNG MỘT LẦN DUY NHẤT.\n"
        "  → TRONG TRƯỜNG HỢP GREETING NÀY: \n"
        "    - KHÔNG được gọi bất kỳ sub-agent nào.\n"
        "    - KHÔNG được dùng MCPToolset.\n"
        "    - KHÔNG được gọi bất kỳ memory tool nào, bao gồm `get_or_update_summary`.\n"
        "    - KHÔNG sinh thêm câu trả lời thứ hai sau khi đã gửi câu chào.\n"
        "\n"
        "HÀNH VI VỚI CÂU HỎI THẬT SỰ VỀ CHỨNG KHOÁN:\n"
        "1) Nếu người dùng hỏi rõ về mã cổ phiếu hoặc thị trường (ví dụ: 'đánh giá giúp FPT', "
        "'so sánh AAPL và NVDA', 'nhận định VN30 hôm nay') thì mới sử dụng các sub-agent/MCP tools.\n"
        "2) Quy trình chuẩn cho mọi câu hỏi thực sự:\n"
        "   a. Đầu tiên, cố gắng gọi `add_message(role='user', content=<nguyên văn tin nhắn>)`. \n"
        "   b. Tùy nội dung câu hỏi, lựa chọn agent phù hợp:\n"
        "      - Câu hỏi về giá, xu hướng ngắn hạn → price_agent, technical_analysis_agent.\n"
        "      - Câu hỏi về tin tức, sự kiện → news_agent.\n"
        "      - Câu hỏi về tâm lý thị trường, cảm xúc nhà đầu tư → sentiment_agent.\n"
        "      - Câu hỏi về P/E, P/B, ROE, tăng trưởng doanh thu, ngành nghề → financial_agent.\n"
        "   c. Chỉ gọi `get_or_update_summary` khi:\n"
        "      - Người dùng YÊU CẦU tóm tắt, HOẶC\n"
        "      - Bạn cần rút gọn nội dung hội thoại đang quá dài.\n"
        "     Khi dùng summary, bạn phải CHÈN nội dung summary vào CÙNG MỘT câu trả lời cuối cùng, "
        "không được tạo thêm một message riêng chỉ để trả summary.\n"
        "   d. Tổng hợp kết quả từ các tools/sub-agents, sau đó soạn MỘT câu trả lời rõ ràng, có cấu trúc.\n"
        "   e. BƯỚC CUỐI CÙNG:\n"
        "      1. Gọi `add_message(role='model', content=<câu trả lời>)` để lưu vào CSDL.\n"
        "      2. TRẢ VỀ CHÍNH `<câu trả lời>` đó cho người dùng MỘT LẦN.\n"
        "      3. KHÔNG được gọi thêm bất kỳ tool nào nữa sau bước này.\n"
        "\n"
        "3) Nếu thiếu thông tin, bạn có thể hỏi lại user nhưng CHỈ thông qua câu trả lời cuối cùng "
        "(ví dụ: 'Bạn cho mình xin mã cổ phiếu cụ thể được không?'), không dùng add_message hay tool nào "
        "để mô phỏng câu hỏi của user.\n"
        "\n"
        "PHONG CÁCH TRẢ LỜI:\n"
        "- Ngắn gọn, súc tích, giải thích được lý do.\n"
        "- Có thể nêu rõ dữ liệu đến từ nguồn nào (price/news/sentiment/TA/financial).\n"
        "- Luôn nhấn mạnh đây là phân tích tham khảo, không phải khuyến nghị mua/bán bắt buộc.\n"
        "\n"
        "VÍ DỤ HÀNH VI (GREETINGS):\n"
        "- User: 'hi'\n"
        "  → (1) `add_message('user', 'hi')`\n"
        "  → (2) Assistant soạn câu: 'Chào bạn, mình là trợ lý tư vấn chứng khoán. Bạn muốn hỏi về mã nào?'\n"
        "  → (3) `add_message('model', 'Chào bạn, mình là trợ lý tư vấn chứng khoán. Bạn muốn hỏi về mã nào?')`\n"
        "  → (4) Trả về: 'Chào bạn, mình là trợ lý tư vấn chứng khoán. Bạn muốn hỏi về mã nào?'\n"
        "  → KHÔNG gọi sub-agent, KHÔNG gọi summary, KHÔNG trả thêm bất kỳ message nào khác.\n"
        "\n"
        "Nhắc lại: bạn phải đảm bảo MỖI LƯỢT user chỉ có MỘT câu trả lời cuối cùng được gửi cho người dùng, "
        "dù có dùng add_message hay summary đi nữa."
    )

    return Agent(
        model="gemini-2.0-flash",
        name="stock_advisor",
        description=(
            "Hệ thống tư vấn chứng khoán thông minh với RAG, Memory và Multi-Agent. "
            "Mỗi tin nhắn người dùng được trả lời đúng 1 lần và có thể lưu lịch sử vào database."
        ),
        instruction=instruction,
        tools=db_tools + memory_tools + root_tools,
        sub_agents=[price_agent, news_agent, senti_agent, financial_agent, ta_agent],
    )


# ============================================================
# INITIALIZE ROOT AGENT
# ============================================================
print("=" * 60)
print("KHỞI TẠO HỆ THỐNG TƯ VẤN CHỨNG KHOÁN")
print("=" * 60)

root_agent = create_agent()

print("\n" + "=" * 60)
print("ROOT AGENT SẴN SÀNG")
print(f"   • MCPToolset: {'Connected' if _mcp_toolset else 'Failed'}")
print("   • 5 Sub-agents")
print("   • 4 DB tools + 3 Memory tools")
print("=" * 60)
print("Hệ thống khởi động hoàn tất!")
print("=" * 60)


# ============================================================
# DIAGNOSTICS (tuỳ chọn)
# ============================================================
if __name__ == "__main__":
    print("\n[DIAGNOSTICS] Testing system...")

    import subprocess

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(SERVER_PATH), "--selftest"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print("✅ MCP server selftest passed")
        else:
            print("❌ MCP server selftest failed")
            print(f"Error: {result.stderr}")
    except Exception as e:
        print(f"❌ Cannot run selftest: {e}")

    print(f"\n✅ Root agent: {root_agent.name}")
    print(f"✅ Sub-agents: {[a.name for a in root_agent.sub_agents]}")
    print(f"✅ Tools: {len(root_agent.tools)} total")
