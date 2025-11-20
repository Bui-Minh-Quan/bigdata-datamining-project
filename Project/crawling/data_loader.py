import os
import sys
import io
import time
from datetime import datetime, timedelta

# --- QUAN TRỌNG: Ép encoding sang UTF-8 ngay lập tức ---
# Fix lỗi UnicodeDecodeError trên Windows khi in ra console
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except Exception:
    pass # Bỏ qua nếu không thể set encoding (hiếm gặp)

import pandas as pd
from vnstock import Quote

# Setup đường dẫn dự án
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from database.db import get_database

# Kết nối DB
db = get_database()

PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

def format_date(d):
    """Chuyển đổi mọi định dạng ngày về YYYY-MM-DD string"""
    if isinstance(d, str): return d.split(" ")[0]
    try: return d.strftime("%Y-%m-%d")
    except: return str(d)

def fetch_recent_data_online():
    print(">> Dang tai du lieu bo sung (30 ngay gan nhat) tu VnStock...")
    
    col = db["stock_price_data"]
    
    # Lấy dư ra 35 ngày cho chắc chắn
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
    
    for symbol in PORTFOLIO_STOCKS:
        try:
            # Lấy dữ liệu từ vnstock
            df = Quote(symbol=symbol.lower(), source='vci').history(start=start_date, end=end_date, interval='1D')
            
            if not df.empty:
                count = 0
                for _, row in df.iterrows():
                    # Ép kiểu dữ liệu an toàn cho MongoDB
                    record = {
                        "symbol": symbol,
                        "time": format_date(row['time']),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": int(row['volume'])
                    }
                    
                    # Upsert vào MongoDB
                    col.update_one(
                        {"symbol": record["symbol"], "time": record["time"]},
                        {"$set": record},
                        upsert=True
                    )
                    count += 1
                print(f"   + Da cap nhat {symbol}: {count} phien.")
            else:
                print(f"   - Khong co du lieu moi cho {symbol}")
            
            # Delay nhẹ để tránh bị chặn IP
            time.sleep(1)
            
        except Exception as e:
            # In lỗi không dấu để tránh crash
            print(f"   ! Loi tai {symbol}: {e}")

if __name__ == "__main__":
    # Tự động tải thêm dữ liệu mới nhất để lấp đầy khoảng trống
    fetch_recent_data_online()
    
    print("\n>> HOAN TAT! MongoDB da co du du lieu gia cho main.py phan tich.")