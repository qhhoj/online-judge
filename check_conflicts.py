#!/usr/bin/env python3
"""
Script kiểm tra xung đột tên file/folder trong Django project
Giúp phát hiện các conflicts như middleware.py vs middleware/ 
"""

import os
import sys

def check_naming_conflicts():
    """Kiểm tra conflicts trong judge/ directory"""
    judge_dir = 'judge/'
    
    if not os.path.exists(judge_dir):
        print(f"❌ Directory {judge_dir} không tồn tại!")
        return False
    
    # Lấy danh sách files và folders
    try:
        items = os.listdir(judge_dir)
        files = [f for f in items if os.path.isfile(os.path.join(judge_dir, f)) and f.endswith('.py')]
        folders = [f for f in items if os.path.isdir(os.path.join(judge_dir, f)) and f != '__pycache__']
        
        # Loại bỏ .py extension để so sánh
        file_names = [f[:-3] for f in files]
        
        conflicts = []
        for folder in folders:
            if folder in file_names:
                conflicts.append({
                    'file': f"{folder}.py",
                    'folder': f"{folder}/",
                    'severity': 'HIGH' if folder in ['middleware', 'models', 'views', 'forms', 'admin'] else 'MEDIUM'
                })
        
        print("=" * 60)
        print("🔍 KIỂM TRA NAMING CONFLICTS")
        print("=" * 60)
        
        if conflicts:
            print("⚠️ PHÁT HIỆN CONFLICTS:")
            print()
            for conflict in conflicts:
                severity_icon = "🔥" if conflict['severity'] == 'HIGH' else "⚡"
                print(f"{severity_icon} {conflict['severity']} CONFLICT:")
                print(f"   File: judge/{conflict['file']}")
                print(f"   Folder: judge/{conflict['folder']}")
                
                if conflict['severity'] == 'HIGH':
                    print(f"   💡 Khuyến nghị: Đổi tên folder thành {conflict['folder'][:-1]}s/")
                print()
                
            print("🔧 CÁCH KHẮC PHỤC:")
            print("1. Đổi tên folder conflict (khuyến nghị thêm 's' hoặc prefix)")
            print("2. Cập nhật tất cả imports trong code")
            print("3. Cập nhật settings.py nếu cần")
            print("4. Test lại toàn bộ hệ thống")
            
            return False
        else:
            print("✅ KHÔNG PHÁT HIỆN CONFLICTS")
            print()
            print("📊 THỐNG KÊ:")
            print(f"   - Files .py: {len(files)}")
            print(f"   - Folders: {len(folders)}")
            print(f"   - Tổng items: {len(items) - 1}")  # -1 for __pycache__
            print()
            print("🎉 Project structure an toàn!")
            
            return True
            
    except Exception as e:
        print(f"❌ Lỗi khi kiểm tra: {e}")
        return False

def check_imports():
    """Kiểm tra imports có hoạt động không"""
    print("\n" + "=" * 60)
    print("🔗 KIỂM TRA IMPORTS")
    print("=" * 60)
    
    test_imports = [
        'judge.middlewares.user_activity',
        'judge.models.user_activity',
        'judge.views.user_activity',
        'judge.admin.user_activity',
    ]
    
    success_count = 0
    
    for import_path in test_imports:
        try:
            __import__(import_path)
            print(f"✅ {import_path}")
            success_count += 1
        except ImportError as e:
            print(f"❌ {import_path} - {e}")
        except Exception as e:
            print(f"⚠️ {import_path} - {e}")
    
    print(f"\n📊 KẾT QUẢ: {success_count}/{len(test_imports)} imports thành công")
    
    if success_count == len(test_imports):
        print("🎉 Tất cả imports hoạt động tốt!")
        return True
    else:
        print("⚠️ Có imports bị lỗi, kiểm tra lại cấu hình!")
        return False

def main():
    """Main function"""
    print("🚀 DJANGO PROJECT CONFLICT CHECKER")
    print("Phiên bản: 1.0")
    print("Tác giả: QHHOJ Team")
    
    # Kiểm tra conflicts
    conflicts_ok = check_naming_conflicts()
    
    # Kiểm tra imports (chỉ khi không có conflicts)
    if conflicts_ok:
        imports_ok = check_imports()
        
        if imports_ok:
            print("\n🎯 KẾT LUẬN: Project sẵn sàng deploy!")
            sys.exit(0)
        else:
            print("\n⚠️ KẾT LUẬN: Cần fix imports trước khi deploy!")
            sys.exit(1)
    else:
        print("\n❌ KẾT LUẬN: Cần fix naming conflicts trước!")
        sys.exit(1)

if __name__ == "__main__":
    main() 