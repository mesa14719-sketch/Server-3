# app.py - النسخة المبسطة النهائية
from flask import Flask, request, jsonify, send_file
import os
import subprocess
import tempfile
import sys
import secrets
import string
import threading
import uuid
import urllib.request
import urllib.error
import json
import time
import hashlib
import ast
import importlib.util
from datetime import datetime
from io import BytesIO

app = Flask(__name__)

# ==================== الإعدادات ====================
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
MAX_EXECUTION_TIME = int(os.environ.get("MAX_EXECUTION_TIME", 600))
SYNC_INTERVAL = 60
JOB_RETENTION = 3600

# ==================== خريطة المكتبات ====================
PIP_NAME_MAP = {
    "telebot": "pyTelegramBotAPI",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "telegram": "python-telegram-bot",
    "discord": "discord.py",
    "dotenv": "python-dotenv",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",
    "OpenSSL": "pyOpenSSL",
    "serial": "pyserial",
    "google": "google-api-python-client",
    "flask": "Flask",
    "django": "Django",
    "pyfiglet": "pyfiglet",
    "socketio": "python-socketio",
    "websocket": "websocket-client",
    "docx": "python-docx",
    "fpdf": "fpdf2",
    "qrcode": "qrcode",
    "barcode": "python-barcode",
    "pygame": "pygame",
    "pyautogui": "PyAutoGUI",
    "pynput": "pynput",
    "pyperclip": "pyperclip",
    "win32com": "pywin32",
    "pythoncom": "pywin32",
    "flask_cors": "Flask-Cors",
    "flask_sqlalchemy": "Flask-SQLAlchemy",
    "flask_login": "Flask-Login",
    "flask_wtf": "Flask-WTF",
    "wtforms": "WTForms",
    "markdown": "Markdown",
    "pygments": "Pygments",
    "openpyxl": "openpyxl",
    "reportlab": "reportlab",
}

# المكتبات المدمجة في Python
BUILTIN_MODULES = set(sys.builtin_module_names) | {
    'os', 'sys', 'time', 'datetime', 'random', 're', 'math', 'hashlib',
    'base64', 'threading', 'subprocess', 'urllib', 'socket', 'ssl',
    'email', 'http', 'xml', 'csv', 'io', 'pathlib', 'typing', 'collections',
    'itertools', 'functools', 'operator', 'string', 'logging', 'warnings',
    'traceback', 'inspect', 'importlib', 'argparse', 'configparser',
    'glob', 'shutil', 'zipfile', 'tarfile', 'gzip', 'pickle', 'copy',
    'pprint', 'textwrap', 'unicodedata', 'uuid', 'tempfile', 'ctypes',
    'multiprocessing', 'asyncio', 'concurrent', 'queue', 'signal',
    'stat', 'platform', 'tkinter', 'sqlite3', 'json', 'struct',
    'binascii', 'secrets', 'enum', 'dataclasses', 'abc', 'contextlib',
    'weakref', 'gc', 'atexit', 'site', 'builtins', '__future__',
    'ast', 'dis', 'tokenize', 'token', 'keyword', 'codecs',
    'locale', 'gettext', 'calendar', 'zoneinfo', 'timeit',
    'array', 'bisect', 'heapq', 'graphlib', 'decimal', 'fractions',
    'numbers', 'cmath', 'statistics', 'mmap',
    'select', 'selectors', 'errno', 'fcntl', 'termios', 'tty',
    'pty', 'pipes', 'posix', 'resource', 'pwd', 'grp', 'crypt'
}


# ==================== قاعدة البيانات ====================
DB_FILE = "tools_db.json"
DB_LOCK = threading.Lock()


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


