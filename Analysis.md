# Phân tích kết quả Memory Systems for AI Agent

Bài đo cho thấy persistent profile cải thiện recall xuyên phiên, còn compact
giảm tải prompt khi lịch sử đủ dài. Hai lợi ích có chi phí khác nhau:
Advanced nhớ đúng hơn nhưng tốn thêm prompt ở hội thoại ngắn; xử lý
correction giữ recall đúng nhưng không làm token tự động giảm.

Báo cáo bài nộp dùng tên **Analysis.md**. Repo không quy định tên khác nên
chọn tên này; nếu giảng viên có quy ước riêng, đổi tên khi nộp. Output CLI
nguyên bản nằm ở [BenchmarkOutput.md](BenchmarkOutput.md); phép đo bonus
nằm ở [BonusOutput.md](BonusOutput.md).

## Cách đo và khả năng chạy lại

Python >= 3.11. Từ root:

```powershell
python -m pip install -r requirements.txt
python src/benchmark.py
pytest src/test_agents.py -v
python src/bonus_benchmark.py
```

CLI benchmark ép cả hai agent offline, không cần API key. Mỗi conversation
chạy cùng thứ tự lượt cho hai agent, rồi hỏi recall ngay ở một thread mới
dùng chung cho các câu recall của conversation đó. Hỏi ngay sau conversation
tránh dùng correction trong tương lai để chấm đáp án của phiên trước.
Dữ liệu trong data/ giữ nguyên, không lọc lượt hoặc sửa expected_contains.

Cấu hình đã đo: ngưỡng compact **2000**, giữ **4 message**; estimator
`ceil(len(text.strip()) / 4)`, rỗng trả 0. Các token là heuristic cùng
công thức cho hai agent, không phải token thực hoặc hóa đơn API.

Mỗi run dùng vùng profile mới trong state/benchmark-runs/run-*/ và tách
Standard/Stress. Hai lần chạy sau khi xóa state trước mỗi lần cho bảng
giống hệt nhau; SHA256 của cả hai dataset trước/sau đo không đổi.
Các run được giữ trên đĩa để xem profile; tổng dung lượng thư mục run
qua nhiều lần chạy không phải cột Memory growth của một run.

## Output benchmark

### Standard Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 1551 | 14595 | 0% | 0% | 0 | 0 |
| Advanced | 1350 | 19842 | 100% | 100% | 275 | 0 |

### Long-Context Stress Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 330 | 22944 | 0% | 0% | 0 | 0 |
| Advanced | 742 | 16664 | 100% | 100% | 205 | 1 |

Token cộng cả lượt học và recall qua tất cả thread. Memory growth là tổng
kích thước profile cuối trừ đầu theo user duy nhất, không cộng lặp profile
dungct qua 10 phiên. Compactions cộng số lần nén trong các thread của run.

Recall chấm 0 nếu không khớp fact, 0,5 nếu khớp một phần và 1 nếu khớp hết,
rồi lấy trung bình theo câu hỏi. So chuỗi dùng NFC và casefold, giữ dấu.
Quality là tỷ lệ fact khớp nhân hệ số ngắn gọn
`min(1, 120 / max(1, số từ))`, cùng công thức cho cả hai agent.
Quality 100% chỉ là đạt heuristic trên câu recall; không chấm suy luận,
độ tự nhiên hoặc fact sai ngoài expected. Format 3 bullet được kiểm tra
riêng bằng test, không nằm trong công thức quality.

## Bốn câu hỏi của Guide, gắn với số đo

### 1. Vì sao Advanced có recall tốt hơn?

Cả hai bảng: Baseline recall **0%**, memory growth **0 byte**; Advanced
recall **100%**, memory growth **275/205 byte**. Baseline giữ
[SessionState theo thread_id](src/agent_baseline.py), nên thread recall mới
không có fact từ thread học; Advanced đi qua
[extract_profile_updates và upsert_fact](src/memory_store.py), ghi User.md
rồi [đọc facts từ profile khi trả lời](src/agent_advanced.py).
Giới hạn: điểm số trên dữ liệu cố định chứng minh cơ chế nhớ đã chạy, không
chứng minh regex hiểu mọi câu tiếng Việt; câu hỏi mới có thể nằm ngoài
các field mà formatter nhận diện.

### 2. Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?

