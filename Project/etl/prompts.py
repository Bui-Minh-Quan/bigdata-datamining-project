from langchain_core.prompts import PromptTemplate

# =============================================================================
# 1. ENTITY EXTRACTION (Xử lý 1 bài lẻ)
# =============================================================================
ENTITY_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn là chuyên gia phân tích tài chính. Nhiệm vụ của bạn là trích xuất các thực thể (Cổ phiếu, Công ty, Ngành, Quốc gia...) chịu ảnh hưởng từ bài báo.

DANH MỤC CỔ PHIẾU CẦN THEO DÕI (PORTFOLIO):
{portfolio}

QUY TẮC BẮT BUỘC (CRITICAL RULES):
1. NẾU thực thể là công ty trong Portfolio trên:
   - BẮT BUỘC chỉ dùng MÃ CỔ PHIẾU làm tên thực thể.
   - Ví dụ: Dùng "HPG" (thay vì "Tập đoàn Hòa Phát"), dùng "MWG" (thay vì "Thế giới di động").
   - KHÔNG thêm tên ngành hay mô tả vào trong tên (VD: Sai -> "FPT Công nghệ", Đúng -> "FPT").

2. XỬ LÝ CÁC TỪ CHUNG CHUNG (BLACKLIST):
   - TUYỆT ĐỐI KHÔNG dùng các từ sau làm thực thể độc lập: "Doanh nghiệp", "Công ty", "Nhà đầu tư", "Người dân", "Thị trường", "Kinh tế", "Việt Nam", "Chính phủ", "Nhà nước", "Khách hàng", "Người tiêu dùng".
   - PHẢI cụ thể hóa chúng theo Ngành hoặc Nhóm đối tượng.
     + Sai: "Doanh nghiệp" -> Đúng: "Doanh nghiệp Bất động sản", "Các công ty xuất khẩu".
     + Sai: "Nhà đầu tư" -> Đúng: "Khối ngoại", "Nhà đầu tư cá nhân".
     + Sai: "Người dân" -> Đúng: "Người mua nhà", "Tầng lớp trung lưu".
   - Nếu không thể cụ thể hóa, hãy BỎ QUA thực thể đó.

3. Ưu tiên liên kết với các thực thể đã có: {existing_entities}
4. Chỉ trích xuất tối đa 5 thực thể quan trọng nhất.

Định dạng trả về:
[[POSITIVE]]
[Mã_CP_hoặc_Tên_Cụ_Thể]: [Giải thích ngắn gọn nguyên nhân và số liệu]

[[NEGATIVE]]
[Mã_CP_hoặc_Tên_Cụ_Thể]: [Giải thích ngắn gọn nguyên nhân và số liệu]

----------------
(VÍ DỤ MINH HỌA)

Bài báo: Các doanh nghiệp gặp khó vì tỷ giá. Người dân thắt chặt chi tiêu. Vinamilk vẫn lãi lớn.
Danh sách thực thể:

[[POSITIVE]]
VNM: Doanh thu ổn định nhờ vị thế đầu ngành sữa, bất chấp sức mua giảm.

[[NEGATIVE]]
Doanh nghiệp nhập khẩu: Chịu áp lực chi phí đầu vào tăng cao do tỷ giá.
Ngành bán lẻ: Doanh thu sụt giảm do người tiêu dùng thắt chặt chi tiêu.
(Lưu ý: Không dùng "Doanh nghiệp", "Người dân" chung chung)

(HẾT VÍ DỤ)
----------------

DỮ LIỆU ĐẦU VÀO:
Ngày đăng: {date}
Mã liên quan: {stockCodes}
Tiêu đề: {title}
Mô tả: {description}

