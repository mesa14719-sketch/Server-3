from flask import Flask, request, send_file, jsonify
import requests
import io
import uuid
import json
import os
from datetime import datetime

app = Flask(__name__)
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

@app.route('/')
def home():
    tools = load_tools()
    return f'✅ السيرفر شغال | الأدوات: {len(tools)}'

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    tool_url = data.get('url')
    tool_name = data.get('name', 'أداة')
    
    if not tool_url:
        return jsonify({"error": "الرابط مطلوب"}), 400
    
    try:
        response = requests.get(tool_url, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"فشل التحميل: {response.status_code}"}), 400
        
        tool_id = str(uuid.uuid4())[:8]
        tools = load_tools()
        tools[tool_id] = {
            "name": tool_name,
            "code": response.text,
            "created_at": datetime.now().isoformat(),
            "active": True
        }
        save_tools(tools)
        
        loader = f'''import requests, sys
SERVER_URL = "https://server-3-jykw.onrender.com"
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
    tools = load_tools()
    if tool_id not in tools:
        return jsonify({"error": "غير موجود"}), 404
    if not tools[tool_id].get("active", True):
        return jsonify({"error": "موقفة"}), 403
    return tools[tool_id]["code"]

@app.route('/clean', methods=['POST'])
def clean():
    count = len(load_tools())
    save_tools({})
    return jsonify({"status": "✅ تم التنظيف", "deleted": count})

@app.route('/list')
def list_tools():
    tools = load_tools()
    return jsonify({
        "count": len(tools),
        "tools": [{"id": tid, "name": info["name"], "active": info.get("active", True)} 
                  for tid, info in tools.items()]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