Standard: output Advanced **1350**, thấp hơn Baseline **1551**; nhưng prompt
Advanced **19842**, cao hơn **14595** khoảng **36,0%**, và cả hai compact **0**.
`_estimate_prompt_context_tokens()` cộng profile + summary + recent ở mỗi
lượt; profile là ngữ cảnh thêm mà hội thoại ngắn chưa đủ dài để compact bù
lại, trong khi output phụ thuộc nội dung response tất định.
Giới hạn: không được nói mọi loại token đều tăng; ghi User.md là I/O cục bộ,
không tự sinh token LLM, và benchmark chưa đo latency hay chi phí ghi đĩa.

### 3. Vì sao compact có lợi thế ở hội thoại dài?

Stress: prompt Advanced **16664**, thấp hơn Baseline **22944** khoảng
**27,4%**, với **1 compaction**; output lại tăng từ **330** lên **742**.
[CompactMemoryManager.append](src/memory_store.py) thay phần lịch sử cũ bằng
summary có giới hạn và giữ 4 message gần nhất, nên ngữ cảnh phải xử lý giảm;
response Advanced dài hơn vì nhớ đủ fact và tuân thủ 3 bullet.
Giới hạn: compact tối ưu prompt, không bảo đảm giảm output; một message
gần nhất rất dài vẫn có thể làm context vượt ngưỡng, và summary có thể mất
chi tiết. Stress hiện tại kích hoạt 1 lần; test riêng đã xác nhận nhiều lần nén.

Đo riêng Baseline qua 16 lượt học: prompt lượt đầu **187**, lượt cuối
**2580**, tổng **22752**; cộng recall thành **22944**. Điều này chứng minh
chi phí mỗi lượt tăng khi lịch sử dài ra. Tổng token cộng dồn có thể tăng
gần bậc hai với các lượt dài tương đương, không chỉ tuyến tính.

### 4. File memory tăng trưởng ra sao và rủi ro gì?

Profile Standard tăng **275 byte**, Stress **205 byte**, nhưng compaction
tương ứng **0/1**: hai số đo thuộc hai cơ chế độc lập. Upsert theo khóa thay
fact cũ thay vì nối correction mới; tin tức dài chỉ nằm trong thread/summary,
nên profile Stress không lớn hơn chỉ vì conversation dài hơn.
Giới hạn: đây là chênh lệch đầu-cuối, chưa phải đường cong tăng trưởng dài
hạn; field mới vẫn làm file tăng, và không có memory decay để bỏ preference
cũ. Artifacts của nhiều run cũng chiếm đĩa dù từng profile nhỏ.

Hai lỗi thực sự phát hiện khi chạy test toàn dataset là mất AI trong danh
sách “Python, AI” do tách dấu phẩy, và preference “ví dụ thực chiến” ghi đè
“ngắn gọn”. Đã sửa extraction danh sách và cập nhật style từng thành phần.
Đó là bằng chứng rủi ro lưu thiếu/mất fact; bảng hiện tại không chứng minh
file đang phình mất kiểm soát hay còn chứa fact nhiễu sai.

## Đối chứng: tắt compact

Override ngưỡng lên 1000000 trong tiến trình thử nghiệm, giữ nguyên input:

| Stress | Output tokens | Prompt tokens | Recall | Memory growth (bytes) | Compactions |
|---|---:|---:|---:|---:|---:|
| Baseline | 330 | 22944 | 0% | 0 | 0 |
| Advanced compact bật | 742 | 16664 | 100% | 205 | 1 |
| Advanced compact tắt | 742 | 26402 | 100% | 205 | 0 |

Compact giảm **9738 prompt token**, khoảng **36,9%** so với chính Advanced
không compact; recall/profile không đổi. Không compact, Advanced tốn hơn
Baseline do profile và output dài hơn đi theo lịch sử. Bảng Standard không
đổi vì mặc định cũng không nén ở bộ ngắn. Đã khôi phục ngưỡng về **2000**;
không sửa .env hay dữ liệu trong phép thử.

## Bonus đã chọn: Conflict handling

**Vấn đề:** correction trong dataset đổi nghề backend sang MLOps và nơi ở
Huế sang Đà Nẵng ở Stress; cập nhật preference từng phần cũng không được
xóa yêu cầu còn hiệu lực. Lỗi ghi đè brevity đã được phát hiện thực tế.
Chọn xử lý xung đột, không chọn decay vì chưa có số đo cho thấy profile
phình nhanh cần cơ chế quên theo thời gian.