def run_tool(job_id, code_text, user_args, stdin_input):
    """تشغيل الأداة في الخلفية"""
    process = None
    temp_path = None

    try:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "running"
                JOBS[job_id]["started_at"] = datetime.now().isoformat()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write(code_text)
            temp_path = f.name

        process = subprocess.Popen(
            [sys.executable, "-u", temp_path] + [str(a) for a in user_args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1"
            }
        )

        with JOBS_LOCK:
            PROCESSES[job_id] = process

        try:
            stdout, stderr = process.communicate(
                input=stdin_input or "",
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
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

        with JOBS_LOCK:
            PROCESSES.pop(job_id, None)
        cleanup_old_jobs()


# ==================== اكتشاف المكتبات ====================

def extract_imports(code_text):
    """استخراج المكتبات من الكود"""
    try:
        tree = ast.parse(code_text)
    except SyntaxError as e:
        raise ValueError(f"خطأ في بناء الجملة: {e}")

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])

    pip_packages = []
    for module in imports:
        if module in BUILTIN_MODULES:
            continue
        if module in PIP_NAME_MAP:
            pip_name = PIP_NAME_MAP[module]
            if pip_name:
                pip_packages.append(pip_name)
        else:
            pip_packages.append(module)

    return sorted(set(pip_packages))


def is_package_installed(package_name):
    """التحقق من تثبيت المكتبة"""
    try:
        import_name = package_name
        for import_n, pip_n in PIP_NAME_MAP.items():
            if pip_n == package_name:
                import_name = import_n
                break
        spec = importlib.util.find_spec(import_name)
        return spec is not None
    except Exception:
        return False


def install_package(package_name):
    """تثبيت مكتبة"""
    try:
        if is_package_installed(package_name):
            print(f"   ✅ {package_name} (مثبتة)")
            return True

        print(f"   📦 تثبيت {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", package_name],
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode == 0:
            print(f"   ✅ {package_name}")
            return True
        else:
            print(f"   ⚠️ فشل: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"   ❌ خطأ: {e}")
        return False


def install_dependencies(packages):
    """تثبيت قائمة مكتبات"""
    if not packages:
        return []
    print(f"\n📦 تثبيت {len(packages)} مكتبة:")
    return [{"package": p, "success": install_package(p)} for p in packages]


# ==================== اكتشاف المدخلات ====================

def extract_inputs(code_text):
    """
    اكتشاف كل استدعاءات input() في الكود.
    تُرجع قائمة بالنصوص (prompts).
    """
    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        return []

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
                        # f-string: نحاول استخراج النص الثابت
                        parts = []
                        for v in arg.values:
                            if isinstance(v, ast.Constant):
                                parts.append(str(v.value))
                            else:
                                parts.append("?")
                        prompt = "".join(parts)
                inputs_found.append(prompt)
    return inputs_found


# ==================== دوال مساعدة ====================

def generate_license_key(tool_id):
    random_part = ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(32)
    )
    return f"{tool_id.upper()[:8]}-{random_part}"


