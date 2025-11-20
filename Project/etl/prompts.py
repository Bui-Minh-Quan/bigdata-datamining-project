from langchain_core.prompts import PromptTemplate


ENTITY_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn được cho một hoặc nhiều bài báo, bao gồm tựa đề và mô tả ngắn gọn về bài báo đó, ngoài ra bạn có
thông tin về ngày xuất bản của bài báo, và loại chủ đề mà bài báo đang đề cập tới.

Lưu ý [QUAN TRỌNG, không được bỏ qua]: 
   - Hạn chế tạo mới một thực thể, chỉ tạo liên kết tới 5 thực thể. 
   - Luôn ưu tiên liên kết với các thực thể đã có: {existing_entities}

Bạn cần phân tích bài báo, đưa ra tên của những thực thể (ví dụ như cổ phiếu, ngành nghề, công ty, quốc gia, tỉnh thành...)
sẽ bị ảnh hưởng trực tiếp bởi thông tin của bài báo, theo hướng tích cực hoặc tiêu cực.

Với mỗi thực thể, ở phần Tên thực thể, hạn chế dùng dấu chấm, gạch ngang, dấu và &, dấu chấm phẩy ;. Và cần ghi thêm quốc gia, địa phương cụ thể và ngành nghề của nó (nếu có).
Tên chỉ nói tới một thực thể duy nhất. Phần Tên không được quá phức tạp, đơn giản nhất có thể.
Nếu thực thể nào thuộc danh mục cổ phiếu sau: {portfolio}, hãy ghi rõ tên cổ phiếu.
Ví dụ: SSI Chứng khoán; Ngành công nghiệp Việt Nam; Người dùng Mỹ; Ngành thép Châu Á; Ngành du lịch Hạ Long, ...

Ghi nhớ, Hạn chế tạo mới một thực thể, chỉ tạo liên kết tới 5 thực thể. Luôn cố liên kết với các thực thể đã có.

Phần giải thích mỗi thực thể, bắt buộc đánh giá số liệu được ghi, nhiều hoặc ít, tăng hoặc giảm, gấp bao nhiêu lần, ...
Cần cố gắng liên kết với nhiều thực thể khác. Tuy nhiên không suy ngoài phạm vi bài báo. Không tự chèn số liệu ngoài bài báo.
Không dùng dấu hai chấm trong phần giải thích, chỉ dùng hai chấm : để tách giữa Tên thực thể và phần giải thích.
                                                          
Đưa ra theo định dạng sau:
[[POSITIVE]]
[Entity 1]: [Explanation]
...
[Entity N]: [Explanation]

[[NEGATIVE]]
[Entity A]: [Explanation]
..
[Entity Z]: [Explanation]
                                                          
Một ví dụ cho bài báo:

(BẮT ĐẦU VÍ DỤ)

Ngày đăng: 2025-01-01T00:00:00+07:00
Mã cổ phiếu liên quan: (không có)
Tựa đề: Số lượng hóa đơn khởi tạo từ máy tính tiền tăng gấp 13 lần năm 2023

Mô tả: Tỷ lệ cơ sở kinh doanh sử dụng hóa đơn điện tử tăng mạnh, với số lượng hóa đơn từ máy tính tiền tăng gấp 13 lần so với năm trước. Ngành bán lẻ và dịch vụ hưởng lợi lớn từ chuyển đổi số này.

Danh sách thực thể sẽ bị ảnh hưởng:

[[POSITIVE]]
Ngành bán lẻ Việt Nam: Số lượng hóa đơn điện tử từ máy tính tiền tăng gấp 13 lần trong năm 2023, giúp tăng hiệu quả quản lý và giảm chi phí vận hành
MWG Bán lẻ: Là chuỗi bán lẻ lớn, hưởng lợi trực tiếp từ việc số hóa hóa đơn tăng 13 lần, cải thiện khả năng quản lý tồn kho và dòng tiền
Ngành công nghệ Việt Nam: Cung cấp giải pháp hóa đơn điện tử và máy tính tiền cho hàng nghìn cơ sở kinh doanh, doanh thu dự kiến tăng mạnh
FPT Công nghệ: Là nhà cung cấp giải pháp chuyển đổi số hàng đầu, hưởng lợi từ nhu cầu triển khai hóa đơn điện tử tăng đột biến

[[NEGATIVE]]
(Không có thực thể bị ảnh hưởng tiêu cực rõ ràng từ bài báo này)

