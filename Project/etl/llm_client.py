import os
import time
from dotenv import load_dotenv
try:
    import google.generativeai as genai
except ImportError:
    print("Trying newer version of Google Gemini AI Library...")
    from google import genai
except Exception as e:
    print(f"Error importing google.generativeai: {e}")
    raise e

from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

class APIKeyManager:
    """
    Quản lý nhiều Google API keys và tự động chuyển đổi khi gặp lỗi.
    """
    MAX_RETRIES_PER_KEY = 2
    
    def __init__(self):
        raw_keys = [
            ("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY")),
            ("GOOGLE_API_KEY_1", os.getenv("GOOGLE_API_KEY_2")),
            ("GOOGLE_API_KEY_2", os.getenv("GOOGLE_API_KEY_2")),
            ("GOOGLE_API_KEY_3", os.getenv("GOOGLE_API_KEY_3")),
            ("GOOGLE_API_KEY_4", os.getenv("GOOGLE_API_KEY_4")),
        ]
        
        # Xử lý key: split để bỏ comment, strip để bỏ khoảng trắng
        self.keys = [
            (name, key.split(" ")[0].strip()) 
            for name, key in raw_keys 
            if key and key.strip()
        ]
        
        if not self.keys:
            raise ValueError("❌ Không tìm thấy API key! Kiểm tra file .env")
        
        self.current_index = 0
        self.error_counts = {name: 0 for name, _ in self.keys}
        print(f"✓ Phát hiện {len(self.keys)} API keys")
        self._activate_key(0)
    
    def _activate_key(self, index):
        if index >= len(self.keys):
            raise Exception("❌ Đã hết tất cả API keys!")
        
        self.current_index = index
        key_name, key_value = self.keys[index]
        
        # 1. Cấu hình cho thư viện google.generativeai
        genai.configure(api_key=key_value)
        
        # 2. QUAN TRỌNG: Cập nhật luôn biến môi trường để LangChain không bị nhầm Key cũ
        os.environ["GOOGLE_API_KEY"] = key_value
        
        print(f"🔑 Đang sử dụng: {key_name} (Key {index + 1}/{len(self.keys)})")
    
    def get_current_key(self):
        return self.keys[self.current_index][1]
    
    def on_error(self):
        key_name = self.keys[self.current_index][0]
        self.error_counts[key_name] += 1
        
        # Nếu key này đã lỗi quá số lần cho phép -> Đổi key
        if self.error_counts[key_name] >= self.MAX_RETRIES_PER_KEY:
            next_index = self.current_index + 1
            if next_index < len(self.keys):
                self._activate_key(next_index)
                return True # Đã đổi key thành công
            else:
                return False # Hết key để đổi
        
        return False # Chưa đổi key (vẫn retry key cũ)
    
    def reset_errors(self):
        self.error_counts = {name: 0 for name, _ in self.keys}

def get_llm_chain(api_manager, prompt_template, temperature=0.15, model_name="gemini-2.0-flash"):
    """
    Hàm helper để tạo LangChain chain với API key hiện tại
    """
    current_key = api_manager.get_current_key()

    model = ChatGoogleGenerativeAI(
        model=model_name, 
        temperature=temperature,
        api_key=current_key,
        max_retries=0,
    )
    
    # Sử dụng toán tử | (pipe) của LangChain để nối Prompt và Model
    chain = prompt_template | model
    return chain