def fetch_from_github(url):
    """جلب كود من GitHub"""
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    elif "gist.github.com" in url:
        if not url.endswith("/raw"):
            url = url.rstrip("/") + "/raw"

    try:
        separator = "&" if "?" in url else "?"
        fresh_url = f"{url}{separator}t={int(time.time())}"

        req = urllib.request.Request(
            fresh_url,
            headers={
                "User-Agent": "Mozilla/5.0 ToolServer/11.0",
                "Cache-Control": "no-cache"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        raise ValueError(f"فشل التحميل (HTTP {e.code})")
    except urllib.error.URLError as e:
        raise ValueError(f"فشل الاتصال: {e.reason}")
    except Exception as e:
        raise ValueError(f"خطأ: {str(e)}")


def compute_hash(code_text):
    return hashlib.sha256(code_text.encode('utf-8')).hexdigest()


def generate_client_file(tool_id, license_key, server_url, tool_name=None, inputs_prompts=None):
    """توليد ملف العميل مع المدخلات المكتشفة"""
    tool_name = tool_name or tool_id
    inputs_prompts = inputs_prompts or []
    prompts_repr = repr(inputs_prompts) if inputs_prompts else "[]"

    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  {tool_name} - Client
  تم إنشاؤه: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
============================================================
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


def verify_license():
    print("\\n🔐 جاري جلب الترخيص من السرفر...")
    try:
        response = requests.post(
            f"{{SERVER_URL}}/verify_license",
            json={{"tool_id": TOOL_ID, "license_key": LICENSE_KEY}},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ تم التحقق من الترخيص")
            print(f"🏷️  الأداة: {{data.get('tool_name', TOOL_NAME)}}")
            if data.get('updated_at'):
                print(f"📅 آخر تحديث: {{data['updated_at'][:19]}}")
            return True
        else:
            try:
                error = response.json().get("error", "خطأ غير معروف")
            except Exception:
                error = response.text
            print(f"❌ فشل التحقق: {{error}}")
            return False
    except Exception as e:
        print(f"❌ خطأ: {{e}}")
        return False


def collect_inputs():
    """
    جمع المدخلات من المستخدم بناءً على ما اكتشفه السرفر.
    """
    if not INPUTS_PROMPTS:
        return ""
    
    print(f"\\n📝 الأداة تحتاج {{len(INPUTS_PROMPTS)}} مدخل(ات):")
    print("-" * 60)
    
    values = []
    for i, prompt in enumerate(INPUTS_PROMPTS, 1):
        # تنظيف النص
        clean_prompt = prompt.strip()
        if not clean_prompt:
            clean_prompt = f"مدخل #{{i}}"
        
        try:
            value = input(f"{{i}}. {{clean_prompt}}: ")
        except EOFError:
            value = ""
        values.append(value)
    
    # السماح بإضافة مدخلات إضافية
    print("\\n➕ يمكنك إضافة مدخلات إضافية (Enter على سطر فارغ للانتهاء):")
    while True:
        try:
            more = input(f"مدخل #{{len(values)+1}}: ")
        except EOFError:
            break
        if not more:
            break
        values.append(more)
    
    return "\\n".join(values) + "\\n"


def start_execution(args, stdin_input=""):
    try:
        response = requests.post(
            f"{{SERVER_URL}}/execute",
            json={{
                "tool_id": TOOL_ID,
                "license_key": LICENSE_KEY,
                "args": args,
                "stdin_input": stdin_input
            }},
            timeout=30
        )
        if response.status_code == 202:
            return response.json().get("job_id")
        else:
            try:
                error = response.json().get("error", "خطأ")
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
                elif status in ("timeout", "failed", "cancelled"):
                    result = data.get("result", {{}})
                    print(f"\\n❌ {{result.get('error', 'فشل')}}")
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
    print(f"📡 السرفر: {{SERVER_URL}}")
    print("-" * 60)

    if not verify_license():
        print("\\n❌ فشل التحقق من الترخيص")
        sys.exit(1)

    # جمع المدخلات
    stdin_input = collect_inputs()

    # الوسائط من سطر الأوامر
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    print(f"\\n📤 إرسال الطلب للسرفر...")
    job_id = start_execution(args, stdin_input)
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


# ==================== المزامنة التلقائية ====================
def sync_worker():
    print("🔄 بدأ عامل المزامنة (كل 60 ثانية)")

    while True:
        try:
            time.sleep(SYNC_INTERVAL)

            db = load_db()
            updated = 0

            for tool_id, tool in list(db.items()):
                github_url = tool.get('github_url')
                if not github_url:
                    continue

                try:
                    new_code = fetch_from_github(github_url)
                    new_hash = compute_hash(new_code)
                    old_hash = tool.get('code_hash')

                    if new_hash != old_hash:
                        db[tool_id]['code'] = new_code
                        db[tool_id]['code_hash'] = new_hash
                        db[tool_id]['updated_at'] = datetime.now().isoformat()

                        # إعادة اكتشاف المكتبات
                        try:
                            new_deps = extract_imports(new_code)
                            old_deps = set(tool.get('dependencies', []))
                            new_deps_set = set(new_deps)

                            added = new_deps_set - old_deps
                            if added:
                                print(f"📦 مكتبات جديدة لـ '{tool_id}': {list(added)}")
                                install_dependencies(list(added))

                            db[tool_id]['dependencies'] = new_deps
                        except Exception as e:
                            print(f"⚠️ فشل مكتبات '{tool_id}': {e}")

                        # إعادة اكتشاف المدخلات
                        try:
                            new_inputs = extract_inputs(new_code)
                            db[tool_id]['inputs_prompts'] = new_inputs
                        except Exception as e:
                            print(f"⚠️ فشل مدخلات '{tool_id}': {e}")

                        updated += 1
                        print(f"🔄 تم تحديث '{tool_id}'")

                except Exception as e:
                    print(f"⚠️ فشل تحديث '{tool_id}': {e}")

            if updated > 0:
                save_db(db)
                print(f"✅ تم تحديث {updated} أداة")

        except Exception as e:
            print(f"⚠️ خطأ في المزامنة: {e}")
            time.sleep(10)


def start_sync_worker():
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()
    print("✅ تم تشغيل عامل المزامنة")


# ==================== المسارات ====================

@app.route('/')
def home():
    db = load_db()
    with JOBS_LOCK:
        active = sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))

    return jsonify({
        "status": "🟢 السرفر يعمل",
        "tools_count": len(db),
        "active_jobs": active,
        "sync_interval": SYNC_INTERVAL,
        "version": "11.0.0",
        "features": [
            "auto-detect-dependencies",
            "auto-detect-inputs",
            "auto-install",
            "auto-sync"
        ]
    })


@app.route('/upload_tool', methods=['POST'])
def upload_tool():
    """
    رفع أداة من GitHub - يكتشف المكتبات والمدخلات تلقائياً.
    """
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        tool_name = data.get('tool_name', tool_id).strip()
        github_url = data.get('github_url', '').strip()

        if not all([tool_id, github_url]):
            return jsonify({"error": "tool_id و github_url مطلوبان"}), 400

        # جلب الكود من GitHub
        try:
            code_text = fetch_from_github(github_url)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # التحقق من الكود
        try:
            compile(code_text, '<string>', 'exec')
        except SyntaxError as e:
            return jsonify({"error": f"كود غير صالح: {str(e)}"}), 400

        # ✅ اكتشاف المكتبات
        try:
            detected_deps = extract_imports(code_text)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # ✅ اكتشاف المدخلات
        detected_inputs = extract_inputs(code_text)

        print(f"\n✅ استلمت الأداة '{tool_id}'")
        print(f"🔗 من: {github_url}")
        print(f"📏 الحجم: {len(code_text)} حرف")
        print(f"📦 المكتبات المكتشفة: {len(detected_deps)}")
        for dep in detected_deps:
            print(f"   - {dep}")
        print(f"📥 المدخلات المكتشفة: {len(detected_inputs)}")
        for i, prompt in enumerate(detected_inputs, 1):
            print(f"   {i}. {prompt or '(بدون نص)'}")

        # التحقق من عدم الوجود
        db = load_db()
        if tool_id in db:
            return jsonify({"error": f"الأداة '{tool_id}' موجودة مسبقاً"}), 409

        # ✅ تثبيت المكتبات تلقائياً
        install_results = []
        if detected_deps:
            install_results = install_dependencies(detected_deps)

        # توليد الترخيص
        license_key = generate_license_key(tool_id)
        server_url = get_server_url(request)
        code_hash = compute_hash(code_text)

        client_code = generate_client_file(
            tool_id=tool_id,
            license_key=license_key,
            server_url=server_url,
            tool_name=tool_name,
            inputs_prompts=detected_inputs  # ← تمرير المدخلات
        )

        # تخزين
        db[tool_id] = {
            "tool_id": tool_id,
            "tool_name": tool_name,
            "code": code_text,
            "code_hash": code_hash,
            "license_key": license_key,
            "dependencies": detected_deps,
            "inputs_prompts": detected_inputs,
            "github_url": github_url,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "executions": 0,
            "sync_enabled": True,
            "install_results": install_results
        }
        save_db(db)

        return jsonify({
            "status": "success",
            "message": f"✅ تم رفع '{tool_name}'",
            "tool_id": tool_id,
            "tool_name": tool_name,
            "license_key": license_key,
            "github_url": github_url,
            "code_size": len(code_text),
            "dependencies": detected_deps,
            "dependencies_count": len(detected_deps),
            "inputs_prompts": detected_inputs,
            "inputs_count": len(detected_inputs),
            "install_results": install_results,
            "sync_interval": SYNC_INTERVAL,
            "client_code": client_code
        }), 201

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/verify_license', methods=['POST'])
def verify_license():
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        license_key = data.get('license_key', '').strip()

        if not all([tool_id, license_key]):
            return jsonify({"error": "tool_id و license_key مطلوبان"}), 400

        db = load_db()
        if tool_id not in db:
            return jsonify({"error": "الأداة غير موجودة"}), 404

        tool = db[tool_id]

        if tool['license_key'] != license_key:
            return jsonify({"error": "الترخيص غير صالح"}), 403

        return jsonify({
            "status": "valid",
            "tool_id": tool_id,
            "tool_name": tool['tool_name'],
            "executions": tool['executions'],
            "updated_at": tool.get('updated_at'),
            "dependencies": tool.get('dependencies', []),
            "inputs_prompts": tool.get('inputs_prompts', [])
        })

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/execute', methods=['POST'])
def execute_tool():
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

        if tool['license_key'] != license_key:
            return jsonify({"error": "الترخيص غير صالح"}), 403

        db[tool_id]['executions'] += 1
        save_db(db)

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
            args=(job_id, tool['code'], user_args, stdin_input),
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
        "updated_at": tool.get('updated_at'),
        "executions": tool['executions'],
        "code_size": len(tool.get('code', '')),
        "code_hash": tool.get('code_hash', '')[:16],
        "github_url": tool.get('github_url'),
        "dependencies": tool.get('dependencies', []),
        "inputs_prompts": tool.get('inputs_prompts', [])
    })


