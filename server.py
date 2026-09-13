# app.py - نسخة كاملة مع البث المباشر
from flask import Flask, request, jsonify, send_file
import os
import subprocess
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


# ==================== التخزين في RAM ====================
TOOLS_RAM = {}
RAM_LOCK = threading.Lock()


def get_tools():
    with RAM_LOCK:
        return dict(TOOLS_RAM)


def get_tool(tool_id):
    with RAM_LOCK:
        tool = TOOLS_RAM.get(tool_id)
        return dict(tool) if tool else None


def save_tool(tool_id, tool_data):
    with RAM_LOCK:
        TOOLS_RAM[tool_id] = tool_data


def delete_tool(tool_id):
    with RAM_LOCK:
        return TOOLS_RAM.pop(tool_id, None)


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
    """تشغيل الأداة مع البث المباشر للإخراج"""
    process = None

    try:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "running"
                JOBS[job_id]["started_at"] = datetime.now().isoformat()
                JOBS[job_id]["output_lines"] = []

        # ✅ تشغيل بدون ملف مؤقت (python -c)
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", code_text] + [str(a) for a in user_args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1"
            }
        )

        with JOBS_LOCK:
            PROCESSES[job_id] = process

        # كتابة stdin
        if stdin_input:
            try:
                process.stdin.write(stdin_input)
                process.stdin.flush()
                process.stdin.close()
            except Exception:
                pass

        output_buffer = []
        start_time = time.time()

        # ✅ قراءة الإخراج سطراً بسطر (Live)
        for line in iter(process.stdout.readline, ''):
            if not line:
                break

            # فحص المهلة
            if time.time() - start_time > MAX_EXECUTION_TIME:
                process.kill()
                break

            output_buffer.append(line)
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["output_lines"].append(line)

        process.wait(timeout=30)
        returncode = process.returncode

        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "completed"
                JOBS[job_id]["result"] = {
                    "stdout": "".join(output_buffer),
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
                JOBS[job_id]["result"] = {"error": f"تجاوزت المهلة ({MAX_EXECUTION_TIME}ث)"}
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


# ==================== اكتشاف المكتبات ====================

def extract_imports(code_text):
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
    try:
        if is_package_installed(package_name):
            print(f"   ✅ {package_name}")
            return True
        print(f"   📦 تثبيت {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", package_name],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            print(f"   ✅ {package_name}")
            return True
        return False
    except Exception as e:
        print(f"   ❌ {e}")
        return False


def install_dependencies(packages):
    if not packages:
        return []
    print(f"\n📦 تثبيت {len(packages)} مكتبة:")
    return [{"package": p, "success": install_package(p)} for p in packages]


# ==================== اكتشاف المدخلات ====================

def extract_inputs(code_text):
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
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    elif "gist.github.com" in url and not url.endswith("/raw"):
        url = url.rstrip("/") + "/raw"

    try:
        separator = "&" if "?" in url else "?"
        fresh_url = f"{url}{separator}t={int(time.time())}"
        req = urllib.request.Request(
            fresh_url,
            headers={"User-Agent": "Mozilla/5.0 ToolServer/12.0", "Cache-Control": "no-cache"}
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
    if not INPUTS_PROMPTS:
        return ""
    print(f"\\n📝 الأداة تحتاج {{len(INPUTS_PROMPTS)}} مدخل(ات):")
    print("-" * 60)
    values = []
    for i, prompt in enumerate(INPUTS_PROMPTS, 1):
        clean_prompt = prompt.strip() or f"مدخل #{{i}}"
        try:
            value = input(f"{{i}}. {{clean_prompt}}: ")
        except EOFError:
            value = ""
        values.append(value)
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


def stream_output(job_id):
    """عرض الإخراج لحظياً"""
    since = 0
    start_time = time.time()
    print()
    print("=" * 60)

    while True:
        try:
            response = requests.get(
                f"{{SERVER_URL}}/job_status/{{job_id}}?since={{since}}",
                timeout=15
            )
            if response.status_code == 404:
                print("\\n❌ المهمة غير موجودة")
                return False

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                new_lines = data.get("new_lines", [])

                for line in new_lines:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                since = data.get("total_lines", since)

                if status == "completed":
                    print()
                    print("=" * 60)
                    return True
                elif status in ("timeout", "failed", "cancelled"):
                    result = data.get("result", {{}})
                    print(f"\\n❌ {{result.get('error', 'فشل')}}")
                    return False

                if status in ("pending", "running"):
                    elapsed = int(time.time() - start_time)
                    if elapsed > 0 and elapsed % 5 == 0 and not new_lines:
                        sys.stdout.write(f"\\r⏳ جاري التنفيذ... ({{elapsed}}ث)   ")
                        sys.stdout.flush()

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

    stdin_input = collect_inputs()
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    print(f"\\n📤 إرسال الطلب للسرفر...")
    job_id = start_execution(args, stdin_input)
    if not job_id:
        print("❌ فشل بدء التنفيذ")
        sys.exit(1)

    success = stream_output(job_id)
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


# ==================== المزامنة ====================
def sync_worker():
    print("🔄 بدأ عامل المزامنة (RAM فقط)")
    while True:
        try:
            time.sleep(SYNC_INTERVAL)

            with RAM_LOCK:
                tools_snapshot = dict(TOOLS_RAM)

            updated = 0
            for tool_id, tool in tools_snapshot.items():
                url = tool.get('github_url')
                if not url:
                    continue
                try:
                    new_code = fetch_from_github(url)
                    new_hash = compute_hash(new_code)
                    if new_hash != tool.get('code_hash'):
                        with RAM_LOCK:
                            if tool_id in TOOLS_RAM:
                                TOOLS_RAM[tool_id]['code'] = new_code
                                TOOLS_RAM[tool_id]['code_hash'] = new_hash
                                TOOLS_RAM[tool_id]['updated_at'] = datetime.now().isoformat()
                                try:
                                    TOOLS_RAM[tool_id]['dependencies'] = extract_imports(new_code)
                                except Exception:
                                    pass
                                try:
                                    TOOLS_RAM[tool_id]['inputs_prompts'] = extract_inputs(new_code)
                                except Exception:
                                    pass
                        updated += 1
                        print(f"🔄 تم تحديث '{tool_id}'")
                except Exception as e:
                    print(f"⚠️ {tool_id}: {e}")

            if updated:
                print(f"✅ تم تحديث {updated} أداة")
        except Exception as e:
            print(f"⚠️ مزامنة: {e}")
            time.sleep(10)


def start_sync_worker():
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()
    print("✅ تم تشغيل عامل المزامنة")


# ==================== المسارات ====================

@app.route('/')
def home():
    with RAM_LOCK:
        count = len(TOOLS_RAM)
    with JOBS_LOCK:
        active = sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))
    return jsonify({
        "status": "🟢 السرفر يعمل",
        "storage": "RAM only",
        "tools_count": count,
        "active_jobs": active,
        "sync_interval": SYNC_INTERVAL,
        "version": "12.0.0"
    })