Danh sách thực thể sẽ bị ảnh hưởng:
""")

# =============================================================================
# 2. RELATION EXTRACTION (Xử lý quan hệ 1-1)
# =============================================================================
RELATION_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn đang phân tích hiệu ứng dây chuyền trong kinh tế.
Dựa trên tác động đến "Thực thể gốc", hãy suy luận các thực thể khác bị ảnh hưởng tiếp theo.

DANH MỤC ĐẦU TƯ: {portfolio}
THỰC THỂ ĐÃ CÓ: {existing_entities}

QUY TẮC ĐẶT TÊN THỰC THỂ (BẮT BUỘC TUÂN THỦ):
1. NẾU thực thể là công ty trong Portfolio trên:
   - BẮT BUỘC chỉ dùng MÃ CỔ PHIẾU làm tên thực thể.
   - Ví dụ: Dùng "HPG" (thay vì "Tập đoàn Hòa Phát"), dùng "MWG" (thay vì "Thế giới di động").
   - KHÔNG thêm tên ngành hay mô tả vào trong tên (VD: Sai -> "FPT Công nghệ", Đúng -> "FPT").
   
2. XỬ LÝ CÁC TỪ CHUNG CHUNG (BLACKLIST):
   - TUYỆT ĐỐI KHÔNG dùng các từ sau làm thực thể độc lập: "Doanh nghiệp", "Công ty", "Nhà đầu tư", "Người dân", "Thị trường", "Kinh tế", "Việt Nam", "Chính phủ", "Nhà nước", "Khách hàng", "Người tiêu dùng".
   - PHẢI cụ thể hóa chúng theo Ngành hoặc Nhóm đối tượng.
     + Sai: "Doanh nghiệp" -> Đúng: "Doanh nghiệp Bất động sản", "Các công ty xuất khẩu".
     + Sai: "Nhà đầu tư" -> Đúng: "Khối ngoại", "Nhà đầu tư cá nhân".
     + Sai: "Người dân" -> Đúng: "Người mua nhà", "Tầng lớp trung lưu".
   - Nếu không thể cụ thể hóa, hãy BỎ QUA thực thể đó.
3. Hạn chế tạo thực thể mới, Ưu tiên liên kết với các thực thể đã có: {existing_entities}

Định dạng trả về:
[[POSITIVE]]
[Entity 1]: [Giải thích]
...
[[NEGATIVE]]
[Entity A]: [Giải thích]
...

(VÍ DỤ)
Thực thể gốc: Bộ Xây dựng
Ảnh hưởng ban đầu: Thúc đẩy giải ngân đầu tư công cho 3000km cao tốc.

Kết quả suy luận:
[[POSITIVE]]
HPG: Nhu cầu thép xây dựng tăng cao nhờ các dự án cao tốc trọng điểm.
Ngành xây dựng hạ tầng: Khối lượng công việc tăng mạnh, đảm bảo doanh thu gối đầu.
[[NEGATIVE]]
Ngân sách Nhà nước: Áp lực cân đối vốn lớn trong ngắn hạn.
(HẾT VÍ DỤ)

Thực thể gốc: {entities}
Ảnh hưởng ban đầu: {description}

Danh sách thực thể bị ảnh hưởng tiếp theo (Hiệu ứng dây chuyền):
""")

# =============================================================================
# 3. BATCH RELATION EXTRACTION (Xử lý nhiều thực thể cùng lúc - Phase 2)
# =============================================================================
BATCH_RELATION_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn đang phân tích chuỗi cung ứng và tác động kinh tế.
Dưới đây là danh sách các thực thể và tác động họ đang chịu. Hãy suy luận xem điều này ảnh hưởng tiếp đến ai?

DANH MỤC ƯU TIÊN (PORTFOLIO): {portfolio}
THỰC THỂ ĐÃ CÓ: {existing_entities}

QUY TẮC (BẮT BUỘC TUÂN THỦ):
1. NẾU thực thể là công ty trong Portfolio trên:
   - BẮT BUỘC chỉ dùng MÃ CỔ PHIẾU làm tên thực thể.
   - Ví dụ: Dùng "HPG" (thay vì "Tập đoàn Hòa Phát"), dùng "MWG" (thay vì "Thế giới di động").
   - KHÔNG thêm tên ngành hay mô tả vào trong tên (VD: Sai -> "FPT Công nghệ", Đúng -> "FPT").