@app.route('/manual_sync/<tool_id>', methods=['POST'])
def manual_sync(tool_id):
    """مزامنة يدوية"""
    db = load_db()
    if tool_id not in db:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    tool = db[tool_id]
    github_url = tool.get('github_url')
    if not github_url:
        return jsonify({"error": "لا يوجد رابط GitHub"}), 400

    try:
        new_code = fetch_from_github(github_url)
        new_hash = compute_hash(new_code)

        old_hash = tool.get('code_hash')
        changed = new_hash != old_hash

        new_deps = extract_imports(new_code)
        new_inputs = extract_inputs(new_code)

        if changed:
            db[tool_id]['code'] = new_code
            db[tool_id]['code_hash'] = new_hash
            db[tool_id]['updated_at'] = datetime.now().isoformat()
            db[tool_id]['dependencies'] = new_deps
            db[tool_id]['inputs_prompts'] = new_inputs
            save_db(db)

        return jsonify({
            "status": "success",
            "changed": changed,
            "dependencies": new_deps,
            "inputs_prompts": new_inputs
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
            "updated_at": tool.get('updated_at'),
            "executions": tool['executions'],
            "github_url": tool.get('github_url'),
            "dependencies": tool.get('dependencies', []),
            "inputs_count": len(tool.get('inputs_prompts', []))
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

    del db[tool_id]
    save_db(db)

    return jsonify({"status": "success"})


# ==================== التشغيل ====================
start_sync_worker()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