@app.route('/upload_tool', methods=['POST'])
def upload_tool():
    try:
        data = request.get_json()
        tool_id = data.get('tool_id', '').strip()
        tool_name = data.get('tool_name', tool_id).strip()
        github_url = data.get('github_url', '').strip()

        if not all([tool_id, github_url]):
            return jsonify({"error": "tool_id و github_url مطلوبان"}), 400

        try:
            code_text = fetch_from_github(github_url)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        try:
            compile(code_text, '<string>', 'exec')
        except SyntaxError as e:
            return jsonify({"error": f"كود غير صالح: {str(e)}"}), 400

        try:
            detected_deps = extract_imports(code_text)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        detected_inputs = extract_inputs(code_text)

        print(f"\n✅ استلمت الأداة '{tool_id}'")
        print(f"📦 المكتبات: {len(detected_deps)}")
        print(f"📥 المدخلات: {len(detected_inputs)}")

        if get_tool(tool_id):
            return jsonify({"error": f"الأداة '{tool_id}' موجودة مسبقاً"}), 409

        install_results = []
        if detected_deps:
            install_results = install_dependencies(detected_deps)

        license_key = generate_license_key(tool_id)
        server_url = get_server_url(request)
        code_hash = compute_hash(code_text)

        client_code = generate_client_file(
            tool_id=tool_id,
            license_key=license_key,
            server_url=server_url,
            tool_name=tool_name,
            inputs_prompts=detected_inputs
        )

        save_tool(tool_id, {
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
            "install_results": install_results
        })

        print(f"💾 تم التخزين في RAM")

        return jsonify({
            "status": "success",
            "message": f"✅ تم رفع '{tool_name}'",
            "tool_id": tool_id,
            "tool_name": tool_name,
            "license_key": license_key,
            "github_url": github_url,
            "code_size": len(code_text),
            "dependencies": detected_deps,
            "inputs_prompts": detected_inputs,
            "inputs_count": len(detected_inputs),
            "storage": "RAM only",
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
            return jsonify({"error": "بيانات ناقصة"}), 400

        tool = get_tool(tool_id)
        if not tool:
            return jsonify({"error": "الأداة غير موجودة"}), 404

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
            return jsonify({"error": "بيانات ناقصة"}), 400

        tool = get_tool(tool_id)
        if not tool:
            return jsonify({"error": "الأداة غير موجودة"}), 404

        if tool['license_key'] != license_key:
            return jsonify({"error": "الترخيص غير صالح"}), 403

        with RAM_LOCK:
            if tool_id in TOOLS_RAM:
                TOOLS_RAM[tool_id]['executions'] += 1

        job_id = str(uuid.uuid4())
        with JOBS_LOCK:
            JOBS[job_id] = {
                "job_id": job_id,
                "tool_id": tool_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "result": None,
                "output_lines": []
            }

        thread = threading.Thread(
            target=run_tool,
            args=(job_id, tool['code'], user_args, stdin_input),
            daemon=True
        )
        thread.start()

        return jsonify({"status": "started", "job_id": job_id}), 202

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500


@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    since = int(request.args.get('since', 0))

    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "المهمة غير موجودة"}), 404
        job = dict(JOBS[job_id])
        output_lines = list(job.get("output_lines", []))
        result = dict(job["result"]) if job.get("result") else None

    new_lines = output_lines[since:]

    response = {
        "job_id": job_id,
        "tool_id": job["tool_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "finished_at": job.get("finished_at"),
        "new_lines": new_lines,
        "total_lines": len(output_lines),
        "since": since
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
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    return jsonify({
        "tool_id": tool['tool_id'],
        "tool_name": tool['tool_name'],
        "created_at": tool['created_at'],
        "updated_at": tool.get('updated_at'),
        "executions": tool['executions'],
        "code_size": len(tool.get('code', '')),
        "github_url": tool.get('github_url'),
        "dependencies": tool.get('dependencies', []),
        "inputs_prompts": tool.get('inputs_prompts', []),
        "storage": "RAM only"
    })


@app.route('/list_tools', methods=['GET'])
def list_tools():
    with RAM_LOCK:
        tools_data = dict(TOOLS_RAM)

    tools = [{
        "tool_id": t['tool_id'],
        "tool_name": t['tool_name'],
        "created_at": t['created_at'],
        "updated_at": t.get('updated_at'),
        "executions": t['executions'],
        "github_url": t.get('github_url'),
        "dependencies": t.get('dependencies', []),
        "inputs_count": len(t.get('inputs_prompts', []))
    } for t in tools_data.values()]

    with JOBS_LOCK:
        jobs_info = {
            "total": len(JOBS),
            "active": sum(1 for j in JOBS.values() if j["status"] in ("pending", "running"))
        }

    return jsonify({
        "tools": tools,
        "count": len(tools),
        "jobs": jobs_info,
        "storage": "RAM only"
    })


@app.route('/delete_tool/<tool_id>', methods=['DELETE'])
def delete_tool_endpoint(tool_id):
    deleted = delete_tool(tool_id)
    if not deleted:
        return jsonify({"error": "الأداة غير موجودة"}), 404
    return jsonify({"status": "success", "message": f"تم حذف '{tool_id}'"})


@app.route('/manual_sync/<tool_id>', methods=['POST'])
def manual_sync(tool_id):
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({"error": "الأداة غير موجودة"}), 404

    github_url = tool.get('github_url')
    if not github_url:
        return jsonify({"error": "لا يوجد رابط GitHub"}), 400

    try:
        new_code = fetch_from_github(github_url)
        new_hash = compute_hash(new_code)
        changed = new_hash != tool.get('code_hash')
        new_inputs = extract_inputs(new_code)

        if changed:
            with RAM_LOCK:
                if tool_id in TOOLS_RAM:
                    TOOLS_RAM[tool_id]['code'] = new_code
                    TOOLS_RAM[tool_id]['code_hash'] = new_hash
                    TOOLS_RAM[tool_id]['updated_at'] = datetime.now().isoformat()
                    TOOLS_RAM[tool_id]['inputs_prompts'] = new_inputs

        return jsonify({
            "status": "success",
            "changed": changed,
            "inputs_prompts": new_inputs
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download_client/<tool_id>', methods=['GET'])
def download_client(tool_id):
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({"error": "الأداة غير موجودة"}), 404

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


# ==================== التشغيل ====================
start_sync_worker()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
