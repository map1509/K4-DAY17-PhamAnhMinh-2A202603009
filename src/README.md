# Source implementation

Các module dùng import phẳng; chạy lệnh từ root repo:

- python src/benchmark.py: hai bảng offline, không cần API key.
- pytest src/test_agents.py -v: bốn test tích hợp trên tmp_path.
- python -m pytest src -q: toàn bộ test.
- python src/bonus_benchmark.py: đối chứng Conflict handling.

Thứ tự phụ thuộc: model_provider/config -> memory_store -> agents -> benchmark.
Advanced tái sử dụng formatter recall của Baseline, nhưng lấy profile
bền vững và compact context. state/ tự sinh, không phải input bài nộp.
Phân tích và thiết lập môi trường ở README.md, STEP8.md và Analysis.md.
