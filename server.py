from flask import Flask, request, send_file
import requests
import io
import uuid

app = Flask(__name__)
tools = {}

@app.route('/')
def home():
    return '✅ سيرفر الأدوات شغال'

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    tool_url = data.get('url')
    
    if not tool_url:
        return {"error": "الرابط مطلوب"}, 400
    
    try:
        response = requests.get(tool_url, timeout=10)
        if response.status_code != 200:
            return {"error": f"فشل التحميل: {response.status_code}"}, 400
        
        tool_id = str(uuid.uuid4())[:8]
        tools[tool_id] = response.text
        
        loader = f'''
import requests, sys
SERVER_URL = "https://server-3-jykw.onrender.com"
TOOL_ID = "{tool_id}"
try:
    r = requests.get(f"{{SERVER_URL}}/get/{{TOOL_ID}}", timeout=10)
    if r.status_code == 200:
        exec(r.text)
    else: print(f"❌ فشل: {{r.status_code}}")
except Exception as e: print(f"❌ {{e}}")
'''
        return send_file(
            io.BytesIO(loader.encode()),
            mimetype='text/x-python',
            as_attachment=True,
            download_name=f'tool_{tool_id}.py'
        )
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/get/<tool_id>')
def get(tool_id):
    if tool_id not in tools:
        return {"error": "غير موجود"}, 404
    return tools[tool_id]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
