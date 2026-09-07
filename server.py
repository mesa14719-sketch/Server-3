from flask import Flask, request, jsonify, send_file
import json
import os
import uuid
from datetime import datetime
import io

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

@app.route('/register', methods=['POST'])
def register():
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
    
    runner_code = f'''import requests, sys
SERVER_URL = "https://server-3-jykw.onrender.com"
TOOL_ID = "{tool_id}"
try:
    r = requests.get(f"{{SERVER_URL}}/run/{{TOOL_ID}}", timeout=10)
    if r.status_code == 200:
        d = r.json()
        h = {{'Authorization': f'token {{d["token"]}}', 'Accept': 'application/vnd.github.v3.raw'}}
        r2 = requests.get(d["url"], headers=h, timeout=10)
        if r2.status_code == 200:
            exec(r2.text)
        else: print(f"❌ فشل: {{r2.status_code}}")
    elif r.status_code == 403: print("❌ موقفة")
    else: print(f"❌ فشل: {{r.status_code}}")
except Exception as e: print(f"❌ {{e}}")'''

    return send_file(
        io.BytesIO(runner_code.encode()),
        mimetype='text/x-python',
        as_attachment=True,
        download_name=f'tool_{tool_id}.py'
    )

@app.route('/run/<tool_id>')
def run_tool(tool_id):
    tools = load_tools()
    if tool_id not in tools: return jsonify({"error": "❌ غير موجود"}), 404
    tool = tools[tool_id]
    if not tool.get("active", True): return jsonify({"error": "❌ موقفة"}), 403
    return jsonify({"token": tool["token"], "url": tool["url"], "name": tool["name"]})

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