**Cơ chế đã triển khai:** `upsert_fact()` giữ một dòng mỗi khóa và thay giá
trị mới; `_prepare_turn()` hợp nhất style theo thành phần, thay số bullet/
loại ví dụ cùng loại; `_offline_response()` ưu tiên profile mới hơn summary
cũ. Extractor bỏ câu hỏi, câu đùa, ví dụ cũ và nơi đi họp trong các case đã
test. Đây là heuristic lựa chọn fact, chưa phải confidence threshold có
điểm tin cậy được hiệu chuẩn.

**Bằng chứng định lượng:** [bonus_benchmark.py](src/bonus_benchmark.py) chạy
hai Advanced trên cùng dataset, cùng compaction và cùng câu hỏi. Đối chứng
FirstFactWinsStore giữ giá trị đầu tiên của từng field và bỏ mọi correction;
bản bật dùng store thật. Chỉ thay chính sách ghi profile, không sửa agent
chính hay dữ liệu để tạo kết quả.

| Bộ | Conflict handling | Prompt tokens | Recall | Quality | Memory growth (bytes) | Compactions |
|---|---|---:|---:|---:|---:|---:|
| Standard | Tắt, giữ fact đầu | 19454 | 64,3% | 66,8% | 261 | 0 |
| Standard | Bật | 19842 | 100% | 100% | 275 | 0 |
| Stress | Tắt, giữ fact đầu | 16441 | 66,7% | 75% | 174 | 1 |
| Stress | Bật | 16664 | 100% | 100% | 205 | 1 |

Bật correction tăng recall **35,7 điểm phần trăm** ở Standard và **33,3**
ở Stress. Bản tắt còn Huế trong profile Stress; bản bật giữ đúng Đà Nẵng.
Cả hai vẫn compact 1 lần nên chênh lệch recall không đến từ bật/tắt compact.
Prompt tăng **388/223 token**, profile tăng thêm **14/31 byte**; bonus này
ưu tiên đúng fact, không có bằng chứng nó tiết kiệm token ở phép đo hiện tại.

**Rủi ro và giới hạn:** “mới nhất thắng” có thể ghi đè fact đúng bằng một
khẳng định mới nhưng sai; không có timestamp/confidence/provenance để xác
minh correction. Hợp nhất style có thể giữ thành phần đã hết hiệu lực nếu
người dùng hủy bằng cách diễn đạt regex chưa hiểu. Summary cũ vẫn có thể
chứa nơi ở cũ; offline giải quyết bằng profile ưu tiên, còn nhánh live cơ
bản cần guardrail prompt rõ hơn khi gặp hai nguồn mâu thuẫn.
Giữ fact đầu chỉ là một đối chứng cụ thể; kết quả không đại diện cho mọi
chính sách xung đột khác. Test [test_bonus.py](src/test_bonus.py) xác nhận
recall Stress 2/3 khi tắt so với 1 khi bật và một dòng location trên đĩa.

## Hệ thống mạnh hơn và phức tạp hơn

Recall tăng 0% lên 100% nhưng Standard tốn thêm 5247 prompt token; Stress
tiết kiệm 6280 prompt token nhưng cần compaction và vẫn giữ profile 205 byte.
Để tạo các số này, Advanced thêm extractor, lưu đĩa, giải quyết correction,
cách ly user và summary có giới hạn. Đường dẫn user được chuẩn hóa và
resolve trong root; thread Advanced không dùng chung giữa hai user;
assistant không được trích thành fact; query không tự tạo hồ sơ rỗng.
Các guardrail đó đã có test, nhưng chưa có concurrent writes, memory decay
hay xác minh độ tin cậy của fact; benchmark chính vẫn đo offline.

## Đối chiếu Rubric và kiểm tra

| Mốc Rubric | Bằng chứng hiện có |
|---|---|
| 0–60 | Baseline nhớ theo thread; Advanced ghi profile thật; Stress compact 1; cấu trúc và dataset rõ |
| 60–75 | Cùng input/thread recall mới; 4 test test_agents.py pass; hai bảng đủ 6 cột |
| 75–90 | Standard/Stress; prompt từng lượt; đối chứng compact; phân tích riêng output/prompt và rủi ro memory |
| 90–100 | Conflict handling có code, test, đối chứng 64,3%/66,7% lên 100%, chi phí và rủi ro được nêu |

Bài có bằng chứng để reviewer xem xét dải **90–100**, không tự khẳng định
điểm 100; quyết định điểm thuộc giảng viên và chất lượng đánh giá thực tế.
LangGraph tools/InMemorySaver/middleware, judge live, memory decay và
confidence threshold chưa được triển khai; live hiện chỉ là chat model
factory với memory do code quản lý.

