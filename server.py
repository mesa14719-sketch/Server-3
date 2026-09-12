# app.py - بسيط ومباشر
from flask import Flask, request, jsonify, send_file, render_template_string
import os
import subprocess
import tempfile
import sys
import secrets
import string
import json
import ast
import threading
import uuid
from datetime import datetime
from io import BytesIO

app = Flask(__name__)

# ==================== الإعدادات ====================
MAX_EXECUTION_TIME = 600   # 10 دقائق
JOB_RETENTION = 3600       # ساعة

# مجلد تخزين الأدوات
TOOLS_DIR = "tools_storage"
os.makedirs(TOOLS_DIR, exist_ok=True)

DB_FILE = "tools_db.json"
DB_LOCK = threading.Lock()


# ==================== قاعدة البيانات ====================
def load_db():
    with DB_LOCK:
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}


def save_db(db):
    with DB_LOCK:
        try:
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ فشل الحفظ: {e}")


# ==================== نظام المهام ====================
JOBS = {}
JOBS_LOCK = threading.Lock()
PROCESSES = {}


def cleanup_old_jobs():
    now = datetime.now()
    with JOBS_LOCK:
        to_delete = []
        for job_id, job in JOBS.items():
            finished = job.get("finished_at")
            if finished:
                try:
                    age = (now - datetime.fromisoformat(finished)).total_seconds()
                    if age > JOB_RETENTION:
                        to_delete.append(job_id)
                except Exception:
                    pass
        for job_id in to_delete:
            JOBS.pop(job_id, None)
            PROCESSES.pop(job_id, None)


def run_tool(job_id, tool_path, user_args, stdin_input):
    """تشغيل الأداة من مسارها على الخادم"""
    process = None

    try:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "running"
                JOBS[job_id]["started_at"] = datetime.now().isoformat()

        # ✅ تشغيل الأداة مباشرة من مسارها
        process = subprocess.Popen(
            [sys.executable, "-u", tool_path] + [str(a) for a in user_args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        )

        with JOBS_LOCK:
            PROCESSES[job_id] = process

        try:
            stdout, stderr = process.communicate(
                input=stdin_input,
                timeout=MAX_EXECUTION_TIME
            )
            returncode = process.returncode

            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "completed"
                    JOBS[job_id]["result"] = {
                        "stdout": stdout,
                        "stderr": stderr,
                        "returncode": returncode
                    }
                    JOBS[job_id]["finished_at"] = datetime.now().isoformat()

        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "timeout"
                    JOBS[job_id]["result"] = {
                        "error": f"تجاوزت الأداة المهلة ({MAX_EXECUTION_TIME} ثانية)"
                    }
                    JOBS[job_id]["finished_at"] = datetime.now().isoformat()

    except Exception as e:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["result"] = {"error": str(e)}
                JOBS[job_id]["finished_at"] = datetime.now().isoformat()

    finally:
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
        with JOBS_LOCK:
            PROCESSES.pop(job_id, None)
        cleanup_old_jobs()


# ==================== دوال مساعدة ====================

def generate_license_key(tool_id):
    """توليد كود ترخيص عشوائي"""
    random_part = ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(32)
    )
    return f"{tool_id.upper()[:8]}-{random_part}"


def count_inputs_in_code(code_text):
    """اكتشاف عدد input() في الكود"""
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
                        prompt = "أدخل قيمة"
                inputs_found.append(prompt)
    return inputs_found


def generate_client_file(tool_id, license_key, server_url, tool_name=None, inputs_prompts=None):
    """توليد ملف العميل - يحتوي فقط على رابط + ترخيص"""
    tool_name = tool_name or tool_id
    inputs_prompts = inputs_prompts or []
    prompts_repr = repr(inputs_prompts) if inputs_prompts else "[]"

    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  {tool_name} - Client
  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

import requests
import sys
import time

SERVER_URL = "{server_url}"
TOOL_ID = "{tool_id}"
LICENSE_KEY = "{license_key}"
TOOL_NAME = "{tool_name}"
INPUTS_PROMPTS = {prompts_repr}


