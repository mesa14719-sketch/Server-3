# app.py
from flask import Flask, request, jsonify, send_file, render_template_string
import os
import base64
import hmac
import subprocess
import tempfile
import sys
import secrets
import string
import json
from datetime import datetime
from io import BytesIO

app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

# ==================== قاعدة البيانات (ملف JSON) ====================
DB_FILE = "tools_db.json"


def load_db():
    """تحميل قاعدة البيانات من الملف"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(db):
    """حفظ قاعدة البيانات في الملف"""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ==================== دوال مساعدة ====================

def generate_license_key(tool_id, length=32):
    """توليد كود ترخيص عشوائي فريد"""
    random_part = ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(length)
    )
    return f"{tool_id.upper()[:8]}-{random_part}"


def generate_client_file(tool_id, license_key, server_url, tool_name=None):
    """توليد ملف العميل تلقائياً (لا يحتوي على أي كود من الأداة)"""
    tool_name = tool_name or tool_id

    client_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  {tool_name} - Client
  تم إنشاؤه تلقائياً بواسطة نظام الحماية
  التاريخ: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
============================================================
  
  ⚠️ هذا الملف لا يحتوي على أي كود من الأداة.
  الأداة تعمل على الخادم فقط.
============================================================
"""

import requests
import sys
import os

# ==================== الإعدادات (لا تعدلها) ====================
SERVER_URL = "{server_url}"
TOOL_ID = "{tool_id}"
LICENSE_KEY = "{license_key}"
TOOL_NAME = "{tool_name}"
# ==============================================================


def print_banner():
    print("=" * 60)
    print(f"  🛠️  {{TOOL_NAME}}")
    print("=" * 60)