2. XỬ LÝ CÁC TỪ CHUNG CHUNG (BLACKLIST):
   - TUYỆT ĐỐI KHÔNG dùng các từ sau làm thực thể độc lập: "Doanh nghiệp", "Công ty", "Nhà đầu tư", "Người dân", "Thị trường", "Kinh tế", "Việt Nam", "Chính phủ", "Nhà nước", "Khách hàng", "Người tiêu dùng".
   - PHẢI cụ thể hóa chúng theo Ngành hoặc Nhóm đối tượng.
     + Sai: "Doanh nghiệp" -> Đúng: "Doanh nghiệp Bất động sản", "Các công ty xuất khẩu".
     + Sai: "Nhà đầu tư" -> Đúng: "Khối ngoại", "Nhà đầu tư cá nhân".
     + Sai: "Người dân" -> Đúng: "Người mua nhà", "Tầng lớp trung lưu".
   - Nếu không thể cụ thể hóa, hãy BỎ QUA thực thể đó.
3. Ưu tiên liên kết với các thực thể đã có: {existing_entities}
3. Mỗi thực thể gốc chỉ suy luận ra tối đa 3 thực thể bị ảnh hưởng tiếp theo.

Định dạng Output:
[[SOURCE: Tên thực thể nguồn]]
[[IMPACT: POSITIVE/NEGATIVE]]

[[POSITIVE]]
[Tên Thực Thể A]: [Giải thích]
[Tên Thực Thể B]: [Giải thích]

[[NEGATIVE]]
[Tên Thực Thể C]: [Giải thích]

----------------
DANH SÁCH THỰC THỂ NGUỒN:
{input_entities}

SUY LUẬN HIỆU ỨNG DÂY CHUYỀN:
""")


# =============================================================================
# 4. BATCH ARTICLE EXTRACTION (Prompt quan trọng nhất - Phase 1)
# =============================================================================
BATCH_ARTICLE_EXTRACTION_PROMPT = PromptTemplate.from_template("""
Bạn là chuyên gia phân tích vĩ mô và thị trường chứng khoán (Senior Financial Analyst).
Nhiệm vụ của bạn là xây dựng "Đồ thị Tri thức Tài chính" (Financial Knowledge Graph) từ danh sách tin tức thô.

Bạn cần trích xuất các thực thể chịu tác động và cơ chế tác động của tin tức đó.

=========================================
📋 THÔNG TIN QUAN TRỌNG (CONTEXT)
=========================================
1. DANH MỤC CỔ PHIẾU ƯU TIÊN (PORTFOLIO):
   {portfolio}

2. CÁC THỰC THỂ ĐÃ TỒN TẠI TRONG ĐỒ THỊ:
   {existing_entities}
   (Lưu ý: Hãy cố gắng tái sử dụng các tên thực thể này nếu ngữ nghĩa phù hợp, tránh tạo thực thể trùng lặp)

=========================================
⚠️ QUY TẮC XỬ LÝ (BẮT BUỘC TUÂN THỦ)
=========================================

Quy tắc 1: ĐỊNH DANH CỔ PHIẾU (QUAN TRỌNG NHẤT)
   - Nếu thực thể là công ty nằm trong danh sách PORTFOLIO, bạn **BẮT BUỘC** dùng **MÃ CỔ PHIẾU 3 CHỮ CÁI** làm tên thực thể.
   - TUYỆT ĐỐI KHÔNG dùng tên đầy đủ, tên tiếng Việt hay tên kèm ngành nghề.
   - Ví dụ sai ❌: "Tập đoàn Hòa Phát", "Cổ phiếu HPG", "HPG Steel", "Vinamilk".
   - Ví dụ đúng ✅: "HPG", "VNM", "VCB", "FPT".

