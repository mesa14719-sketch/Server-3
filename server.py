from flask import Flask, request, jsonify, send_file
import requests
import subprocess
import tempfile
import os
import json
import uuid
import io
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
# 1. رفع الأداة (تتحفظ في السيرفر)
# ============================================
@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    github_url = data.get('url')
    tool_name = data.get('name', 'tool')
    
    if not github_url:
        return jsonify({"error": "الرابط مطلوب"}), 400
    
    try:
        # تحميل الكود من GitHub
        response = requests.get(github_url, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"فشل التحميل: {response.status_code}"}), 400
        
        # حفظ الأداة في السيرفر
        tool_id = str(uuid.uuid4())[:8]
        tools = load_tools()
        tools[tool_id] = {
            "name": tool_name,
            "code": response.text,
            "url": github_url,
            "created_at": datetime.now().isoformat()
        }
        save_tools(tools)
        
        return jsonify({
            "status": "✅ تم الرفع",
            "tool_id": tool_id,
            "name": tool_name
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# 2. تشغيل الأداة (من السيرفر)
# ============================================
@app.route('/run/<tool_id>', methods=['POST'])
def run_tool(tool_id):
    """تشغيل الأداة المخزنة في السيرفر"""
    
    tools = load_tools()
    
    if tool_id not in tools:
        return jsonify({"error": "الأداة غير موجودة"}), 404
    
    code = tools[tool_id]["code"]
    args = request.json or {}
    
    try:
        # حفظ مؤقت للتشغيل
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name
        
        # تشغيل الأداة
        env = os.environ.copy()
        env['TOOL_ARGS'] = json.dumps(args)
        
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        
        # حذف الملف المؤقت
        os.unlink(temp_file)
        
        return jsonify({
            "status": "success",
            "output": result.stdout,
            "error": result.stderr if result.stderr else None
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({"error": "تم تجاوز وقت التنفيذ"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# 3. عرض الأدوات المخزنة
# ============================================
@app.route('/tools')
def list_tools():
    tools = load_tools()
    return jsonify({
        "count": len(tools),
        "tools": [{"id": tid, "name": info["name"]} for tid, info in tools.items()]
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
# 5. الصفحة الرئيسية
# ============================================
@app.route('/')
def home():
    tools = load_tools()
    return f'''
    <h1>🚀 مدير الأدوات</h1>
    <p>عدد الأدوات المخزنة: {len(tools)}</p>
    <ul>
        {''.join(f'<li>{tid} - {info["name"]}</li>' for tid, info in tools.items())}
    </ul>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
