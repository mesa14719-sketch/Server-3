from flask import Flask, request, send_file, jsonify
import requests
import io
import uuid
import json
import os
from datetime import datetime

app = Flask(__name__)
TOOLS_FILE = "tools.json"

# ============================================
# تحميل وحفظ الأدوات
# ============================================
def load_tools():
    try:
        with open(TOOLS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_tools(tools):
    with open(TOOLS_FILE, 'w') as f:
        json.dump(tools, f, indent=2)

# ============================================
# الصفحة الرئيسية
# ============================================
@app.route('/')
def home():
    tools = load_tools()
    return f'✅ السيرفر شغال | الأدوات: {len(tools)}'

# ============================================
# 1. رفع الأداة (يطلب رابط + توكن)
# ============================================
@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    tool_url = data.get('url')
    tool_name = data.get('name', 'أداة')
    github_token = data.get('token', '')
    
    if not tool_url:
        return jsonify({"error": "❌ الرابط مطلوب"}), 400
    
    if not github_token:
        return jsonify({"error": "❌ التوكن مطلوب للمستودع الخاص"}), 400
    
    try:
        # 🔑 استخدام التوكن للوصول للمستودع الخاص
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3.raw"
        }
        
        response = requests.get(tool_url, headers=headers, timeout=10)
        
        if response.status_code == 401:
            return jsonify({"error": "❌ التوكن غير صالح أو منتهي الصلاحية"}), 401
        
        if response.status_code == 404:
            return jsonify({"error": "❌ الملف غير موجود أو المستودع خاص"}), 404
        
        if response.status_code != 200:
            return jsonify({"error": f"❌ فشل التحميل: {response.status_code}"}), 400
        
        # توليد معرف فريد
        tool_id = str(uuid.uuid4())[:8]
        
        # حفظ الأداة في السيرفر
        tools = load_tools()
        tools[tool_id] = {
            "name": tool_name,
            "url": tool_url,
            "code": response.text,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "active": True
        }
        save_tools(tools)
        
        # ============================================
        # إنشاء ملف التشغيل (بدون توكن)
        # ============================================
        loader = f'''import requests
import sys

SERVER_URL = "https://server-3-mzac.onrender.com"
TOOL_ID = "{tool_id}"

def run(data=None):
    try:
        r = requests.post(
            f"{{SERVER_URL}}/run/{{TOOL_ID}}",
            json=data or {{}},
            timeout=60
        )
        if r.status_code == 200:
            result = r.json()
            output = result.get("output", "")
            if output:
                print(output)
        else:
            print(f"❌ فشل: {{r.status_code}}")
    except Exception as e:
        print(f"❌ خطأ: {{e}}")

if __name__ == "__main__":
    run({{}})
'''
        
        return send_file(
            io.BytesIO(loader.encode()),
            mimetype='text/x-python',
            as_attachment=True,
            download_name=f'{tool_name}.py'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# 2. تشغيل الأداة (بدون كود)
# ============================================
@app.route('/run/<tool_id>', methods=['POST'])
def run_tool(tool_id):
    tools = load_tools()
    
    if tool_id not in tools:
        return jsonify({"error": "❌ الأداة غير موجودة"}), 404
    
    tool = tools[tool_id]
    
    if not tool.get('active', True):
        return jsonify({"error": "❌ الأداة موقفة"}), 403
    
    code = tool.get('code', '')
    user_data = request.json or {}
    
    try:
        import subprocess
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name
        
        env = os.environ.copy()
        env['TOOL_ARGS'] = json.dumps(user_data)
        
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        
        os.unlink(temp_file)
        
        return jsonify({
            "status": "success",
            "output": result.stdout,
            "error": result.stderr if result.stderr else None
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({"error": "⏰ تم تجاوز وقت التنفيذ"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# 3. عرض الأدوات
# ============================================
@app.route('/list')
def list_tools():
    tools = load_tools()
    return jsonify({
        "count": len(tools),
        "tools": [{
            "id": tid,
            "name": info["name"],
            "active": info.get("active", True),
            "created_at": info.get("created_at", "غير معروف")
        } for tid, info in tools.items()]
    })

# ============================================
# 4. حذف أداة
# ============================================
@app.route('/delete/<tool_id>', methods=['DELETE'])
def delete_tool(tool_id):
    tools = load_tools()
    if tool_id not in tools:
        return jsonify({"error": "غير موجود"}), 404
    
    del tools[tool_id]
    save_tools(tools)
    return jsonify({"status": "✅ تم الحذف"})

# ============================================
# تشغيل السيرفر
# ============================================
if __name__ == '__main__':
    print("🚀 السيرفر شغال على http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
