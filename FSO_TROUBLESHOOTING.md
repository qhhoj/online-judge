# Hướng dẫn khắc phục và kiểm tra Final Submission Only Contest Format

## Các vấn đề đã fix

### 1. Nút Judge giờ luôn hiển thị
- Không cần chờ contest kết thúc
- Có thể dùng để rejudge bất cứ lúc nào
- Nếu contest chưa kết thúc, sẽ có warning nhưng vẫn cho phép judge

### 2. Task judge giờ dùng rejudge=True
- Bypass logic chặn pending trong judgeapi.py
- Đảm bảo submissions được judge thực sự

### 3. Thêm logging chi tiết
- Có thể theo dõi periodic task hoạt động
- Debug dễ dàng hơn

## Kiểm tra Celery Beat có chạy không

### Bước 1: Kiểm tra process Celery Beat
```bash
ps aux | grep celery
```

Phải thấy 2 process:
- `celery -A dmoj worker` (worker)
- `celery -A dmoj beat` (scheduler)

### Bước 2: Nếu chưa chạy, start Celery Beat
```bash
# Terminal 1: Start Celery Worker
celery -A dmoj worker -l info

# Terminal 2: Start Celery Beat
celery -A dmoj beat -l info
```

### Bước 3: Kiểm tra log
Trong log của Celery Beat, mỗi 5 phút phải thấy:
```
[INFO] Checking X final_submission contests that ended in last 10 minutes
[INFO] Contest abc: auto_judge=True
[INFO] Contest abc: Y pending submissions
[INFO] Triggering judge task for contest abc
```

## Test thủ công

### Test 1: Gọi periodic task trực tiếp
```python
python manage.py shell

from judge.tasks.contest import check_final_submission_contests
result = check_final_submission_contests()
print(f"Processed {result} contests")
```

### Test 2: Gọi judge task cho 1 contest cụ thể
```python
python manage.py shell

from judge.tasks.contest import judge_final_submissions
from judge.models import Contest

contest = Contest.objects.get(key='your-contest-key')
task = judge_final_submissions.delay(contest.key)
print(f"Task ID: {task.id}")
```

### Test 3: Kiểm tra pending submissions
```python
python manage.py shell

from judge.models import Contest, Submission

contest = Contest.objects.get(key='your-contest-key')
pending = Submission.objects.filter(
    contest__participation__contest=contest,
    status='PD'
)
print(f"Pending submissions: {pending.count()}")
for sub in pending[:5]:
    print(f"  - Submission {sub.id}: {sub.user.user.username} - {sub.problem.code}")
```

## Các trường hợp cần kiểm tra

### Trường hợp 1: Contest vừa kết thúc
1. Đợi tối đa 5 phút (chu kỳ của Celery Beat)
2. Kiểm tra log Celery Beat
3. Nếu không tự động judge, chạy test thủ công ở trên

### Trường hợp 2: Contest đã kết thúc lâu (>10 phút)
- Periodic task chỉ check contests kết thúc trong 10 phút gần nhất
- Phải dùng nút "Judge Final Submissions" trong admin

### Trường hợp 3: auto_judge = false
- Periodic task sẽ skip contest này
- Phải dùng nút "Judge Final Submissions" trong admin

## Cấu hình Production

### Supervisor config cho Celery (khuyến nghị)
Tạo file `/etc/supervisor/conf.d/dmoj-celery.conf`:

```ini
[program:dmoj-celery-worker]
command=/path/to/venv/bin/celery -A dmoj worker -l info
directory=/path/to/site
user=dmoj
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/dmoj/celery-worker.log

[program:dmoj-celery-beat]
command=/path/to/venv/bin/celery -A dmoj beat -l info
directory=/path/to/site
user=dmoj
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/dmoj/celery-beat.log
```

Sau đó:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start dmoj-celery-worker
sudo supervisorctl start dmoj-celery-beat
```

### Systemd service (thay thế)
Tạo file `/etc/systemd/system/dmoj-celery-worker.service`:

```ini
[Unit]
Description=DMOJ Celery Worker
After=network.target

[Service]
Type=simple
User=dmoj
WorkingDirectory=/path/to/site
ExecStart=/path/to/venv/bin/celery -A dmoj worker -l info
Restart=always

[Install]
WantedBy=multi-user.target
```

Tạo file `/etc/systemd/system/dmoj-celery-beat.service`:

```ini
[Unit]
Description=DMOJ Celery Beat
After=network.target

[Service]
Type=simple
User=dmoj
WorkingDirectory=/path/to/site
ExecStart=/path/to/venv/bin/celery -A dmoj beat -l info
Restart=always

[Install]
WantedBy=multi-user.target
```

Sau đó:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dmoj-celery-worker
sudo systemctl enable dmoj-celery-beat
sudo systemctl start dmoj-celery-worker
sudo systemctl start dmoj-celery-beat
```

## Kiểm tra hoạt động

### Xem log realtime
```bash
# Celery Worker
tail -f /var/log/dmoj/celery-worker.log

# Celery Beat
tail -f /var/log/dmoj/celery-beat.log
```

### Kiểm tra task đã chạy
```python
python manage.py shell

from celery.result import AsyncResult

# Thay YOUR_TASK_ID bằng task ID thực tế
task = AsyncResult('YOUR_TASK_ID')
print(f"State: {task.state}")
print(f"Result: {task.result}")
```

## Migration

Nếu chưa chạy migration:
```bash
python manage.py migrate
```

## Tóm tắt các thay đổi

1. **judge/tasks/contest.py**: 
   - Dùng `rejudge=True` khi judge pending submissions
   - Thêm logging chi tiết

2. **judge/admin/contest.py**:
   - Cho phép judge ngay cả khi contest chưa kết thúc (với warning)

3. **templates/admin/judge/contest/change_form.html**:
   - Nút Judge luôn hiển thị cho FSO contests
   - Không cần chờ contest kết thúc

4. **dmoj/celery.py**:
   - Đã có Celery Beat schedule chạy mỗi 5 phút

## Liên hệ nếu vẫn gặp vấn đề

Nếu sau khi làm theo hướng dẫn trên mà vẫn không hoạt động:
1. Gửi log của Celery Beat
2. Gửi kết quả của các test thủ công
3. Gửi thông tin contest (key, end_time, format_config)