def print_banner():
    print("=" * 60)
    print(f"  🛠️  {{TOOL_NAME}}")
    print("=" * 60)


def collect_inputs():
    if not INPUTS_PROMPTS:
        return ""
    print(f"\\n📝 الأداة تحتاج {{len(INPUTS_PROMPTS)}} مدخل(ات):")
    print("-" * 60)
    values = []
    for i, prompt in enumerate(INPUTS_PROMPTS, 1):
        clean_prompt = prompt.strip() or f"مدخل #{{i}}"
        try:
            value = input(f"{{i}}. {{clean_prompt}}: ").strip()
        except EOFError:
            value = ""
        values.append(value)
    while True:
        try:
            more = input("\\n➕ مدخل إضافي؟ (Enter للتخطي): ").strip()
        except EOFError:
            break
        if not more:
            break
        values.append(more)
    return "\\n".join(values) + "\\n"


def start_execution(stdin_input=""):
    try:
        response = requests.post(
            f"{{SERVER_URL}}/execute",
            json={{
                "tool_id": TOOL_ID,
                "license_key": LICENSE_KEY,
                "args": [],
                "stdin_input": stdin_input
            }},
            timeout=30
        )
        if response.status_code == 202:
            return response.json().get("job_id")
        else:
            try:
                error = response.json().get("error", "خطأ غير معروف")
            except Exception:
                error = response.text
            print(f"❌ خطأ ({{response.status_code}}): {{error}}")
            return None
    except Exception as e:
        print(f"❌ فشل الاتصال: {{e}}")
        return None


def wait_for_result(job_id):
    last_status = None
    start_time = time.time()
    last_dot = 0

    while True:
        try:
            response = requests.get(
                f"{{SERVER_URL}}/job_status/{{job_id}}",
                timeout=15
            )
            if response.status_code == 404:
                print("\\n❌ المهمة غير موجودة")
                return False

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")

                if status != last_status:
                    if status == "running":
                        print("\\n🔄 بدأ التنفيذ...")
                    last_status = status

                if status == "completed":
                    result = data.get("result", {{}})
                    print("\\n" + "=" * 60)
                    if result.get("stdout"):
                        print(result["stdout"])
                    if result.get("stderr"):
                        print("⚠️ تحذيرات:")
                        print(result["stderr"])
                    return True

                elif status == "timeout":
                    result = data.get("result", {{}})
                    print(f"\\n⏱️ {{result.get('error', 'انتهت المهلة')}}")
                    return False

                elif status == "failed":
                    result = data.get("result", {{}})
                    print(f"\\n❌ {{result.get('error', 'فشل التنفيذ')}}")
                    return False

                elif status == "cancelled":
                    print("\\n🚫 تم الإلغاء")
                    return False

                if status in ("pending", "running"):
                    elapsed = int(time.time() - start_time)
                    if elapsed - last_dot >= 2:
                        sys.stdout.write(f"\\r⏳ جاري التنفيذ... ({{elapsed}}ث)   ")
                        sys.stdout.flush()
                        last_dot = elapsed

            time.sleep(1.5)

        except requests.exceptions.Timeout:
            continue
        except KeyboardInterrupt:
            print("\\n\\n👋 تم الإلغاء")
            sys.exit(0)
        except Exception:
            time.sleep(2)


def main():
    print_banner()
    print(f"📡 الخادم: {{SERVER_URL}}")
    print("-" * 60)

    stdin_input = collect_inputs()

    print(f"\\n📤 إرسال الطلب للخادم...")
    job_id = start_execution(stdin_input)
    if not job_id:
        print("❌ فشل بدء التنفيذ")
        sys.exit(1)

    print(f"🆔 المهمة: {{job_id[:8]}}...")
    print("=" * 60)

    success = wait_for_result(job_id)
    print("\\n" + "=" * 60)
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


def get_server_url(request):
    return request.host_url.rstrip('/')


# ==================== المسارات ====================

@app.route('/')
def home():
    db = load_db()
    with JOBS_LOCK:
        active = sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))
    return jsonify({
        "status": "🟢 الخادم يعمل",
        "tools_count": len(db),
        "active_jobs": active,
        "version": "5.0.0"
    })


