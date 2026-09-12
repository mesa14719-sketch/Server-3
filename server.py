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
import ast
import urllib.request
import urllib.error
from datetime import datetime
from io import BytesIO

app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

# ==================== قاعدة البيانات ====================
DB_FILE = "tools_db.json"


def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(db):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ==================== دوال مساعدة ====================

def generate_license_key(tool_id, length=32):
    random_part = ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(length)
    )
    return f"{tool_id.upper()[:8]}-{random_part}"


def count_inputs_in_code(code_text):
    """
    تحليل كود Python وعدّ استدعاءات input() مع استخراج prompts.
    """
    try:
        tree = ast.parse(code_text)
    except SyntaxError as e:
        raise ValueError(f"خطأ في بناء الجملة: {e}")

    inputs_found = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'input':
                prompt = ""
                if node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant):
                        prompt = str(arg.value)
                    elif isinstance(arg, ast.JoinedStr):
                        # f-string مثل input(f"أدخل {x}: ")
                        prompt = "أدخل قيمة"
                inputs_found.append(prompt)

    return inputs_found


def fetch_code_from_url(url):
    """
    جلب كود Python من رابط (GitHub Raw أو أي رابط مباشر).
    """
    # تحويل روابط GitHub العادية إلى Raw
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 ToolServer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        raise ValueError(f"فشل تحميل الرابط (HTTP {e.code}): {url}")
    except urllib.error.URLError as e:
        raise ValueError(f"فشل الاتصال بالرابط: {e.reason}")
    except Exception as e:
        raise ValueError(f"خطأ في تحميل الرابط: {str(e)}")


def generate_client_file(tool_id, license_key, server_url, tool_name=None, inputs_prompts=None):
    """توليد ملف العميل تلقائياً مع دعم الإدخالات."""
    tool_name = tool_name or tool_id
    inputs_prompts = inputs_prompts or []
    prompts_repr = repr(inputs_prompts) if inputs_prompts else "[]"

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
INPUTS_PROMPTS = {prompts_repr}
# ==============================================================


def print_banner():
    print("=" * 60)
    print(f"  🛠️  {{TOOL_NAME}}")
    print("=" * 60)


def collect_inputs():
    """جمع الإدخالات من المستخدم بناءً على ما تحتاجه الأداة."""
    if not INPUTS_PROMPTS:
        return ""

    print(f"\\n📝 الأداة تحتاج {{len(INPUTS_PROMPTS)}} مدخل(ات):")
    print("-" * 60)

    values = []
    for i, prompt in enumerate(INPUTS_PROMPTS, 1):
        clean_prompt = prompt.strip() or f"مدخل #{{i}}"
        value = input(f"{{i}}. {{clean_prompt}}: ").strip()
        values.append(value)

    # خيار إضافة مدخلات إضافية
    while True:
        more = input("\\n➕ مدخل إضافي؟ (Enter للتخطي): ").strip()
        if not more:
            break
        values.append(more)

    return "\\n".join(values) + "\\n"


