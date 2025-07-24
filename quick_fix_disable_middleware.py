#!/usr/bin/env python3
"""
Quick fix script để disable UserActivity middleware trong trường hợp khẩn cấp
"""

import os
import sys

def disable_middleware():
    """Disable UserActivity middleware bằng cách comment out trong settings.py"""
    settings_path = 'dmoj/settings.py'
    
    if not os.path.exists(settings_path):
        print(f"❌ File {settings_path} không tồn tại!")
        return False
    
    try:
        # Đọc file settings
        with open(settings_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Comment out middleware
        old_line = "'judge.middlewares.user_activity_safe.UserActivityMiddleware',"
        new_line = "# 'judge.middlewares.user_activity_safe.UserActivityMiddleware',  # DISABLED DUE TO ERROR"
        
        if old_line in content:
            content = content.replace(old_line, new_line)
            
            # Ghi lại file
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ UserActivity middleware đã được DISABLE!")
            print("🔄 Restart server để áp dụng changes:")
            print("   sudo systemctl restart gunicorn")
            print("   sudo systemctl restart nginx")
            return True
        else:
            print("⚠️ Middleware line không tìm thấy trong settings.py")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi khi disable middleware: {e}")
        return False

def enable_middleware():
    """Enable lại UserActivity middleware"""
    settings_path = 'dmoj/settings.py'
    
    if not os.path.exists(settings_path):
        print(f"❌ File {settings_path} không tồn tại!")
        return False
    
    try:
        # Đọc file settings
        with open(settings_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Uncomment middleware
        old_line = "# 'judge.middlewares.user_activity_safe.UserActivityMiddleware',  # DISABLED DUE TO ERROR"
        new_line = "'judge.middlewares.user_activity_safe.UserActivityMiddleware',"
        
        if old_line in content:
            content = content.replace(old_line, new_line)
            
            # Ghi lại file
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ UserActivity middleware đã được ENABLE!")
            print("🔄 Restart server để áp dụng changes:")
            print("   sudo systemctl restart gunicorn")
            print("   sudo systemctl restart nginx")
            return True
        else:
            print("⚠️ Disabled middleware line không tìm thấy trong settings.py")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi khi enable middleware: {e}")
        return False

def main():
    print("🚨 QUICK FIX - UserActivity Middleware Control")
    print("=" * 50)
    
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python quick_fix_disable_middleware.py disable")
        print("  python quick_fix_disable_middleware.py enable")
        sys.exit(1)
    
    action = sys.argv[1].lower()
    
    if action == 'disable':
        print("🔴 DISABLING UserActivity Middleware...")
        if disable_middleware():
            print("\n🎯 Middleware đã được disable!")
            print("   Server sẽ hoạt động bình thường mà không tracking user activity")
        else:
            print("\n❌ Không thể disable middleware!")
            sys.exit(1)
            
    elif action == 'enable':
        print("🟢 ENABLING UserActivity Middleware...")
        if enable_middleware():
            print("\n🎯 Middleware đã được enable!")
            print("   User activity tracking sẽ hoạt động trở lại")
        else:
            print("\n❌ Không thể enable middleware!")
            sys.exit(1)
    else:
        print("❌ Invalid action. Use 'disable' or 'enable'")
        sys.exit(1)

if __name__ == "__main__":
    main() 