Tất cả test dùng offline/mock, không cần API key. Bốn test scaffold dùng
make_config(tmp_path) trực tiếp, đủ 7 trường, ngưỡng 300 và giữ 4 message;
không đọc .env hay ghi state thật. Trên sandbox Windows đã dùng cache làm
basetemp vì thư mục temp mặc định ngoài workspace không truy cập được:

```powershell
python -m pytest src -q --basetemp=.pytest_cache/full-suite-tmp
```

Kết quả cuối: **33 test pass**, gồm 4 test scaffold và test đối chứng bonus.

## Quy ước cấu hình

load_config đọc root/.env bằng python-dotenv; môi trường sẵn có ưu tiên.
Nếu không có .env, không import python-dotenv: benchmark offline chạy bằng
thư viện chuẩn khi bản sao chỉ có src/ và data/. Test cần pytest như công
cụ chạy test; không cần API key, SDK hay requirements.txt của repo.
base/data/state cùng một root; tạo state khi nạp config. SDK được import
khi dựng model live; force_offline bỏ qua factory.

| Biến | Giá trị mặc định / quy tắc |
|---|---|
| LLM_PROVIDER | openai; hỗ trợ custom, gemini, anthropic, ollama, openrouter; alias anthorpic được chuẩn hóa |
| LLM_MODEL | Theo provider: gpt-4o-mini, local-model, gemini-2.5-flash, claude-sonnet-4-5, llama3.2, openai/gpt-4o-mini |
| LLM_TEMPERATURE | 0; hữu hạn và không âm |
| LLM_API_KEY, LLM_BASE_URL | Override key/endpoint model chính |
| JUDGE_PROVIDER, JUDGE_MODEL, JUDGE_TEMPERATURE | Kế thừa model chính; đổi provider dùng model mặc định của provider mới |
| JUDGE_API_KEY, JUDGE_BASE_URL | Override judge; kế thừa key/endpoint chỉ khi cùng provider |
| COMPACT_THRESHOLD_TOKENS | 2000; số nguyên dương |
| COMPACT_KEEP_MESSAGES | 4; số nguyên dương |

Key theo provider: OPENAI_API_KEY, CUSTOM_API_KEY, GEMINI_API_KEY (fallback
GOOGLE_API_KEY), ANTHROPIC_API_KEY, OPENROUTER_API_KEY. Endpoint là
<PROVIDER>_BASE_URL; Ollama mặc định http://localhost:11434.
Override LLM/JUDGE ưu tiên hơn biến theo provider. Judge config được nạp
nhưng benchmark offline dùng heuristic, chưa gọi judge thật.

Live cần package tương ứng langchain-openai, langchain-google-genai,
langchain-anthropic, langchain-ollama, langchain-openrouter; chúng không
bắt buộc cho offline. Custom cần base URL, dùng key placeholder nếu
endpoint không xác thực. Constructor đã đối chiếu tài liệu
[LangChain](https://docs.langchain.com/oss/python/langchain/models);
unit test live dùng mock; phép kiểm tra API thật được ghi dưới đây.

## Kiểm tra live bằng Gemini API thật

Ngày 04/10/2026, đã kiểm tra nhánh live của cả hai agent, không cho fallback
offline và dùng profile riêng trong state/live-tests/. Gemini 3.8 Flash
trả được response nhưng nhiều lượt tiếp theo gặp 503 tải cao, kể cả retry;
Gemini 2.5 Flash trả 404 không còn khả dụng cho tài khoản này. Không thay
đổi model hoặc key trong .env của người dùng.

Sau khi đọc danh sách model từ API, thử cùng bộ kiểm tra với
gemini-flash-lite-latest: 10/10 check pass. Bao gồm model thật của hai
agent, Baseline nhớ trong thread và quên ở thread mới, Advanced ghi
profile thật và recall ở thread mới, correction Huế sang Đà Nẵng,
một dòng location trên đĩa, compact kích hoạt, token được ghi, và recall
qua một instance Advanced mới. Toàn bộ 33 test offline cũng pass.

Đây là smoke test hành vi bằng API thật trên một kịch bản ngắn, không phải
benchmark live toàn bộ hai dataset hoặc kiểm tra sáu provider. Bộ kiểm tra
đầy đủ với model 3.8 Flash vẫn chưa hoàn tất do 503 dịch vụ. Không dùng số
live này để thay các bảng token/quality offline ở trên; key không ghi log.
