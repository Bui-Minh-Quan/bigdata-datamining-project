import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

import pandas as pd 
from langchain.prompts import PromptTemplate
from database.db import get_database
try:
    from etl.graph_loader import GraphLoader
    from etl.llm_client import APIKeyManager, get_llm_chain
    from etl.extractor import invoke_chain_with_retry
except:
    from llm_client import APIKeyManager, get_llm_chain
    from graph_loader import GraphLoader
    from extractor import invoke_chain_with_retry
    
PREDICTION_PROMPT = PromptTemplate.from_template("""
Bạn là một chuyên gia phân tích tài chính cấp cao (Financial Analyst).
Nhiệm vụ của bạn là dự đoán xu hướng giá cổ phiếu {ticker} vào phiên giao dịch tiếp theo.
Dựa trên những dữ liệu đầu vào sau:
1. **Bối cảnh Thị trường & Chuỗi Tác động (Knowledge Graph):**
(Đây là các sự kiện và mối quan hệ quan trọng nhất đang diễn ra)
{graph_context}
2. **Tâm lý Nhà đầu tư (Social Sentiment):**
- Số bài viết tích cực có đề cập đến {ticker}: {positive_count}
- Số bài viết tiêu cực có đề cập đến {ticker}: {negative_count}
- Số bài viết trung lập có đề cập đến {ticker}: {neutral_count}
- Tổng số bài viết có đề cập đến {ticker}: {total_count}

3. **Xu hướng Giá cổ phiếu Gần đây:**
- Giá đóng cửa của {ticker} trong 5 phiên giao dịch gần nhất: {recent_prices}

Dựa trên các dữ liệu trên, yêu cầu:
- Hãy phân tích sự tương quan giữa các sự kiện vĩ mô trong Đồ thị với cổ phiếu {ticker}.
- Kết hợp với Tâm lý Nhà đầu tư và Xu hướng Giá cổ phiếu để đưa ra dự đoán.
- Đưa ra dự đoán xu hướng giá cổ phiếu {ticker} trong phiên giao dịch tiếp theo: Tăng(INCREASE), Giảm(DECREASE) hay ĐI NGANG (SIDEWAYS).

Định dạng trả về (BẮT BUỘC tuân thủ):
[TREND]: <INCREASE/DECREASE/SIDEWAYS>
[CONFIDENCE]: <MỨC ĐỘ TIN CẬY TỪ 0-100%>
[REASONING]: <Giải thích ngắn gọn trong 3 gạch đầu dòng>

(Ví dụ câu trả lời đúng định dạng:)
[TREND]: INCREASE
[CONFIDENCE]: 85%
[REASONING]:
- Sự kiện A trong đồ thị cho thấy triển vọng tích cực cho ngành B.
- Tâm lý nhà đầu tư hiện tại đang rất lạc quan với số lượng bài viết tích cực vượt trội.
- Giá cổ phiếu đã có xu hướng tăng trong 5 phiên gần nhất.
""")


class StockPredictor:
    def __init__(self):
        self.db = get_database()
        self.api_manager = APIKeyManager()
        
    def get_social_sentiment(self, target_date, ticker):
        sentiemnt_col = self.db["sentiment_from_posts"]
        
        # query based on target_date and target stock ticker
        doc = sentiemnt_col.find_one({"date": target_date, "taggedSymbols": ticker})
        if doc:
            return {
                "positive_posts": doc.get("positive_posts", 0),
                "negative_posts": doc.get("negative_posts", 0),
                "neutral_posts": doc.get("neutral_posts", 0),
                "total_posts": doc.get("total_posts", 0),
            }
    
    def get_recent_prices(self, ticker, target_date, days=5):
        prices_col = self.db["stock_price_data"]
        target_dt = pd.to_datetime(target_date)
        start_dt = target_dt - pd.Timedelta(days=10)  # buffer to ensure enough trading days
        
        cursor = prices_col.find({
            "symbol": ticker,
            "date": {"$gte": str(start_dt.date()), "$lt": str(target_dt.date())}
        }).sort("date", 1)
        
        prices = []
        for doc in cursor:
            prices.append((pd.to_datetime(doc["date"]), doc["close"]))
        
        # Get last 'days' trading days
        prices = sorted(prices, key=lambda x: x[0], reverse=True)[:days]
        prices = [price for date, price in sorted(prices)]
        
        return prices
    
    def predict(self, ticker, target_date, graph_context, recent_prices=None):
        # Prepare social sentiment data
        sentiment_data = self.get_social_sentiment(target_date, ticker)
        if not sentiment_data:
            print(f"No sentiment data for {ticker} on {target_date}")
            sentiment_data = {
                "positive_posts": 0,
                "negative_posts": 0,
                "neutral_posts": 0,
                "total_posts": 0,
            }
        # Prepare recent prices data
        if not recent_prices:
            recent_prices = self.get_recent_prices(ticker, target_date)
            if not recent_prices:
                print(f"No recent prices for {ticker} before {target_date}")
                recent_prices = []
        # Prepare prompt inputs
        prompt_inputs = {
            "ticker": ticker,
            "graph_context": graph_context,
            "positive_count": sentiment_data["positive_posts"],
            "negative_count": sentiment_data["negative_posts"],
            "neutral_count": sentiment_data["neutral_posts"],
            "total_count": sentiment_data["total_posts"],
            "recent_prices": recent_prices
        }
        
        # Get LLM chain
        try:
            response = invoke_chain_with_retry(
                PREDICTION_PROMPT,
                prompt_inputs,
                self.api_manager,
                model_name="gemini-2.5-flash"
            )
            
            return response.content 
        except Exception as e:
            print(f"Prediction LLM invocation error for {ticker}: {e}")
            return None

if __name__ == "__main__":
    mock_context = """
    2025-11-19, Cơ quan quản lý nhà nước, NEGATIVE, Bộ Tài chính
    2025-11-19, Doanh nghiệp Việt Nam, NEGATIVE, Bộ Tài chính
    2025-11-19, VIC-Bất động sản, POSITIVE, Doanh nghiệp Việt Nam
    """
    
    predictor = StockPredictor()
    result = predictor.predict("VIC", "2025-11-19", mock_context, recent_prices=[100, 102, 101, 103, 104])
    print("Prediction Result:")
    print(result)
        