@app.route('/admin')
def admin_panel():
    return render_template_string(ADMIN_HTML)


@app.route('/upload_tool', methods=['POST'])
def upload_tool():
    """
    رفع أداة - يُخزَّن الكود كما هو في ملف منفصل.
    """
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        tool_name = data.get('tool_name', tool_id).strip()
        code_text = data.get('code')  # ← كود Python عادي
        dependencies = data.get('dependencies', [])

        if not all([tool_id, code_text]):
            return jsonify({"error": "tool_id و code مطلوبان"}), 400

        # التحقق من أن الكود صالح
        try:
            compile(code_text, '<string>', 'exec')
        except SyntaxError as e:
            return jsonify({"error": f"كود غير صالح: {str(e)}"}), 400

        # اكتشاف الإدخالات
        try:
            detected_inputs = count_inputs_in_code(code_text)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        db = load_db()
        if tool_id in db:
            return jsonify({"error": f"الأداة '{tool_id}' موجودة مسبقاً"}), 409

        # ✅ حفظ الكود في ملف على الخادم
        tool_filename = f"{tool_id}.py"
        tool_path = os.path.join(TOOLS_DIR, tool_filename)

        with open(tool_path, 'w', encoding='utf-8') as f:
            f.write(code_text)

        print(f"✅ تم حفظ الأداة في: {tool_path}")
        print(f"🔍 عدد الإدخالات: {len(detected_inputs)}")

        # توليد ترخيص
        license_key = generate_license_key(tool_id)
        server_url = get_server_url(request)

        # توليد العميل
        client_code = generate_client_file(
            tool_id=tool_id,
            license_key=license_key,
            server_url=server_url,
            tool_name=tool_name,
            inputs_prompts=detected_inputs
        )

        # حفظ في قاعدة البيانات
        db[tool_id] = {
            "tool_id": tool_id,
            "tool_name": tool_name,
            "file_path": tool_path,
            "license_key": license_key,
            "dependencies": dependencies,
            "created_at": datetime.now().isoformat(),
            "executions": 0,
            "max_executions": data.get('max_executions', 0),
            "expires_at": data.get('expires_at', None),
            "inputs_prompts": detected_inputs
        }
        save_db(db)

        return jsonify({
            "status": "success",
            "message": f"✅ تم رفع الأداة '{tool_name}'",
            "tool_id": tool_id,
            "license_key": license_key,
            "file_path": tool_path,
            "inputs_count": len(detected_inputs),
            "inputs_prompts": detected_inputs,
            "client_code": client_code
        }), 201

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/execute', methods=['POST'])
def execute_tool():
    """تنفيذ الأداة من ملفها على الخادم"""
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

        # التحقق من الترخيص
        if tool['license_key'] != license_key:
            return jsonify({"error": "كود الترخيص غير صالح"}), 403

        # التحقق من الانتهاء
        if tool.get('expires_at'):
            if datetime.now() > datetime.fromisoformat(tool['expires_at']):
                return jsonify({"error": "انتهت صلاحية الترخيص"}), 403

        # التحقق من الحد الأقصى
        max_exec = tool.get('max_executions', 0)
        if max_exec > 0 and tool['executions'] >= max_exec:
            return jsonify({"error": "انتهت صلاحية الترخيص"}), 403

        # ✅ التحقق من وجود الملف
        tool_path = tool.get('file_path')
        if not tool_path or not os.path.exists(tool_path):
            return jsonify({"error": "ملف الأداة غير موجود على الخادم"}), 404

        # زيادة العداد
        db[tool_id]['executions'] += 1
        save_db(db)

        # إنشاء مهمة
        job_id = str(uuid.uuid4())
        with JOBS_LOCK:
            JOBS[job_id] = {
                "job_id": job_id,
                "tool_id": tool_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "result": None
            }

        thread = threading.Thread(
            target=run_tool,
            args=(job_id, tool_path, user_args, stdin_input),
            daemon=True
        )
        thread.start()

        return jsonify({
            "status": "started",
            "job_id": job_id
        }), 202

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "المهمة غير موجودة"}), 404
        job = dict(JOBS[job_id])
        result = dict(job["result"]) if job.get("result") else None

    response = {
        "job_id": job_id,
        "tool_id": job["tool_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "finished_at": job.get("finished_at")
    }
    if result:
        response["result"] = result
    return jsonify(response)


@app.route('/job_kill/<job_id>', methods=['POST'])
def job_kill(job_id):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "المهمة غير موجودة"}), 404
        if JOBS[job_id]["status"] not in ("pending", "running"):
            return jsonify({"error": "المهمة انتهت"}), 400

        process = PROCESSES.get(job_id)
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

        JOBS[job_id]["status"] = "cancelled"
        JOBS[job_id]["finished_at"] = datetime.now().isoformat()
        JOBS[job_id]["result"] = {"error": "تم الإلغاء"}

    return jsonify({"status": "success"})


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
        "file_exists": os.path.exists(tool.get('file_path', '')),
        "inputs_count": len(tool.get('inputs_prompts', [])),
        "inputs_prompts": tool.get('inputs_prompts', [])
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
            "inputs_count": len(tool.get('inputs_prompts', [])),
            "file_exists": os.path.exists(tool.get('file_path', ''))
        })

    with JOBS_LOCK:
        jobs_info = {
            "total": len(JOBS),
            "active": sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))
        }

    return jsonify({"tools": tools, "count": len(tools), "jobs": jobs_info})


