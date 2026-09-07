from flask import Flask, request, send_file
import requests
import io
import uuid

app = Flask(__name__)

# Dictionary لتخزين الأدوات المحملة (في الذاكرة، للأغراض التعليمية)
tools = {}

@app.route('/')
def home():
    return '✅ سيرفر الأدوات شغال. استخدم /upload لرفع أداة.'

@app.route('/upload', methods=['POST'])
def upload_tool():
    """استقبال رابط الأداة من GitHub وتخزينها"""
    data = request.json
    tool_url = data.get('url')

    if not tool_url:
        return {"error": "الرابط مطلوب"}, 400

    try:
        # تحميل الأداة من GitHub
        response = requests.get(tool_url, timeout=10)
        if response.status_code != 200:
            return {"error": f"فشل تحميل الأداة من GitHub: {response.status_code}"}, 400

        tool_code = response.text
        tool_id = str(uuid.uuid4())[:8]

        # تخزين الأداة في الذاكرة
        tools[tool_id] = tool_code

        # إنشاء ملف التشغيل (Loader)
        loader_code = f'''
import requests
import sys

SERVER_URL = "https://your-server.onrender.com"  # غيّر هذا لرابط سيرفرك
TOOL_ID = "{tool_id}"

print("📥 جاري جلب الأداة من السيرفر...")
try:
    r = requests.get(f"{{SERVER_URL}}/get_tool/{{TOOL_ID}}", timeout=15)
    if r.status_code == 200:
        print("✅ جاري تشغيل الأداة...")
        exec(r.text)  # تنفيذ الكود المحمّل
    else:
        print(f"❌ فشل جلب الأداة: {{r.status_code}}")
except Exception as e:
    print(f"❌ خطأ: {{e}}")
'''
        # إرسال ملف التشغيل للمطور
        return send_file(
            io.BytesIO(loader_code.encode()),
            mimetype='text/x-python',
            as_attachment=True,
            download_name=f'tool_{tool_id}_loader.py'
        )

    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    """إرجاع كود الأداة المخزنة إلى ملف التشغيل"""
    if tool_id not in tools:
        return {"error": "الأداة غير موجودة"}, 404

    return tools[tool_id]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)