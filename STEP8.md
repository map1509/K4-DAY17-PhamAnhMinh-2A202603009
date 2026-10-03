# Bước 8 — Phân tích kết quả

Phạm Anh Minh — 2A202603009. Số liệu offline: compact 2000 token, giữ 4
message. Output đầy đủ: [BenchmarkOutput.md](BenchmarkOutput.md).
Phương pháp, bonus và giới hạn: [Analysis.md](Analysis.md).

## 1. Vì sao Advanced có recall tốt hơn Baseline?

Cả Standard và Stress: Advanced recall 100%, Baseline 0%; memory growth
Advanced là 275/205 byte, Baseline 0. Baseline giữ lịch sử theo thread_id
nên thread recall mới không có fact; Advanced trích fact, upsert User.md,
rồi đọc profile khi trả lời trong thread mới. Kết quả chứng minh recall
trên dataset này, không bảo đảm regex hiểu mọi cách diễn đạt mới.

## 2. Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?

Standard: prompt Advanced 19842 so với Baseline 14595, tăng khoảng 36%;
cả hai compaction 0. Mỗi lượt Advanced mang thêm profile mà hội thoại
chưa đủ dài để nén bù chi phí. Output lại thấp hơn: 1350 so với 1551,
nên không kết luận mọi loại token đều tăng; ghi file cục bộ không sinh
LLM token và benchmark không đo latency I/O.

## 3. Vì sao compact có lợi thế ở hội thoại dài?

Stress: prompt Advanced 16664 so với Baseline 22944, giảm 27,4%;
compaction 1. Khi tắt compact, prompt Advanced tăng lên 26402 mà recall
vẫn 100%, xác nhận compact giảm prompt trong khi profile giữ recall.
Output Advanced 742 lớn hơn Baseline 330: compact không bảo đảm giảm
output. Summary có giới hạn nên vẫn có rủi ro mất chi tiết.

## 4. Memory tăng trưởng thế nào và có rủi ro gì?

Profile tăng 275 byte ở Standard và 205 byte ở Stress; số compaction là
0/1 và không đo dung lượng profile. Upsert thay field cũ thay vì nối
correction, còn tin dài nằm trong thread/summary. Số cuối run chưa chứng
minh xu hướng dài hạn; field mới, preference cũ và extraction sai vẫn có
thể làm memory tăng hoặc recall sai. Test từng phát hiện mất AI trong
danh sách có dấu phẩy và mất preference ngắn gọn; cả hai đã được sửa.

## Bonus: Conflict handling

Đối chứng giữ fact đầu thay vì sửa theo correction cho recall Standard
64,3% và Stress 66,7%; bản bật đạt 100% ở cả hai, cùng dataset và cùng
compaction. Prompt tăng nhẹ 388/223 token, nên lợi ích là đúng fact.
Rủi ro là khẳng định mới nhưng sai có thể ghi đè fact đúng, và hợp nhất
style có thể giữ preference đã hết hiệu lực. Chưa có confidence/timestamp
để xác minh correction. Xem [BonusOutput.md](BonusOutput.md) và chạy lại
bằng python src/bonus_benchmark.py.

Hệ thống có recall tốt hơn nhưng thêm extractor, ghi file, conflict
handling và compact; cần kiểm chứng guardrail và dữ liệu mới. Đối chiếu
đầy đủ các mốc Rubric nằm trong Analysis.md.