def execute_tool(stdin_input="", args=None):
    """إرسال طلب التنفيذ للخادم."""
    try:
        response = requests.post(
            f"{{SERVER_URL}}/execute",
            json={{
                "tool_id": TOOL_ID,
                "license_key": LICENSE_KEY,
                "args": args or [],
                "stdin_input": stdin_input
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
    print(f"📡 الخادم: {{SERVER_URL}}")
    print("-" * 60)

    stdin_input = collect_inputs()

    print(f"\\n⏳ جاري التنفيذ على الخادم...")
    print("=" * 60)

    success = execute_tool(stdin_input=stdin_input)

    print("=" * 60)
    if success:
        print("✅ تم الانتهاء بنجاح")
    else:
        print("❌ فشل التنفيذ")
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
    return request.host_url.rstrip('/')


# ==================== المسارات ====================

@app.route('/')
def home():
    db = load_db()
    return jsonify({
        "status": "🟢 الخادم يعمل",
        "tools_count": len(db),
        "version": "2.0.0"
    })


@app.route('/admin')
def admin_panel():
    return render_template_string(ADMIN_HTML)


@app.route('/upload_tool', methods=['POST'])
def upload_tool():
    """
    رفع أداة جديدة.
    يستقبل:
      - tool_id, tool_name, dependencies, max_executions, expires_at
      - إما: code (base64)
      - أو: code_url (رابط GitHub Raw أو أي رابط مباشر)
    """
    try:
        data = request.get_json()

        tool_id = data.get('tool_id', '').strip()
        tool_name = data.get('tool_name', tool_id).strip()
        encoded_code = data.get('code')
        code_url = data.get('code_url', '').strip()
        dependencies = data.get('dependencies', [])

        if not tool_id:
            return jsonify({"error": "tool_id مطلوب"}), 400

        # ✅ الحصول على الكود من مصدرين
        code_text = None

        if code_url:
            # من رابط
            try:
                code_text = fetch_code_from_url(code_url)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        elif encoded_code:
            # من Base64
            try:
                code_text = base64.b64decode(encoded_code).decode('utf-8')
            except Exception as e:
                return jsonify({"error": f"فشل فك Base64: {str(e)}"}), 400
        else:
            return jsonify({"error": "يجب توفير code أو code_url"}), 400

        # التحقق من أن الكود بايثون صالح
        try:
            compile(code_text, '<string>', 'exec')
        except SyntaxError as e:
            return jsonify({"error": f"كود بايثون غير صالح: {str(e)}"}), 400

        # ✅ اكتشاف الإدخالات تلقائياً
        try:
            detected_inputs = count_inputs_in_code(code_text)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        print(f"\n🔍 تحليل الأداة '{tool_id}':")
        print(f"   📦 عدد الإدخالات المكتشفة: {len(detected_inputs)}")
        for i, prompt in enumerate(detected_inputs, 1):
            print(f"      {i}. {prompt or '(بدون نص)'}")

        # إعادة ترميز الكود بـ Base64 للتخزين
        stored_code = base64.b64encode(code_text.encode('utf-8')).decode('utf-8')

        db = load_db()
        if tool_id in db:
            return jsonify({"error": f"الأداة '{tool_id}' موجودة مسبقاً"}), 409

        license_key = generate_license_key(tool_id)
        server_url = get_server_url(request)

        client_code = generate_client_file(
            tool_id=tool_id,
            license_key=license_key,
            server_url=server_url,
            tool_name=tool_name,
            inputs_prompts=detected_inputs
        )

        db[tool_id] = {
            "tool_id": tool_id,
            "tool_name": tool_name,
            "code": stored_code,
            "license_key": license_key,
            "dependencies": dependencies,
            "created_at": datetime.now().isoformat(),
            "executions": 0,
            "max_executions": data.get('max_executions', 0),
            "expires_at": data.get('expires_at', None),
            "inputs_prompts": detected_inputs,
            "source_url": code_url if code_url else None
        }
        save_db(db)

        return jsonify({
            "status": "success",
            "message": f"✅ تم رفع الأداة '{tool_name}' بنجاح",
            "tool_id": tool_id,
            "license_key": license_key,
            "inputs_count": len(detected_inputs),
            "inputs_prompts": detected_inputs,
            "client_code": client_code
        }), 201

    except Exception as e:
        return jsonify({"error": f"خطأ في الخادم: {str(e)}"}), 500


@app.route('/execute', methods=['POST'])
def execute_tool():
    """
    تنفيذ أداة مخزّنة.
    يستقبل: tool_id, license_key, args, stdin_input
    """
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        license_key = data.get('license_key', '').strip()
        user_args = data.get('args', [])
        stdin_input = data.get('stdin_input', '')

        if not all([tool_id, license_key]):
            return jsonify({"error": "tool_id و license_key مطلوبان"}), 400

        db = load_db()
        if tool_id not in db:
            return jsonify({"error": "الأداة غير موجودة"}), 404

        tool = db[tool_id]

        if not hmac.compare_digest(tool['license_key'], license_key):
            return jsonify({"error": "كود الترخيص غير صالح"}), 403

        if tool.get('expires_at'):
            if datetime.now() > datetime.fromisoformat(tool['expires_at']):
                return jsonify({"error": "انتهت صلاحية الترخيص"}), 403

        max_exec = tool.get('max_executions', 0)
        if max_exec > 0 and tool['executions'] >= max_exec:
            return jsonify({"error": "انتهت صلاحية الترخيص (تجاوز الحد)"}), 403

        db[tool_id]['executions'] += 1
        save_db(db)

        try:
            code_bytes = base64.b64decode(tool['code'])
        except Exception:
            return jsonify({"error": "خطأ في قراءة الأداة"}), 500

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.py', delete=False
            ) as f:
                f.write(code_bytes)
                temp_path = f.name

            # ✅ تمرير stdin_input للأداة (يحل مشكلة input())
            result = subprocess.run(
                [sys.executable, temp_path] + [str(a) for a in user_args],
                capture_output=True,
                text=True,
                timeout=120,
                input=stdin_input,
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
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    tool = db[tool_id]
    return jsonify({
        "tool_id": tool['tool_id'],
        "tool_name": tool['tool_name'],
        "created_at": tool['created_at'],
        "executions": tool['executions'],
        "dependencies": tool['dependencies'],
        "inputs_count": len(tool.get('inputs_prompts', [])),
        "inputs_prompts": tool.get('inputs_prompts', []),
        "source_url": tool.get('source_url')
    })


@app.route('/download_client/<tool_id>', methods=['GET'])
def download_client(tool_id):
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    tool = db[tool_id]
    server_url = get_server_url(request)

    client_code = generate_client_file(
        tool_id=tool_id,
        license_key=tool['license_key'],
        server_url=server_url,
        tool_name=tool['tool_name'],
        inputs_prompts=tool.get('inputs_prompts', [])
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
            "dependencies": tool['dependencies'],
            "inputs_count": len(tool.get('inputs_prompts', []))
        })

    return jsonify({"tools": tools, "count": len(tools)})


@app.route('/delete_tool/<tool_id>', methods=['DELETE'])
def delete_tool(tool_id):
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
    <title>لوحة التحكم</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #38bdf8; margin-bottom: 20px; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #334155; }
        button { padding: 10px 20px; border-radius: 8px; background: #38bdf8; color: #0f172a; cursor: pointer; font-weight: bold; border: none; font-size: 14px; }
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
            <table>
                <thead>
                    <tr>
                        <th>المعرّف</th>
                        <th>الاسم</th>
                        <th>الاستخدامات</th>
                        <th>الإدخالات</th>
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
                            <td>${tool.inputs_count}</td>
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
        window.addEventListener('load', loadTools);
    </script>
</body>
</html>
"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
