# ═══════════════════════════════════════
# 📁 server.py - السيرفر (يرفع على Render)
# ═══════════════════════════════════════

from flask import Flask, request, jsonify
import json
import os
import uuid
from datetime import datetime

app = Flask(__name__)

# ═══════════════════════════════════════
# 📂 ملف تخزين الأدوات
# ═══════════════════════════════════════
TOOLS_FILE = "tools.json"

def load_tools():
    try:
        with open(TOOLS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_tools(tools):
    with open(TOOLS_FILE, 'w') as f:
        json.dump(tools, f, indent=2)

# ═══════════════════════════════════════
# 📌 المسارات
# ═══════════════════════════════════════

@app.route('/')
def home():
    tools = load_tools()
    return f'✅ السيرفر شغال | الأدوات المسجلة: {len(tools)}'

@app.route('/register', methods=['POST'])
def register():
    """تسجيل أداة جديدة"""
    data = request.json
    tool_name = data.get('name')
    github_token = data.get('token')
    repo_url = data.get('url')
    
    if not all([tool_name, github_token, repo_url]):
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400
    
    tool_id = str(uuid.uuid4())[:8]
    
    tools = load_tools()
    tools[tool_id] = {
        "name": tool_name,
        "token": github_token,
        "url": repo_url,
        "created_at": datetime.now().isoformat(),
        "active": True
    }
    save_tools(tools)
    
    # 🔥 إنشاء ملف الأداة الجديد (المحقون)
    runner_code = f'''# ═══════════════════════════════════════
# 📁 tool_{tool_id}.py - أداة {tool_name}
# ═══════════════════════════════════════

import requests
import sys

# 🔗 رابط السيرفر
SERVER_URL = "https://your-server.onrender.com"
TOOL_ID = "{tool_id}"

print("📥 جاري جلب الأداة...")

try:
    response = requests.get(f"{{SERVER_URL}}/run/{{TOOL_ID}}", timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        GITHUB_TOKEN = data["token"]
        REPO_URL = data["url"]
        
        print(f"✅ الأداة: {{data['name']}}")
        
        headers = {{
            'Authorization': f'token {{GITHUB_TOKEN}}',
            'Accept': 'application/vnd.github.v3.raw'
        }}
        
        print("📥 جاري تحميل الأداة...")
        response = requests.get(REPO_URL, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("✅ جاري التشغيل...")
            exec(response.text)
        else:
            print(f"❌ فشل التحميل: {{response.status_code}}")
            
    elif response.status_code == 403:
        print("❌ الأداة موقفة")
    else:
        print(f"❌ فشل: {{response.status_code}}")
        
except Exception as e:
    print(f"❌ خطأ: {{e}}")
'''

    # حفظ الملف الجديد
    tool_filename = f"tool_{tool_id}.py"
    with open(tool_filename, 'w') as f:
        f.write(runner_code)
    
    return jsonify({
        "status": "✅ تم التسجيل",
        "tool_id": tool_id,
        "name": tool_name,
        "file": tool_filename,
        "message": f"تم إنشاء {tool_filename}"
    })

@app.route('/run/<tool_id>')
def run_tool(tool_id):
    """جلب بيانات الأداة"""
    tools = load_tools()
    
    if tool_id not in tools:
        return jsonify({"error": "❌ غير موجودة"}), 404
    
    tool = tools[tool_id]
    
    if not tool.get("active", True):
        return jsonify({"error": "❌ موقفة"}), 403
    
    return jsonify({
        "token": tool["token"],
        "url": tool["url"],
        "name": tool["name"]
    })

@app.route('/disable/<tool_id>', methods=['POST'])
def disable_tool(tool_id):
    tools = load_tools()
    if tool_id in tools:
        tools[tool_id]["active"] = False
        save_tools(tools)
        return jsonify({"status": f"✅ تم إيقاف {tool_id}"})
    return jsonify({"error": "غير موجود"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)