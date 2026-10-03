# K4-DAY17-PhamAnhMinh-2A202603009

Bài làm cá nhân — Phạm Anh Minh, MSSV 2A202603009.
Day 17: Memory Systems for AI Agent.

So sánh Baseline chỉ nhớ trong thread với Advanced dùng persistent profile
User.md và compact lịch sử dài. Chạy offline tất định, không cần API key.

## Cấu trúc bài nộp

- src/: cấu hình, provider, memory, hai agent, benchmark và test đã triển khai.
- data/: hai bộ dữ liệu gốc, giữ nguyên.
- STEP8.md: trả lời bốn câu hỏi phân tích Bước 8.
- Analysis.md: phân tích chi tiết, phương pháp đo, bonus và giới hạn.
- BenchmarkOutput.md, BonusOutput.md: output đã đo.
- requirements.txt: dependency tối thiểu để chạy offline và test.

## Cài đặt và chạy

Python >= 3.11. Từ thư mục gốc repo:

```powershell
python -m pip install -r requirements.txt
python src/benchmark.py
pytest src/test_agents.py -v
```

Benchmark in Standard Benchmark và Long-Context Stress Benchmark, mỗi bảng
hai agent và sáu chỉ số. Bốn test hành vi memory phải pass. Để chạy tất cả
test hoặc phép đo bonus:

```powershell
python -m pytest src -q
python src/bonus_benchmark.py
```

Không dùng python -m src.benchmark vì src/ dùng import phẳng.
Có thể tạo virtualenv trước khi cài bằng python -m venv .venv.

## Trạng thái sạch

state/ tự sinh khi chạy; không nằm trong Git hay bài nộp. Benchmark tạo
vùng state mới cho mỗi run, nên không dùng profile còn sót từ lần trước.
Để xóa trạng thái trong PowerShell khi đang ở root repo:

```powershell
Remove-Item -LiteralPath ./state -Recurse -Force
```

Chỉ chạy lệnh xóa khi state đã tồn tại. .env, cache và virtualenv cũng
được ignore. Bản nộp không cần file nào từ các thư mục sinh ra khi chạy.

## Cấu hình và live

Mặc định compact 2000 token, giữ 4 message. Có thể override qua
COMPACT_THRESHOLD_TOKENS và COMPACT_KEEP_MESSAGES; quy ước đầy đủ ở
Analysis.md. Hai CLI benchmark luôn ép offline, kể cả có key trong môi trường.

Live cơ bản hỗ trợ openai, custom, gemini, anthropic, ollama, openrouter.
Cài SDK provider tương ứng nếu cần; chúng không bắt buộc cho bài chạy offline.
Chưa triển khai extension LangGraph tools/checkpointer/middleware.
Không đưa .env hoặc API key vào Git.

## Kết quả và bonus

Advanced recall 100% so với Baseline 0% trên hai dataset cố định. Standard:
prompt Advanced cao hơn khoảng 36%; Stress: thấp hơn khoảng 27,4%, với
1 compaction. Đây là token heuristic, quality là heuristic, không phải
token tính phí hoặc đánh giá chất lượng từ judge LLM.

Bonus Conflict handling: thay fact cũ theo field, giữ preference còn hiệu
lực và ưu tiên profile mới hơn summary cũ. Đối chứng giữ fact đầu cho recall
64,3%/66,7%; bật correction đạt 100%/100%. Chi phí và rủi ro ở Analysis.md.