def execute_tool(args=None):
    """إرسال طلب التنفيذ للخادم"""
    try:
        response = requests.post(
            f"{{SERVER_URL}}/execute",
            json={{
                "tool_id": TOOL_ID,
                "license_key": LICENSE_KEY,
                "args": args or []
            }},
            timeout=120
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("stdout"):
                print(data["stdout"])
            if data.get("stderr"):
                print("⚠️ تحذيرات:")
                print(data["stderr"])
            return True
        else:
            try:
                error = response.json().get("error", "خطأ غير معروف")
            except Exception:
                error = response.text
            print(f"❌ خطأ ({{response.status_code}}): {{error}}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ انتهت المهلة - الخادم بطيء")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ فشل الاتصال بالخادم")
        return False
    except Exception as e:
        print(f"❌ خطأ: {{e}}")
        return False


def main():
    print_banner()
    print(f"🔑 الترخيص: {{LICENSE_KEY[:20]}}...")
    print(f"📡 الخادم: {{SERVER_URL}}")
    print("-" * 60)
    
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    if not args:
        print("📝 أدخل الوسائط المطلوبة (أو اتركها فارغة واضغط Enter):")
        user_input = input("> ").strip()
        if user_input:
            args = user_input.split()
    
    print(f"\\n⏳ جاري التنفيذ على الخادم...")
    
    success = execute_tool(args)
    
    if success:
        print("\\n✅ تم الانتهاء بنجاح")
    else:
        print("\\n❌ فشل التنفيذ")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\\n\\n👋 تم الإلغاء")
        sys.exit(0)
'''
    return client_code


def get_server_url(request):
    """استخراج رابط الخادم من الطلب"""
    return request.host_url.rstrip('/')


# ==================== المسارات (Endpoints) ====================

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    db = load_db()
    tools_count = len(db)
    return jsonify({
        "status": "🟢 الخادم يعمل",
        "tools_count": tools_count,
        "version": "1.0.0"
    })


@app.route('/admin')
def admin_panel():
    """لوحة تحكم بسيطة"""
    return render_template_string(ADMIN_HTML)


@app.route('/upload_tool', methods=['POST'])
def upload_tool():
    """
    رفع أداة جديدة إلى الخادم (بدون كلمة مرور).
    يستقبل: tool_id, tool_name, code (base64), dependencies, max_executions, expires_at
    يُرجع: license_key + client_code
    """
    try:
        data = request.get_json()

        tool_id = data.get('tool_id', '').strip()
        tool_name = data.get('tool_name', tool_id).strip()
        encoded_code = data.get('code')
        dependencies = data.get('dependencies', [])

        if not all([tool_id, encoded_code]):
            return jsonify({"error": "الحقول المطلوبة ناقصة"}), 400

        # التحقق من أن الكود بايثون صالح
        try:
            code_bytes = base64.b64decode(encoded_code)
            code_text = code_bytes.decode('utf-8')
            compile(code_text, '<string>', 'exec')
        except Exception as e:
            return jsonify({"error": f"كود بايثون غير صالح: {str(e)}"}), 400

        # التحقق من عدم وجود الأداة مسبقاً
        db = load_db()
        if tool_id in db:
            return jsonify({"error": f"الأداة '{tool_id}' موجودة مسبقاً"}), 409

        # توليد كود ترخيص عشوائي
        license_key = generate_license_key(tool_id)

        # الحصول على رابط الخادم
        server_url = get_server_url(request)

        # توليد ملف العميل تلقائياً
        client_code = generate_client_file(
            tool_id=tool_id,
            license_key=license_key,
            server_url=server_url,
            tool_name=tool_name
        )

        # تخزين الأداة في قاعدة البيانات
        db[tool_id] = {
            "tool_id": tool_id,
            "tool_name": tool_name,
            "code": encoded_code,
            "license_key": license_key,
            "dependencies": dependencies,
            "created_at": datetime.now().isoformat(),
            "executions": 0,
            "max_executions": data.get('max_executions', 0),
            "expires_at": data.get('expires_at', None)
        }
        save_db(db)

        return jsonify({
            "status": "success",
            "message": f"✅ تم رفع الأداة '{tool_name}' بنجاح",
            "tool_id": tool_id,
            "license_key": license_key,
            "client_code": client_code,
            "instructions": "احفظ client_code في ملف .py وأرسله للمستخدم"
        }), 201

    except Exception as e:
        return jsonify({"error": f"خطأ في الخادم: {str(e)}"}), 500


@app.route('/execute', methods=['POST'])
def execute_tool():
    """
    تنفيذ أداة مخزّنة.
    يستقبل: tool_id, license_key, args
    """
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        license_key = data.get('license_key', '').strip()
        user_args = data.get('args', [])

        if not all([tool_id, license_key]):
            return jsonify({"error": "tool_id و license_key مطلوبان"}), 400

        # البحث عن الأداة
        db = load_db()
        if tool_id not in db:
            return jsonify({"error": "الأداة غير موجودة"}), 404

        tool = db[tool_id]

        # التحقق من الترخيص
        if not hmac.compare_digest(tool['license_key'], license_key):
            return jsonify({"error": "كود الترخيص غير صالح"}), 403

        # التحقق من تاريخ الانتهاء
        if tool.get('expires_at'):
            if datetime.now() > datetime.fromisoformat(tool['expires_at']):
                return jsonify({"error": "انتهت صلاحية الترخيص"}), 403

        # التحقق من حد الاستخدام
        max_exec = tool.get('max_executions', 0)
        if max_exec > 0 and tool['executions'] >= max_exec:
            return jsonify({"error": "انتهت صلاحية الترخيص (تجاوز الحد الأقصى)"}), 403

        # زيادة عداد الاستخدام
        db[tool_id]['executions'] += 1
        save_db(db)

        # فك تشفير الكود
        try:
            code_bytes = base64.b64decode(tool['code'])
        except Exception:
            return jsonify({"error": "خطأ في قراءة الأداة"}), 500

        # كتابة الكود في ملف مؤقت وتنفيذه
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.py', delete=False
            ) as f:
                f.write(code_bytes)
                temp_path = f.name

            result = subprocess.run(
                [sys.executable, temp_path] + [str(a) for a in user_args],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )

            return jsonify({
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "executions": db[tool_id]['executions']
            })

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "انتهت مهلة التنفيذ (120 ثانية)"}), 408
    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/tool_info/<tool_id>', methods=['GET'])
def tool_info(tool_id):
    """معلومات عن أداة (بدون كود)"""
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    tool = db[tool_id]
    return jsonify({
        "tool_id": tool['tool_id'],
        "tool_name": tool['tool_name'],
        "created_at": tool['created_at'],
        "executions": tool['executions'],
        "dependencies": tool['dependencies']
    })


@app.route('/download_client/<tool_id>', methods=['GET'])
def download_client(tool_id):
    """تحميل ملف العميل لأداة موجودة (بدون كلمة مرور)"""
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    tool = db[tool_id]
    server_url = get_server_url(request)

    client_code = generate_client_file(
        tool_id=tool_id,
        license_key=tool['license_key'],
        server_url=server_url,
        tool_name=tool['tool_name']
    )

    buffer = BytesIO(client_code.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='text/x-python',
        as_attachment=True,
        download_name=f"client_{tool_id}.py"
    )


@app.route('/list_tools', methods=['GET'])
def list_tools():
    """قائمة الأدوات (بدون كلمة مرور)"""
    db = load_db()
    tools = []
    for tool_id, tool in db.items():
        tools.append({
            "tool_id": tool_id,
            "tool_name": tool['tool_name'],
            "created_at": tool['created_at'],
            "executions": tool['executions'],
            "max_executions": tool.get('max_executions', 0),
            "license_key": tool['license_key'][:15] + "...",
            "dependencies": tool['dependencies']
        })

    return jsonify({"tools": tools, "count": len(tools)})


@app.route('/delete_tool/<tool_id>', methods=['DELETE'])
def delete_tool(tool_id):
    """حذف أداة (بدون كلمة مرور)"""
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    del db[tool_id]
    save_db(db)

    return jsonify({"status": "success", "message": f"تم حذف '{tool_id}'"})


# ==================== لوحة التحكم HTML ====================
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>لوحة التحكم - نظام حماية الأدوات</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #38bdf8; margin-bottom: 20px; }
        .card {
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #334155;
        }
        button {
            padding: 10px 20px;
            border-radius: 8px;
            background: #38bdf8;
            color: #0f172a;
            cursor: pointer;
            font-weight: bold;
            border: none;
            font-size: 14px;
        }
        button:hover { background: #0ea5e9; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: right; border-bottom: 1px solid #334155; }
        th { color: #38bdf8; }
        .status { padding: 8px 12px; border-radius: 6px; margin-top: 10px; }
        .success { background: #065f46; color: #6ee7b7; }
        .error { background: #7f1d1d; color: #fca5a5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ لوحة تحكم نظام حماية الأدوات</h1>

        <div class="card">
            <button onclick="loadTools()">🔄 تحديث قائمة الأدوات</button>
            <div id="status"></div>
        </div>

        <div class="card">
            <h3>📋 الأدوات المسجّلة</h3>
            <table id="toolsTable">
                <thead>
                    <tr>
                        <th>المعرّف</th>
                        <th>الاسم</th>
                        <th>الاستخدامات</th>
                        <th>الترخيص</th>
                        <th>التاريخ</th>
                    </tr>
                </thead>
                <tbody id="toolsBody"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function loadTools() {
            const status = document.getElementById('status');

            try {
                const res = await fetch('/list_tools');
                const data = await res.json();

                if (res.ok) {
                    status.className = 'status success';
                    status.textContent = '✅ تم التحميل: ' + data.count + ' أداة';

                    const tbody = document.getElementById('toolsBody');
                    tbody.innerHTML = '';
                    data.tools.forEach(tool => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${tool.tool_id}</td>
                            <td>${tool.tool_name}</td>
                            <td>${tool.executions}</td>
                            <td>${tool.license_key}</td>
                            <td>${tool.created_at.split('T')[0]}</td>
                        `;
                        tbody.appendChild(row);
                    });
                } else {
                    status.className = 'status error';
                    status.textContent = '❌ ' + data.error;
                }
            } catch (e) {
                status.className = 'status error';
                status.textContent = '❌ خطأ: ' + e.message;
            }
        }

        // تحميل تلقائي عند فتح الصفحة
        window.addEventListener('load', loadTools);
    </script>
</body>
</html>
"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