@app.route('/delete_tool/<tool_id>', methods=['DELETE'])
def delete_tool(tool_id):
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    # حذف الملف
    tool_path = db[tool_id].get('file_path')
    if tool_path and os.path.exists(tool_path):
        try:
            os.unlink(tool_path)
        except Exception:
            pass

    del db[tool_id]
    save_db(db)

    return jsonify({"status": "success"})


# ==================== لوحة التحكم ====================
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
        .stats { display: flex; gap: 20px; flex-wrap: wrap; }
        .stat { background: #0f172a; padding: 15px 25px; border-radius: 8px; }
        .stat-value { font-size: 28px; color: #38bdf8; font-weight: bold; }
        .stat-label { font-size: 13px; color: #94a3b8; margin-top: 5px; }
        button { padding: 10px 20px; border-radius: 8px; background: #38bdf8; color: #0f172a; cursor: pointer; font-weight: bold; border: none; }
        button:hover { background: #0ea5e9; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: right; border-bottom: 1px solid #334155; }
        th { color: #38bdf8; }
        .ok { color: #6ee7b7; }
        .no { color: #fca5a5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ لوحة تحكم الأدوات</h1>
        <div class="card">
            <div class="stats">
                <div class="stat">
                    <div class="stat-value" id="statTools">-</div>
                    <div class="stat-label">الأدوات</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="statJobs">-</div>
                    <div class="stat-label">مهام نشطة</div>
                </div>
            </div>
        </div>
        <div class="card">
            <button onclick="loadTools()">🔄 تحديث</button>
        </div>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>المعرّف</th>
                        <th>الاسم</th>
                        <th>الاستخدامات</th>
                        <th>الإدخالات</th>
                        <th>الملف موجود</th>
                        <th>التاريخ</th>
                    </tr>
                </thead>
                <tbody id="toolsBody"></tbody>
            </table>
        </div>
    </div>
    <script>
        async function loadTools() {
            const res = await fetch('/list_tools');
            const data = await res.json();
            document.getElementById('statTools').textContent = data.count;
            document.getElementById('statJobs').textContent = data.jobs.active;
            const tbody = document.getElementById('toolsBody');
            tbody.innerHTML = '';
            data.tools.forEach(t => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${t.tool_id}</td>
                    <td>${t.tool_name}</td>
                    <td>${t.executions}</td>
                    <td>${t.inputs_count}</td>
                    <td class="${t.file_exists ? 'ok' : 'no'}">${t.file_exists ? '✅' : '❌'}</td>
                    <td>${t.created_at.split('T')[0]}</td>
                `;
                tbody.appendChild(row);
            });
        }
        window.addEventListener('load', loadTools);
    </script>
</body>
</html>
"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
