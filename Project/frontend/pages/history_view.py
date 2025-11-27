import streamlit as st 
import pandas as pd 
import sys 
import os 
from datetime import datetime, timedelta 
import plotly.express as px 

# --- CẤU HÌNH ĐƯỜNG DẪN ---
# Để import được database.db từ thư mục cha (project root)
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(parent_dir)

from database.db import get_database


# Danh sách cổ phiếu cần theo dõi
PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Lịch sử dự đoán và Đánh giá",
    page_icon="📜",
    layout="wide"
)

with st.sidebar:
    st.header("Điều hướng")
    st.page_link("vietnam_stock_dashboard.py", label="Quay lại Dashboard", icon="🏠")
    st.page_link("pages/history_view.py", label="Lịch sử & Đánh giá", icon="📜")
    st.divider()


st.title("📜 Lịch sử & Đánh giá độ chính xác AI")
st.markdown("---")

# --- HÀM XỬ LÝ DỮ LIỆU (ĐÃ TỐI ƯU) ---
@st.cache_data(ttl=300) # Cache 5 phút để giảm tải cho DB
def load_and_process_data():
    db = get_database()
    if db is None: 
        return pd.DataFrame()
        
    # 1. Lấy dữ liệu dự đoán (Chỉ lấy các mã trong danh mục)
    predictions = list(db['stock_predictions'].find({
        "symbol": {"$in": PORTFOLIO_STOCKS}
    }))
    
    if not predictions:
        return pd.DataFrame()
    
    df_pred = pd.DataFrame(predictions)
    
    # 2. Tìm ngày dự đoán cũ nhất để giới hạn phạm vi lấy giá
    if "date" in df_pred.columns and not df_pred.empty:
        min_date_str = df_pred['date'].min()
        # Lùi lại vài ngày cho an toàn
        min_date_obj = datetime.strptime(min_date_str, "%Y-%m-%d") - timedelta(days=5)
        min_date_query = min_date_obj.strftime("%Y-%m-%d")
    else:
        min_date_query = "2024-01-01"
        
    # 3. TỐI ƯU HÓA QUERY GIÁ
    # Chỉ lấy các symbol cần thiết VÀ thời gian >= ngày dự đoán cũ nhất
    query_filter = {
        "symbol": {"$in": PORTFOLIO_STOCKS},
        "time": {"$gte": min_date_query}
    }
    
    # Projection: Chỉ lấy trường cần thiết (Giảm tải Network I/O)
    projection = {"symbol": 1, "time": 1, "close": 1, "_id": 0}
    
    prices = list(db["stock_price_data"].find(query_filter, projection))
    
    if not prices:
        return pd.DataFrame()
    
    df_price = pd.DataFrame(prices)
    
    # 4. Xử lý logic tìm "Giá phiên tiếp theo"
    df_price['time'] = pd.to_datetime(df_price["time"])
    df_price = df_price.sort_values(by=["symbol", "time"])
    
    # Shift(-1) để lấy giá ngày hôm sau đặt vào dòng ngày hôm nay
    df_price['next_close'] = df_price.groupby("symbol")['close'].shift(-1)
    df_price["next_date"] = df_price.groupby("symbol")['time'].shift(-1)
    
    # Convert lại sang string để merge
    df_price['date_str'] = df_price['time'].dt.strftime("%Y-%m-%d")
    
    # 5. Merge bảng Dự đoán với Bảng giá
    df_merged = pd.merge(
        df_pred,
        df_price[["symbol", "date_str", "close", "next_close", "next_date"]],
        left_on=["symbol", "date"],
        right_on=["symbol", "date_str"],
        how="left"
    )    
    
    # 6. Logic so sánh Xu hướng Dự đoán vs Thực tế
    def calculate_accuracy(row):
        if pd.isna(row["next_close"]):
            return "Chưa có dữ liệu", "Chưa có dữ liệu", 0
        
        current_price = row["close"]
        next_price = row["next_close"]
        pred_trend = row["trend"]
        
        # Xác định xu hướng thật
        actual_change = next_price - current_price 
        actual_trend = "SIDEWAYS"
        
        if actual_change > 0:
            actual_trend = "INCREASE"
        elif actual_change < 0:
            actual_trend = "DECREASE"
        
        trend_vi_map = {
            "INCREASE": "Tăng",
            "DECREASE": "Giảm",
            "SIDEWAYS": "Đi ngang",
            "UNKNOWN": "Không rõ" 
        }
        
        is_correct = "Sai"
        if pred_trend == actual_trend:
            is_correct = "Đúng"
        elif pred_trend == "UNKNOWN":
            is_correct = "Không xác định"
        
        return is_correct, trend_vi_map.get(actual_trend, "Không rõ"), actual_change
    
    # Apply logic
    results = df_merged.apply(calculate_accuracy, axis=1, result_type="expand")
    df_merged[["accuracy", "actual_trend_vi", "price_change"]] = results
    
    # Mapping xu hướng dự đoán sang tiếng Việt
    trend_map = {"INCREASE": "Tăng", "DECREASE": "Giảm", "SIDEWAYS": "Đi ngang", "UNKNOWN": "Không rõ"}
    df_merged["pred_trend_vi"] = df_merged['trend'].map(trend_map)
    
    # Chọn cột cuối cùng
    final_df = df_merged[[
        'symbol', "date", "pred_trend_vi", "confidence", "reasoning",
        "close", "next_date", "next_close", "actual_trend_vi", "accuracy", "price_change", "full_analysis"
    ]]
    
    final_df.columns = [
        "Mã CP", "Ngày dự đoán", "Dự đoán", "Độ tin cậy", "Lý do",
        "Giá đóng phiên", "Ngày phiên sau", "Giá phiên sau", "Thực tế", 'Kết quả', "Thay đổi giá", "Phân tích chi tiết"
    ]
    
    return final_df