(KẾT THÚC VÍ DỤ)

Ngày đăng: {date}
Mã cổ phiếu liên quan: {stockCodes}
Tựa đề: {title}

Mô tả: {description}

Danh sách thực thể sẽ bị ảnh hưởng:
""")

RELATION_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn đang làm việc dưới bối cảnh phân tích kinh tế.                                                            
Hạn chế tạo mới một thực thể, chỉ được tạo mới tối đa 2 thực thể mới. Chỉ được liên kết tới 4 thực thể khác. Luôn ưu tiên liên kết với các thực thể đã có: {existing_entities}

Dựa trên tác động đến một thực thể, hãy liệt kê các thực thể sẽ bị ảnh hưởng tiêu cực và ảnh hưởng tích cực do hiệu ứng dây chuyền.
Hãy suy luận xem thực thể hiện tại này có thể ảnh hưởng tiếp đến những thực thể khác nào, theo hướng tích cực hoặc tiêu cực.
                                                            
Với mỗi thực thể, ở phần Tên thực thể, hạn chế dùng dấu chấm, gạch ngang, dấu và &, dấu chấm phẩy ;. Cần ghi thêm quốc gia, địa phương cụ thể và ngành nghề của nó (nếu có). 
Tên chỉ nói tới một thực thể duy nhất. Phần Tên không được quá phức tạp, đơn giản nhất có thể.
Nếu thực thể nào thuộc danh mục cổ phiếu sau: {portfolio}, hãy ghi rõ tên cổ phiếu.
Ví dụ: SSI Chứng khoán; Ngành công nghiệp Việt Nam; Người dùng Mỹ; Ngành thép Châu Á; Ngành du lịch Hạ Long, ...

Ghi nhớ, Hạn chế tạo mới thực thể, chỉ được tạo mới tối đa 2 thực thể mới. Chỉ được liên kết tới 4 thực thể khác. Luôn cố liên kết với các thực thể đã có.

Phần giải thích mỗi thực thể, bắt buộc đánh giá số liệu được ghi, nhiều hoặc ít, tăng hoặc giảm, gấp bao nhiêu lần, ...
Cần cố gắng liên kết với nhiều thực thể khác. Tuy nhiên không suy ngoài phạm vi bài báo. Không tự chèn số liệu ngoài bài báo.
Không dùng dấu hai chấm trong phần giải thích, chỉ dùng hai chấm : để tách giữa Tên thực thể và phần giải thích.

Đưa ra theo định dạng sau:
[[POSITIVE]]
[Entity 1]: [Explanation]
...
[Entity N]: [Explanation]

[[NEGATIVE]]
[Entity A]: [Explanation]
..
[Entity Z]: [Explanation]

(BẮT ĐẦU VÍ DỤ)

Thực thể gốc: Bộ Xây dựng Việt Nam

Ảnh hưởng: Áp lực quản lý 28 dự án với tổng chiều dài 1188 km, nhằm hiện thực hóa mục tiêu đạt 3000 km cao tốc vào năm 2025. Số lượng dự án tăng gấp nhiều lần so với giai đoạn trước, đòi hỏi điều phối nguồn lực và kiểm soát tiến độ chặt chẽ hơn.

Danh sách thực thể sẽ bị ảnh hưởng bởi hiệu ứng dây chuyền:

[[POSITIVE]]
Doanh nghiệp xây dựng Việt Nam: Có cơ hội mở rộng hợp đồng thi công, tăng doanh thu nhờ số lượng dự án cao tốc lớn đang triển khai đồng loạt.
Người lao động Việt Nam: Có thêm nhiều cơ hội việc làm từ các dự án thi công trải dài khắp cả nước.

[[NEGATIVE]]
Bộ Giao thông Vận tải Việt Nam: Chịu áp lực phối hợp và giám sát hiệu quả giữa các bên liên quan, có nguy cơ bị chỉ trích nếu dự án chậm tiến độ.
Doanh nghiệp xây dựng Việt Nam: Có thể chịu áp lực tăng giá nguyên vật liệu và thiếu hụt nguồn cung do nhu cầu tăng đột biến.

(KẾT THÚC VÍ DỤ)

Thực thể gốc: {entities}

Ảnh hưởng: {description}

Danh sách thực thể sẽ bị ảnh hưởng bởi hiệu ứng dây chuyền:
""")