Quy tắc 2: "CẤM CỬA" TỪ KHÓA CHUNG CHUNG (ANTI-SUPER NODES)
   - Bạn TUYỆT ĐỐI KHÔNG được tạo ra các node có tên sau:
     ["Doanh nghiệp", "Công ty", "Nhà đầu tư", "Người dân", "Thị trường", "Kinh tế", "Việt Nam", "Chính phủ", "Nhà nước", "Khách hàng", "Người lao động", "Xã hội"].
   
   - Thay vào đó, bạn PHẢI cụ thể hóa chúng:
     ❌ "Doanh nghiệp" -> ✅ "Doanh nghiệp Xuất khẩu", "Doanh nghiệp BĐS", "SME".
     ❌ "Nhà đầu tư"   -> ✅ "Khối ngoại", "Tự doanh", "Nhà đầu tư cá nhân".
     ❌ "Người dân"    -> ✅ "Người mua nhà", "Tầng lớp thu nhập thấp".
     ❌ "Nhà nước"     -> ✅ "Ngân hàng Nhà nước", "Bộ Tài chính", "Ngân sách Nhà nước".
   
   - Nếu tin tức quá chung chung và không thể cụ thể hóa -> HÃY BỎ QUA, không trích xuất.

Quy tắc 3: PHÂN TÍCH TÁC ĐỘNG (IMPACT)
   - Chỉ trích xuất tối đa **3-4 thực thể** quan trọng nhất chịu ảnh hưởng trực tiếp.
   - Phần giải thích phải ngắn gọn, chứa từ khóa kinh tế (doanh thu, lợi nhuận, chi phí đầu vào, tâm lý thị trường, tỷ giá...).
   - Nếu tin tức có số liệu cụ thể (tăng 5%, lãi 1000 tỷ...), hãy đưa vào phần giải thích.
   
Quy tắc 4: ƯU TIÊN NGÀNH VÀ HÀNG HÓA
   - Nếu không xác định được công ty cụ thể, hãy dùng tên NGÀNH (VD: Ngành Thép, Ngành Du lịch, Ngành Ngân hàng).
   - Các biến số vĩ mô: "Tỷ giá", "Lãi suất", "Giá vàng", "Giá dầu".

=========================================
📝 ĐỊNH DẠNG GIAO TIẾP
=========================================
Dữ liệu đầu vào (Batch):
[ID: 1] Tiêu đề bản tin | Nội dung tóm tắt...
[ID: 2] Tiêu đề bản tin | Nội dung tóm tắt...

Dữ liệu đầu ra mong đợi:
[[ARTICLE_ID: 1]]
[[POSITIVE]]
[Mã_CP_hoặc_Tên_Chuẩn]: [Lý do ngắn gọn]
[[NEGATIVE]]
[Mã_CP_hoặc_Tên_Chuẩn]: [Lý do ngắn gọn]

-----------------------------------------
VÍ DỤ MINH HỌA (MẪU CHUẨN):

Input:
[ID: 1] Giá thép HRC tại Trung Quốc phục hồi mạnh, Hòa Phát đặt kế hoạch lãi 10.000 tỷ.
[ID: 2] Ngân hàng Nhà nước hút ròng tín phiếu, tỷ giá hạ nhiệt.

Output:
[[ARTICLE_ID: 1]]
[[POSITIVE]]
[HPG]: Kế hoạch lợi nhuận khả quan và hưởng lợi từ xu hướng giá thép thế giới phục hồi.
[Ngành thép]: Giá bán đầu ra tăng giúp cải thiện biên lợi nhuận gộp.
[[NEGATIVE]]
[Ngành xây dựng]: Áp lực chi phí nguyên vật liệu đầu vào tăng cao.

[[ARTICLE_ID: 2]]
[[POSITIVE]]
[Tỷ giá USD/VND]: Giảm áp lực tăng giá nhờ động thái hút tiền của NHNN.
[[NEGATIVE]]
[Thị trường chứng khoán]: Tâm lý thận trọng do lo ngại thanh khoản hệ thống bị thu hẹp.

-----------------------------------------
BẮT ĐẦU XỬ LÝ DANH SÁCH DƯỚI ĐÂY:
{batch_content}

KẾT QUẢ TRÍCH XUẤT:
""")