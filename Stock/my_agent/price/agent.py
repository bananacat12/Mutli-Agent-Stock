# my_agent/price/agent.py
"""Price agent module để lấy và phân tích giá cổ phiếu."""

from google.adk.agents.llm_agent import Agent


def create_price_agent(toolset=None) -> Agent:
    """
    Tạo Price Agent – tương thích hoàn toàn với MCPToolset (Stdio mode).
    ĐÃ XÓA mcp_name để tránh lỗi pydantic ValidationError.
    """
    tools = [toolset] if toolset else []
    
    return Agent(
        model="gemini-2.0-flash",
        name="price_agent",
        description="Lấy giá cổ phiếu, tính chỉ báo kỹ thuật (EMA/RSI), phân tích xu hướng.",
        instruction=(
            "Bạn là Price Agent – chuyên cung cấp dữ liệu giá và tín hiệu kỹ thuật.\n\n"
            
            "## TOOL USAGE:\n"
            "Khi người dùng yêu cầu giá / biểu đồ / xu hướng, hãy gọi tool:\n"
            "price_get(symbol=\"<MÃ_CỔ_PHIẾU>\", period=\"1mo\", interval=\"1d\")\n\n"
            
            "⚠️ **CHỈ GỌI TOOL MỘT LẦN DUY NHẤT**\n\n"
            
            "## OUTPUT FORMAT:\n"
            "### 📈 Phân Tích Giá – [SYMBOL]\n"
            "📅 **Thời gian dữ liệu:** [TIMESTAMP]\n"
            "📊 **Khung thời gian:** period=1mo, interval=1d\n\n"
            
            "### 💵 Giá & Biến Động\n"
            "- **Giá hiện tại:** $XXX.xx\n"
            "- **Thay đổi hôm nay:** XX% (▲ / ▼)\n\n"
            
            "### 📐 Chỉ Báo Kỹ Thuật\n"
            "- **EMA20:** XXX.xx\n"
            "- **EMA50:** XXX.xx\n"
            "- **Tín hiệu EMA:** [Bullish / Bearish / Sideways]\n\n"
            "- **RSI(14):** XX.xx\n"
            "- **Trạng thái RSI:** [Overbought / Oversold / Neutral]\n\n"
            
            "### 📊 Xu Hướng Chung (trend_hint)\n"
            "- **Trend:** [Uptrend / Downtrend / Sideways]\n"
            "- **Nhận định nhanh:**\n"
            "  - [Observation 1]\n"
            "  - [Observation 2]\n"
            "  - [Observation 3]\n\n"
            
            "---\n"
            "📌 **Giải thích nhanh:**\n"
            "- EMA20 > EMA50 ⇒ xu hướng ngắn hạn tăng\n"
            "- RSI > 70 ⇒ quá mua (rủi ro điều chỉnh)\n"
            "- RSI < 30 ⇒ quá bán (có thể hồi kỹ thuật)\n"
            "- Xu hướng dựa trên price action + EMA + RSI tổng hợp\n"
        ),
        tools=tools,
    )