# --- GIAO DIỆN CHÍNH (MAIN UI) ---
try:
    df = load_and_process_data()
    
    if df.empty:
        st.warning("⚠️ Chưa có dữ liệu dự đoán hoặc dữ liệu giá trong Database.")
    else:
        # --- SIDEBAR FILTERS ---
        st.sidebar.header("🔍 Bộ lọc & Sắp xếp")
        
        # Filter Symbol
        all_symbols = ['Tất cả'] + sorted(df['Mã CP'].unique().tolist())
        selected_symbol = st.sidebar.selectbox("Chọn Cổ phiếu", all_symbols)
        
        # Filter Result
        all_results = ['Tất cả', 'Đúng', 'Sai', 'Chưa có dữ liệu']
        selected_result = st.sidebar.selectbox("Kết quả dự đoán", all_results)
        
        # Filter Trend
        all_trends = ['Tất cả', 'Tăng', 'Giảm', 'Đi ngang']
        selected_trend = st.sidebar.selectbox("Xu hướng dự đoán", all_trends)
        
        # Sorting
        sort_order = st.sidebar.radio("Sắp xếp theo ngày", ["Mới nhất trước", "Cũ nhất trước"])
        
        # --- ÁP DỤNG BỘ LỌC ---
        filtered_df = df.copy()
        
        if selected_symbol != 'Tất cả':
            filtered_df = filtered_df[filtered_df["Mã CP"] == selected_symbol]
        
        if selected_result != "Tất cả":
            filtered_df = filtered_df[filtered_df["Kết quả"] == selected_result]
        
        if selected_trend != "Tất cả":
            filtered_df = filtered_df[filtered_df["Dự đoán"] == selected_trend]
        
        # Sort data
        filtered_df["Ngày dự đoán"] = pd.to_datetime(filtered_df["Ngày dự đoán"])
        if sort_order == "Mới nhất trước":
            filtered_df = filtered_df.sort_values(by='Ngày dự đoán', ascending=False)
        else:
            filtered_df = filtered_df.sort_values(by='Ngày dự đoán', ascending=True)
        
        # remove rows if "Ngày dự đoán" >= "Ngày phiên sau"
        filtered_df = filtered_df[filtered_df["Ngày dự đoán"] < filtered_df["Ngày phiên sau"]]
        
        filtered_df['Ngày dự đoán'] = filtered_df['Ngày dự đoán'].dt.strftime('%Y-%m-%d')
        filtered_df['Ngày phiên sau'] = pd.to_datetime(filtered_df['Ngày phiên sau']).dt.strftime('%Y-%m-%d')
        
        # multiply "Giá đóng phiên", "Giá phiên sau", "Thay đổi giá" by 1000 to convert to VND
        filtered_df["Giá đóng phiên"] = filtered_df["Giá đóng phiên"] * 1000
        filtered_df["Giá phiên sau"] = filtered_df["Giá phiên sau"] * 1000
        filtered_df["Thay đổi giá"] = filtered_df["Thay đổi giá"] * 1000
        
        # --- METRICS SUMMARY ---
        valid_preds = filtered_df[filtered_df["Kết quả"].isin(["Đúng", "Sai"])]
        accuracy_rate = 0
        if len(valid_preds) > 0:
            correct_count = len(valid_preds[valid_preds["Kết quả"] == "Đúng"])
            accuracy_rate = (correct_count / len(valid_preds)) * 100
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tổng số dự đoán", len(filtered_df))
        m2.metric("Đã có kết quả thực tế", len(valid_preds))
        m3.metric("Số lần đúng", len(valid_preds[valid_preds['Kết quả'] == 'Đúng']) if len(valid_preds)>0 else 0)
        m4.metric("Tỷ lệ chính xác", f"{accuracy_rate:.1f}%")
        
        st.divider()
        
        # --- BẢNG DỮ LIỆU (MASTER VIEW) ---
        
        # Tạo cột tóm tắt lý do để hiển thị gọn trên bảng
        filtered_df["Lý do tóm tắt"] = filtered_df["Lý do"].apply(lambda x: str(x)[:70] + "..." if len(str(x)) > 70 else str(x))

        def highlight_result(val):
            color = 'green' if val == "Đúng" else ("red" if val == "Sai" else "gray")
            return f'color: {color}; font-weight: bold'
        
        st.subheader("Bảng chi tiết")
        st.caption("👇 **Bấm vào một dòng** để xem phân tích chi tiết bên dưới.")
        
        event = st.dataframe(
            filtered_df.style.applymap(highlight_result, subset=["Kết quả"]),
            column_config={
                "Lý do tóm tắt": st.column_config.TextColumn("Lý do (Tóm tắt)", width="medium"),
                "Độ tin cậy": st.column_config.TextColumn("Độ tin cậy", width="small"),
                "Giá đóng phiên": st.column_config.NumberColumn("Giá đóng ngày dự đoán", format="%.0f ₫"),
                "Ngày phiên sau": st.column_config.TextColumn("Ngày phiên sau"),
                "Giá phiên sau": st.column_config.NumberColumn("Giá đóng phiên sau", format="%.0f ₫"),
                "Thay đổi giá": st.column_config.NumberColumn("Thay đổi", format="%.0f ₫"),
                # Ẩn các cột dài hoặc không cần thiết trên bảng chính
                "Lý do": None, 
                "Phân tích chi tiết": None
            },
            column_order=["Mã CP", "Ngày dự đoán", "Dự đoán", "Độ tin cậy", "Lý do tóm tắt", "Giá đóng phiên", "Ngày phiên sau", "Giá phiên sau", "Kết quả", "Thay đổi giá"],
            width='stretch',
            hide_index=True,
            height=400,
            on_select="rerun",          # Kích hoạt tính năng chọn
            selection_mode="single-row" # Chỉ chọn 1 dòng
        )

        # --- CHI TIẾT DỰ ĐOÁN (DETAIL VIEW) ---
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            # Lấy dòng dữ liệu tương ứng (dùng iloc vì index của filtered_df có thể không liên tục)
            row = filtered_df.iloc[selected_index]
            
            st.divider()
            st.markdown(f"### 🔎 Chi tiết: {row['Mã CP']} - Ngày {row['Ngày dự đoán']}")
            
            c1, c2 = st.columns([1, 2])
            
            with c1:
                st.info(f"**Kết quả:** {row['Kết quả']}")
                st.write(f"**Xu hướng dự đoán:** {row['Dự đoán']}")
                st.write(f"**Độ tin cậy:** {row['Độ tin cậy']}")
                st.write(f"**Giá thực tế:** {row['Giá phiên sau']} ({row['Thay đổi giá']}₫)")
                
            with c2:
                with st.container(border=True):
                    st.markdown("**📝 Lý do chính:**")
                    # Render xuống dòng cho dễ đọc
                    st.markdown(str(row['Lý do']).replace("\n", "  \n"))
                
                with st.expander("🤖 Xem Log phân tích đầy đủ (Raw Data)"):
                    st.code(row['Phân tích chi tiết'], language='text')
        
        elif not filtered_df.empty:
            st.info("👆 Hãy chọn một dòng trong bảng trên để xem phân tích chi tiết.")

except Exception as e:
    st.error(f"❌ Đã xảy ra lỗi: {str(e)}")
    import traceback 
    st.text(traceback.format_exc())