# Template batch relation extraction (xử lý nhiều thực thể cùng lúc)
BATCH_RELATION_EXTRACTION_PROMPT = PromptTemplate.from_template("""Bạn đang làm việc dưới bối cảnh phân tích kinh tế.
Hạn chế tạo mới thực thể, chỉ được tạo mới tối đa 2 thực thể mới cho mỗi thực thể gốc. Chỉ được liên kết tối đa 3 thực thể khác cho mỗi thực thể gốc. Luôn ưu tiên liên kết với các thực thể đã có: {existing_entities}

Dựa trên tác động đến các thực thể đầu vào, hãy phân tích hiệu ứng dây chuyền. 
Hãy suy luận xem mỗi thực thể hiện tại có thể ảnh hưởng tiếp đến những thực thể khác nào, theo hướng tích cực hoặc tiêu cực.

Với mỗi thực thể, ở phần Tên thực thể, hạn chế dùng dấu chấm, gạch ngang, dấu và &, dấu chấm phẩy ;. Cần ghi thêm quốc gia, địa phương cụ thể và ngành nghề của nó (nếu có).
Tên chỉ nói tới một thực thể duy nhất. Phần Tên không được quá phức tạp, đơn giản nhất có thể.
Nếu thực thể nào thuộc danh mục cổ phiếu sau: {portfolio}, hãy ghi rõ tên cổ phiếu.
Ví dụ: SSI Chứng khoán; Ngành công nghiệp Việt Nam; Người dùng Mỹ; Ngành thép Châu Á; Ngành du lịch Hạ Long, ...

Phần giải thích mỗi thực thể, bắt buộc đánh giá số liệu được ghi, nhiều hoặc ít, tăng hoặc giảm, gấp bao nhiêu lần...
Cần cố gắng liên kết với nhiều thực thể khác. Tuy nhiên không suy ngoài phạm vi bài báo. Không tự chèn số liệu ngoài bài báo.
Không dùng dấu hai chấm trong phần giải thích, chỉ dùng hai chấm : để tách giữa Tên thực thể và phần giải thích.

Đưa ra theo định dạng sau cho mỗi thực thể nguồn:

[[SOURCE: Tên thực thể nguồn]]
[[IMPACT: POSITIVE/NEGATIVE]]

[[POSITIVE]]
[Thực thể ảnh hưởng 1]: [Giải thích]
[Thực thể ảnh hưởng 2]: [Giải thích]
[Thực thể ảnh hưởng 3]: [Giải thích]

[[NEGATIVE]]
[Thực thể ảnh hưởng A]: [Giải thích]
[Thực thể ảnh hưởng B]: [Giải thích]
[Thực thể ảnh hưởng C]: [Giải thích]


LƯU Ý [RẤT QUAN TRỌNG]:
   - Có thể có RẤT NHIỀU thực thể đầu vào, hãy phân tích CẨN THẬN từng thực thể để không bỏ sót. Không được tạo thêm thực thể gốc. 
   - Bạn sẽ phân tích nhiều thực thể gốc một lúc. Với TỪNG thực thể, chỉ chọn CHÍNH XÁC 2-3 thực thể ảnh hưởng tích cực nhất và 2-3 thực thể ảnh hưởng tiêu cực quan trọng nhất.
   - Thực thể nguồn trong [[SOURCE: ...]] CHỈ chứa TÊN THỰC THỂ GỐC từ danh sách đầu vào, KHÔNG được thêm bất kỳ thông tin nào khác từ phần "Ảnh hưởng" hoặc giải thích.
                                                                  
(BẮT ĐẦU VÍ DỤ)
Danh sách thực thể nguồn:

Thực thể gốc: Bộ Xây dựng Việt Nam

Ảnh hưởng: NEGATIVE, Áp lực quản lý 28 dự án với tổng chiều dài 1188 km, nhằm hiện thực hóa mục tiêu đạt 3000 km cao tốc vào năm 2025. Số lượng dự án tăng gấp nhiều lần so với giai đoạn trước, đòi hỏi điều phối nguồn lực và kiểm soát tiến độ chặt chẽ hơn.

---

Danh sách thực thể sẽ bị ảnh hưởng bởi hiệu ứng dây chuyền:

[[SOURCE: Bộ Xây dựng Việt Nam]]
[[IMPACT: NEGATIVE]]

[[POSITIVE]]
Doanh nghiệp xây dựng Việt Nam: Có cơ hội mở rộng hợp đồng thi công, tăng doanh thu nhờ số lượng dự án cao tốc lớn đang triển khai đồng loạt.
Người lao động Việt Nam: Có thêm nhiều cơ hội việc làm từ các dự án thi công trải dài khắp cả nước.

[[NEGATIVE]]
Bộ Giao thông Vận tải Việt Nam: Chịu áp lực phối hợp và giám sát hiệu quả giữa các bên liên quan, có nguy cơ bị chỉ trích nếu dự án chậm tiến độ.
Doanh nghiệp xây dựng Việt Nam: Có thể chịu áp lực tăng giá nguyên vật liệu và thiếu hụt nguồn cung do nhu cầu tăng đột biến.

(KẾT THÚC VÍ DỤ)

Danh sách thực thể nguồn:

{input_entities}

Danh sách thực thể sẽ bị ảnh hưởng bởi hiệu ứng dây chuyền:
""")


