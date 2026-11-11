# Ghi chú phân tích · Day 04

Họ và tên: Hoàng Minh
MSSV: 2A202604103

## 1\. Case được chọn

* ID case: H3
* Câu trả lời của agent: xác minh một incident Cloudflare theo ID do người dùng cung cấp và yêu cầu link chính xác.
* Điểm ở lần chạy 1: 50/100.
* Câu trả lời của agent kết luận không tìm thấy incident và không có sự cố toàn cầu trong dữ liệu gần đây, nhưng chỉ gọi get\_status.
* Agent chưa tra cứu chính xác ID bằng get\_incident\_details.

## 2\. Bằng chứng trong trace



Trace trước cải tiến:



&#x20;   step 1:

&#x20;     get\_status({"provider": "cloudflare"})

&#x20;     matching\_incidents\_in\_last\_50: 50

&#x20;     incidents: chỉ trả về 5 bản tóm tắt



&#x20;   step 2:

&#x20;     finish: stop



Agent không gọi get\_incident\_details với ID người dùng cung cấp. Danh sách 5 bản tóm tắt không đủ để kết luận ID không nằm trong toàn bộ 50 incident mà tool có thể tra cứu.



Kiểm tra mechanical báo: "Chưa gọi tool cần thiết: get\_incident\_details".



Raw judge score là 80, nhưng mechanical score\_cap là 50, nên điểm cuối cùng của case là 50.



Nguyên nhân có thể xảy ra: system prompt chưa hướng dẫn rõ việc tra cứu trực tiếp khi câu hỏi chứa ID incident. Loop thực thi đúng tool model yêu cầu, nhưng model chọn tool chưa đủ để trả lời.



## 3\. Thay đổi đã thực hiện



Sửa trong agent.py:



1\. Bổ sung SYSTEM\_PROMPT:

&#x20;  - Khi người dùng cung cấp ID để xác minh, gọi get\_incident\_details.

&#x20;  - Không dùng danh sách tóm tắt để kết luận một ID không tồn tại.

&#x20;  - Khi nhận INCIDENT\_NOT\_FOUND, chỉ kết luận trong phạm vi dữ liệu mà tool có thể tra cứu.

&#x20;  - Không tự tạo URL incident.

&#x20;  - Phân biệt timestamp snapshot với trạng thái trực tiếp hiện tại.



2\. Thêm kiểm tra nguồn trong run\_agent:

&#x20;  - Lưu URL từ get\_incident\_details thành công.

&#x20;  - Khi final answer thiếu mọi URL incident đã quan sát, ghi event validation\_missing\_source và yêu cầu model sửa câu trả lời.

&#x20;  - Lượt sửa vẫn nằm trong max\_steps.

&#x20;  - Lookup thất bại không tạo yêu cầu bắt buộc dẫn URL incident.



Chọn thay đổi prompt để xử lý lỗi chọn tool trong H3.

Thêm source validation để đáp ứng contract kiểm tra nguồn.



Kiểm tra:

* Toàn bộ 37 unit tests pass sau cải tiến.
* Diagnostic H3 đạt 100.
* Trong diagnostic, agent gọi get\_incident\_details với đúng ID, nhận INCIDENT\_NOT\_FOUND, trả lời có giới hạn và không bịa link.



## 4\. So sánh hai lần chạy



Cấu hình hai lần giống nhau:

* Provider: openai.
* Agent model: gpt-4o.
* Judge model: gpt-4o.
* max\_steps: 8.
* Dataset: core.
* Mỗi lần có đủ 22/22 case được chấm.



|Chỉ số|`eval\_before.json`|`eval\_after.json`|
|-|-|-|
|Điểm tổng|91.95|88.82|
|Điểm case đã chọn (H3)|50|100|
|Số model calls|48|45|
|Agent tokens|33319 |35248 |
|Judge tokens|32491 |30672 |
|Tổng tokens agent và judge|65810 |65920|
|Chi phí tiền tệ|Không được báo cáo|Không được báo cáo|

* Lỗi đã giải quyết:

&#x20;  - H3 sử dụng đúng tool tra cứu ID và giới hạn kết luận phù hợp.

&#x20;  - Các tests source validation đã pass.

* Lỗi còn lại hoặc mới xuất hiện:

&#x20;  - Điểm tổng giảm 3.13 điểm dù H3 tăng 50 điểm.

&#x20;  - H1 và H6 vẫn ở mức 60.

&#x20;  - A6 giảm 97 → 80; H7 giảm 75 → 60. Chưa phân tích trace để xác định nguyên nhân.

&#x20;  - H4 giảm 100 → 30, nhưng có dấu hiệu judge chấm không nhất quán: expected cho phép trả lời ngoài phạm vi một cách lịch sự, và agent đã nêu phạm vi hỗ trợ, không gọi tool.

&#x20;  - Giữ nguyên điểm H4 trong file eval, không sửa kết quả bằng tay.

## 5\. Giới hạn



* Điểm LLM judge là ước lượng và có thể không nhất quán. H4 là ví dụ cần đối chiếu trực tiếp answer, expected và trace.
* Agent và judge đều dùng gpt-4o, có thể có thiên lệch chung.
* Snapshot chỉ phản ánh dữ liệu được lưu tại thời điểm captured\_at, không xác nhận trạng thái dịch vụ trực tiếp hiện tại.
* Tool giới hạn phạm vi tìm kiếm, số incident trả về và nội dung updates. Không tìm thấy không chứng minh incident chưa từng tồn tại.
* Source validation chỉ kiểm tra sự hiện diện của URL đã quan sát, không chứng minh mọi phát biểu đều được nguồn hỗ trợ.
* Chỉ chạy một lần cho mỗi phiên bản nên chưa chứng minh độ ổn định hoặc quan hệ nhân quả giữa thay đổi code và thay đổi điểm.
* Lần after có cả thay đổi prompt và source validation, nên chưa tách riêng được ảnh hưởng của từng thay đổi.

