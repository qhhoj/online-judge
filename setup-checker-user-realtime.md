# Hướng dẫn cài đặt User Activity Tracking System cho QHHOJ Online Judge

## Tổng quan
Hệ thống theo dõi hoạt động người dùng cho phép admin giám sát:
- Số lượng người dùng hiện tại đang truy cập
- Địa chỉ IP và thiết bị của người dùng
- Lịch sử truy cập chi tiết
- Theo dõi real-time cả người dùng đã đăng nhập và anonymous

## 1. Cài đặt Dependencies

### Thêm package vào requirements.txt
```bash
echo "user-agents==2.2.0" >> requirements.txt
```

### Cài đặt package
```bash
pip install user-agents==2.2.0
# hoặc nếu dùng pip3
pip3 install user-agents==2.2.0
```

## 2. Files cần tạo/thay đổi

### A. Models
**File: judge/models/user_activity.py** (Đã có)
- UserSession: Theo dõi session người dùng
- UserActivity: Ghi log hoạt động chi tiết

### B. Middleware  
**File: judge/middlewares/user_activity.py** (Đã có - lưu ý tránh conflict với middleware.py)
- UserActivityMiddleware: Tự động tracking mọi request

### C. Views
**File: judge/views/user_activity.py** (Đã có)
- active_users_view: Dashboard hiển thị user online
- user_activity_detail: Chi tiết hoạt động user
- all_logs_view: Xem tất cả logs với filter
- export_logs: Export CSV
- delete_user_logs: Xóa logs theo user
- delete_anonymous_logs: Xóa logs anonymous
- active_users_api: API real-time

### D. Admin Interface
**File: judge/admin/user_activity.py** (Đã có)
- UserSessionAdmin và UserActivityAdmin