BATCH_ARTICLE_EXTRACTION_PROMPT = PromptTemplate.from_template("""
Bạn là chuyên gia phân tích kinh tế. Dưới đây là danh sách các tin tức vắn tắt.
Nhiệm vụ của bạn là trích xuất các thực thể (ví dụ như cổ phiếu, ngành nghề, công ty, quốc gia, tỉnh thành...) chịu ảnh hưởng từ TỪNG bài báo riêng biệt.


Lưu ý [QUAN TRỌNG]:
1. Xử lý từng bài báo một cách độc lập dựa trên ID.
2. Hạn chế tạo thực thể mới, ưu tiên dùng: {existing_entities}
3. Nếu thực thể thuộc danh mục {portfolio}, hãy ghi rõ mã tên cổ phiếu.
4. Hãy mô tả thực thể theo đúng phạm vi: 
   Ví dụ:
   - “SSI Chứng khoán”
   - “Ngành công nghiệp Việt Nam”
   - “Người tiêu dùng Mỹ”
   - “Ngành thép Châu Á”
   - “Du lịch Hạ Long”
5. Tránh bỏ sót bài báo nào.
6. Tên chỉ nói tới một thực thể duy nhất. Phần Tên không được quá phức tạp, đơn giản nhất có thể. 
Nếu một thực thể chỉ khác biệt nhỏ về từ ngữ nhưng cùng ý nghĩa, hãy gộp vào thực thể đã có trong {existing_entities}.
Ví dụ: "Ngành bán lẻ Việt Nam" và "Ngành bán lẻ" -> gộp thành "Ngành bán lẻ Việt Nam".
"Người giàu tại Việt Nam" và "Người giàu Việt Nam" -> gộp thành "Người giàu Việt Nam".
7. Với mỗi thực thể, ở phần Tên thực thể, hạn chế dùng dấu chấm, gạch ngang, dấu và &, dấu chấm phẩy ;. Và cần ghi thêm quốc gia, địa phương cụ thể và ngành nghề của nó (nếu có).
Tên chỉ nói tới một thực thể duy nhất. Phần Tên không được quá phức tạp, đơn giản nhất có thể.

Định dạng đầu vào và đầu ra phải tuân thủ nghiêm ngặt như sau:
----------------
📌 **Ví dụ minh họa chuẩn về ĐẦU VÀO:**
[ID: 1] Giá thép tăng mạnh tại Trung Quốc | Giá thép giao tháng 1 tăng 5% do nhu cầu phục hồi.
[ID: 2] FED giữ nguyên lãi suất | FED thông báo giữ nguyên lãi suất, kỳ vọng hạ nhiệt lạm phát.

📌 **Ví dụ minh họa chuẩn về ĐẦU RA:**
[[ARTICLE_ID: 1]]
[[POSITIVE]]
[Ngành thép Châu Á]: Giá thép tăng nhờ nhu cầu phục hồi tại Trung Quốc.
[[NEGATIVE]]
[Doanh nghiệp xây dựng Việt Nam]: Chi phí đầu vào tăng có thể ảnh hưởng biên lợi nhuận.

[[ARTICLE_ID: 2]]
[[POSITIVE]]
[Thị trường chứng khoán Mỹ]: Giữ nguyên lãi suất hỗ trợ tâm lý tích cực.
[[NEGATIVE]]
[Ngành ngân hàng Mỹ]: Biên lợi nhuận lãi vay không tăng do không nâng lãi suất.

----------------
DANH SÁCH TIN TỨC CẦN XỬ LÝ:
{batch_content}

BẮT ĐẦU TRÍCH XUẤT:
""")
