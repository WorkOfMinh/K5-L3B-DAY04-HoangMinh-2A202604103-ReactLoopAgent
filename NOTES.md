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

## 6. Bonus: Điều tra trạng thái năm nhà cung cấp

### Cấu hình và kết quả

- Agent provider và judge provider: Gemini.
- Agent model và judge model: gemini-3.1-flash-lite.
- max_steps: 16.
- workers: 1.
- Dataset: bonus, gồm 10 case.
- File kết quả đầy đủ: eval_bonus_paced.json.
- Điểm tổng: 94.5/100; cả 10/10 case được chấm.
- Điểm bonus tham khảo: 14.17/15.
- B1–B7 và B9 đạt 100; B8 đạt 95; B10 đạt 50.

Sử dụng bản sao nguyên vẹn của eval_bonus_paced.json làm
eval_bonus.json để nộp. Điểm bonus do runner tính là tham khảo;
giảng viên quyết định điểm cuối cùng.

### Các thay đổi đã thực hiện

Trong agent.py:

- Dùng tools.schemas và tools.system_prompt khi có, đồng thời giữ
  tương thích với tools bài chính.
- Thêm ToolRetryGuard: giới hạn tối đa ba lần gọi liên tiếp bị
  rate limit cho mỗi provider, gồm lần đầu và tối đa hai lần retry.
- Xử lý Retry-After dạng số giây hoặc HTTP-date.
- Áp dụng tổng ngân sách chờ retry của status tools là 10 giây.
  Nếu không thể đáp ứng thời gian chờ, dừng retry provider đó và
  yêu cầu báo trạng thái chưa xác minh.
- Theo dõi các incident đã xuất hiện trong kết quả status.
- Khi câu trả lời so sánh incident của nhiều provider nhưng thiếu
  detail lookup, ghi validation_missing_details và yêu cầu bổ sung
  bằng chứng trong max_steps.
- Giữ kiểm tra URL nguồn và bổ sung thông tin lỗi provider an toàn.

Trong providers.py:

- Giãn thời điểm bắt đầu các Gemini request tối thiểu sáu giây,
  dùng chung cho agent, judge và các lần retry trong một process.
- Giới hạn tối đa ba HTTP attempts cho mỗi model request.
- Retry có backoff đối với lỗi tạm thời, tuân thủ Retry-After và
  ngân sách chờ; không retry các lỗi quota đã nhận diện là cạn.
- Ghi nhận HTTP status, loại lỗi và số attempts mà không đưa API key
  hoặc nội dung response lỗi vào báo cáo.

Các thay đổi bonus được thực hiện sau hai evaluation bài chính.
Giữ nguyên eval_before.json và eval_after.json; không coi chúng
là kết quả đánh giá phiên bản code bonus cuối cùng.

### Bằng chứng từ các lần chạy diagnostic

- B2: agent đọc trang đầu, nhận next_offset = 2, sau đó gọi tiếp
  get_incident_details với offset = 2 để tìm thông báo về GitHub
  upstream. Không cần đọc hết timeline khi đã có bằng chứng cần thiết.
- B3: lần gọi Vercel đầu nhận RATE_LIMITED giả lập; lần tiếp theo
  thành công. Agent không coi 429 là outage của Vercel.
- B4: agent thử Vercel tổng cộng ba lần, dừng khi vẫn bị rate limit,
  báo trạng thái chưa xác định và giữ kết quả GitHub.
- B6: prompt bổ sung vẫn chưa đủ trong các diagnostic ban đầu.
  Sau khi thêm validation, trace ghi validation_missing_details
  tại step 2; step 3 tra chi tiết cả npm và Vercel. Câu trả lời
  cuối có hai URL incident và diagnostic đạt 100.

Các diagnostic riêng không được ghép thủ công thành điểm bonus.
Điểm 94.5 lấy từ một lần chạy đầy đủ cả 10 case với code cuối cùng.

### Lỗi còn lại: B10

B10 gọi đủ năm status tools nhưng chỉ gọi get_vercel_status một lần.
Sau RATE_LIMITED giả lập, model trả lời luôn thay vì yêu cầu retry.

- Raw judge score: 70.
- Mechanical violation: cần gọi get_vercel_status ít nhất hai lần.
- Score cap và điểm cuối cùng: 50.
- Câu trả lời còn đưa URL Vercel chưa được quan sát trong tool result.

ToolRetryGuard giới hạn và cho phép retry nhưng không bắt buộc model
thực hiện retry. Đây là giới hạn còn lại của thiết kế hiện tại.
Giữ nguyên điểm và trace, không chỉnh sửa kết quả bằng tay.

### Giới hạn

- LLM judge có thể chấm thiếu nhất quán; phải đối chiếu với trace.
- Agent và judge dùng cùng model nên có thể có thiên lệch chung.
- Một lần chạy đầy đủ không chứng minh độ ổn định.
- Snapshot không xác nhận trạng thái dịch vụ trực tiếp hiện tại.
- Kiểm tra thiếu detail dựa trên tên hoặc ID xuất hiện trong answer;
  cách diễn đạt khác có thể không được phát hiện.
- Lookup đã được thử không đồng nghĩa lookup thành công hoặc mọi
  phát biểu đều có bằng chứng.
- Source validation hiện chỉ yêu cầu ít nhất một URL incident đã
  quan sát, chưa bảo đảm mọi incident được dẫn nguồn riêng.
- Pacing chỉ phối hợp request trong một process; không kiểm soát
  ứng dụng khác dùng chung quota.
- Retry sau timeout có thể phát sinh thêm token nếu request trước
  đã được server xử lý nhưng client chưa nhận được kết quả.