### E. Templates
**Tạo thư mục: templates/admin/user_activity/**
- active_users.html: Dashboard chính
- user_detail.html: Chi tiết người dùng
- all_logs.html: Xem logs
- 404.html: Trang lỗi

### F. URLs
**Thêm vào dmoj/urls.py:**
```python
# Import
from judge.views.user_activity import (
    active_users_view, user_activity_detail, all_logs_view, 
    export_logs, delete_user_logs, delete_anonymous_logs, active_users_api
)

# Thêm vào urlpatterns
path('admin/user-activity/', include([
    path('active-users/', active_users_view, name='active_users'),
    path('user/<int:user_id>/', user_activity_detail, name='user_activity_detail'),
    path('all-logs/', all_logs_view, name='all_logs'),
    path('export-logs/', export_logs, name='export_logs'),
    path('delete-user-logs/<int:user_id>/', delete_user_logs, name='delete_user_logs'),
    path('delete-anonymous-logs/', delete_anonymous_logs, name='delete_anonymous_logs'),
    path('api/active-users/', active_users_api, name='active_users_api'),
])),
```

## 3. Cấu hình Django Settings

### A. Thêm Middleware vào dmoj/settings.py:
```python
MIDDLEWARE = (
    # ... existing middleware ...
    'judge.middlewares.user_activity.UserActivityMiddleware',  # Thêm dòng này
)
```

### B. Thêm permission vào Profile model:
**File: judge/models/profile.py**
```python
class Meta:
    permissions = (
        # ... existing permissions ...
        ('can_see_user_activity', 'Can see user activity'),  # Thêm dòng này
    )
```

### C. Import models trong judge/models/__init__.py:
```python
from judge.models.user_activity import UserActivity, UserSession
```

### D. Đăng ký admin trong judge/admin/__init__.py:
```python
from . import user_activity  # Thêm dòng này
```

## 4. Database Migration

### Tạo migration file:
```bash
python manage.py makemigrations judge
```

### Chạy migration:
```bash
python manage.py migrate
```

### Tạo permission (nếu cần):
```bash
python manage.py shell
```
```python
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from judge.models import Profile

content_type = ContentType.objects.get_for_model(Profile)
permission, created = Permission.objects.get_or_create(
    codename='can_see_user_activity',
    name='Can see user activity',
    content_type=content_type,
)
```

## 5. Cấp quyền cho Admin

### Trong Django Admin hoặc shell:
```python
from django.contrib.auth.models import User
from judge.models import Profile

# Cách 1: Qua Django Admin
# Vào Admin → Users → chọn user → User permissions → thêm "Can see user activity"

# Cách 2: Qua Python shell
user = User.objects.get(username='admin_username')
user.user_permissions.add(Permission.objects.get(codename='can_see_user_activity'))
```

## 6. Static Files và Templates

### A. Đảm bảo có Bootstrap và Chart.js trong base template:
```html
<!-- Bootstrap CSS -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
```

### B. Collect static files:
```bash
python manage.py collectstatic --noinput
```

## 7. Kiểm tra Cài đặt

### A. Kiểm tra URL hoạt động:
```bash
# Test middleware
python manage.py shell
```
```python
from django.test import Client
c = Client()
response = c.get('/')
print("Middleware working" if response.status_code == 200 else "Error")
```

### B. Kiểm tra database tables:
```bash
python manage.py shell
```
```python
from judge.models import UserSession, UserActivity
print(f"UserSession table: {UserSession.objects.count()} records")
print(f"UserActivity table: {UserActivity.objects.count()} records")
```

### C. Test URLs (sau khi đăng nhập admin):
- `/admin/user-activity/active-users/` - Dashboard chính
- `/admin/user-activity/all-logs/` - Xem logs
- `/admin/user-activity/api/active-users/` - API endpoint

## 8. Trouble Shooting

### Lỗi thường gặp:

#### A. ImportError middleware
```bash
# Kiểm tra đường dẫn middleware trong settings.py
'judge.middlewares.user_activity.UserActivityMiddleware'  # Đúng
'judge.middleware.user_activity.UserActivityMiddleware'   # Sai (conflict)
```

#### B. Migration error
```bash
# Xóa migration files nếu có lỗi
rm judge/migrations/00*_user_activity.py
python manage.py makemigrations judge --name user_activity
python manage.py migrate
```

#### C. Permission denied
```bash
# Đảm bảo user có quyền
python manage.py shell
```
```python
user.user_permissions.add(Permission.objects.get(codename='can_see_user_activity'))
```

#### D. Static files không load
```bash
python manage.py collectstatic --noinput
# Kiểm tra STATIC_URL và STATIC_ROOT trong settings
```

## 9. Tối ưu Performance

### A. Database Indexing
Models đã có index sẵn, nhưng có thể thêm:
```python
# Trong UserActivity model
class Meta:
    indexes = [
        models.Index(fields=['user', '-timestamp']),
        models.Index(fields=['timestamp']),
        models.Index(fields=['ip_address', '-timestamp']),
        models.Index(fields=['session', '-timestamp']),  # Thêm nếu cần
    ]
```

### B. Cleanup Task (Optional)
Tạo task tự động xóa logs cũ:
```python
# judge/management/commands/cleanup_user_activity.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from judge.models import UserActivity

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Xóa logs cũ hơn 30 ngày
        cutoff_date = timezone.now() - timedelta(days=30)
        deleted = UserActivity.objects.filter(timestamp__lt=cutoff_date).delete()
        self.stdout.write(f"Deleted {deleted[0]} old activity records")
```

### C. Crontab setup:
```bash
# Thêm vào crontab
0 2 * * * cd /path/to/project && python manage.py cleanup_user_activity
```

## 10. Monitoring và Logs

### A. Kiểm tra logs Django:
```python
import logging
logger = logging.getLogger('judge.middlewares.user_activity')
```

### B. Monitor database size:
```bash
# MySQL
SELECT table_name, 
       ROUND(((data_length + index_length) / 1024 / 1024), 2) as "Size (MB)" 
FROM information_schema.TABLES 
WHERE table_schema = 'your_db_name' 
AND table_name LIKE '%activity%';
```

## 11. Features Chính

### A. Dashboard Features:
- Tổng số users online real-time
- Phân biệt authenticated vs anonymous
- Warning cho multi-session users
- Thống kê theo device/browser
- IP analysis
- Auto-refresh 30 giây

### B. User Detail Features:
- Lịch sử hoạt động chi tiết
- Charts hiển thị activity theo thời gian
- Session management
- Thống kê cá nhân

### C. Logs Management:
- Filter theo user, IP, time range
- Pagination cho performance
- Export CSV
- Bulk delete options

## 12. Security Notes

- Middleware exclude admin endpoints để tránh loop
- CSRF protection cho tất cả forms
- Permission-based access control
- IP tracking cho security audit
- Session management cho multi-device detection

## Kết luận

Sau khi hoàn thành các bước trên, hệ thống sẽ:
1. Tự động tracking mọi user activity
2. Hiển thị real-time dashboard
3. Cung cấp tools quản lý logs
4. Hỗ trợ both authenticated và anonymous users
5. Có các tính năng bảo mật và performance optimization

**Lưu ý quan trọng**: 
- Luôn backup database trước khi chạy migration
- Test trên development environment trước
- Monitor database size và performance sau khi deploy
- Tránh naming conflict giữa files và folders

## 13. Kiểm tra Naming Conflicts

### Các xung đột có thể xảy ra trong Django project:

#### A. ✅ FIXED: middleware.py vs middleware/
```bash
# SAI (gây conflict):
judge/middleware.py        # File gốc hệ thống
judge/middleware/          # Folder tự tạo

# ĐÚNG (đã fix):
judge/middleware.py        # File gốc hệ thống  
judge/middlewares/         # Folder custom
```

#### B. ⚠️ CẢNH BÁO: Các conflicts tiềm ẩn khác:
```bash
# Kiểm tra xung đột trong project:
judge/forms.py             # File hiện tại
judge/forms/               # Nếu tạo folder này sẽ conflict

judge/signals.py           # File hiện tại  
judge/signals/             # Nếu tạo folder này sẽ conflict

judge/views/tasks.py       # File hiện tại
judge/tasks/               # Folder hiện tại - OK vì không có tasks.py

judge/views/widgets.py     # File hiện tại
judge/widgets/             # Folder hiện tại - OK vì trong views/ subfolder
```

#### C. Cách phòng tránh conflicts:
```bash
# 1. Luôn dùng suffix cho custom folders:
judge/middlewares/         # Thay vì middleware/
judge/custom_forms/        # Thay vì forms/ (nếu cần)
judge/custom_signals/      # Thay vì signals/ (nếu cần)

# 2. Kiểm tra trước khi tạo folder mới:
ls judge/ | grep -E "^(folder_name)(\.|/)$"

# 3. Validate imports:
python manage.py shell -c "import judge.middlewares.user_activity"
```

#### D. Script kiểm tra conflicts:
```python
# check_conflicts.py
import os
import glob

def check_naming_conflicts():
    judge_dir = 'judge/'
    files = [f for f in os.listdir(judge_dir) if f.endswith('.py')]
    folders = [f for f in os.listdir(judge_dir) if os.path.isdir(os.path.join(judge_dir, f))]
    
    file_names = [f[:-3] for f in files]  # Remove .py extension
    
    conflicts = []
    for folder in folders:
        if folder in file_names:
            conflicts.append(f"CONFLICT: {folder}/ vs {folder}.py")
    
    if conflicts:
        print("⚠️ Naming conflicts found:")
        for conflict in conflicts:
            print(f"  - {conflict}")
    else:
        print("✅ No naming conflicts detected")

if __name__ == "__main__":
    check_naming_conflicts()
```

### Sử dụng script kiểm tra:
```bash
python check_conflicts.py
```

## 14. Migration Safety

### A. Backup trước khi migrate:
```bash
# MySQL backup
mysqldump -u username -p database_name > backup_$(date +%Y%m%d_%H%M%S).sql

# PostgreSQL backup  
pg_dump database_name > backup_$(date +%Y%m%d_%H%M%S).sql

# SQLite backup
cp db.sqlite3 db_backup_$(date +%Y%m%d_%H%M%S).sqlite3
```

### B. Test migration trên dev:
```bash
# 1. Copy database
python manage.py dumpdata > dev_data.json

# 2. Test migrate
python manage.py migrate --dry-run

# 3. Rollback if needed
python manage.py migrate judge zero  # Rollback judge app
python manage.py migrate judge       # Re-apply
```

### C. Production deployment:
```bash
# 1. Maintenance mode
touch maintenance.html

# 2. Backup
mysqldump -u user -p prod_db > backup_before_user_activity.sql

# 3. Deploy code
git pull origin main

# 4. Install dependencies
pip install -r requirements.txt

# 5. Migrate
python manage.py migrate

# 6. Collect static
python manage.py collectstatic --noinput

# 7. Restart services
sudo systemctl restart gunicorn
sudo systemctl restart nginx

# 8. Remove maintenance
rm maintenance.html
``` 