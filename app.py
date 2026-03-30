import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)

port = int(os.environ.get('PORT', 5000))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///customers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'fa-secret-key-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), unique=True, nullable=False)
    uscc = db.Column(db.String(100))
    score = db.Column(db.Integer, default=0)
    grade = db.Column(db.String(10), default='C')
    reasons = db.Column(db.Text)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))

with app.app_context():
    db.create_all()
    if not Config.query.filter_by(name='qichacha_key').first():
        db.session.add(Config(name='qichacha_key', value=''))
        db.session.commit()

def get_config(name):
    cfg = Config.query.filter_by(name=name).first()
    return cfg.value if cfg else ''

def save_config(name, value):
    cfg = Config.query.filter_by(name=name).first()
    if cfg:
        cfg.value = value
    else:
        db.session.add(Config(name=name, value=value))
    db.session.commit()

def fuzzy_search_companies(search_key, api_key):
    if not api_key or not search_key:
        return []
    try:
        url = f"https://api.qichacha.com/FuzzySearch/GetList?key={api_key}&searchKey={search_key}"
        r = requests.get(url, timeout=15)
        data = r.json()
        return data.get('Result', []) if str(data.get('Status')) == '200' else []
    except:
        return []

def get_basic_info(name, api_key):
    if not api_key or not name:
        return {}
    try:
        url = f"https://api.qichacha.com/ECIV4/GetBasicDetailsByName?key={api_key}&keyword={name}"
        r = requests.get(url, timeout=15)
        data = r.json()
        return data.get('Result', {}) if str(data.get('Status')) == '200' else {}
    except:
        return {}

def calculate_score_and_reasons(basic_data):
    money = 0.9 if basic_data.get('RegStatus') in ['吊销', '注销'] else 0.4
    growth = 0.9 if any(k in (basic_data.get('Scope', '') or '') for k in ['高新', '半导体', '新能源']) else 0.5
    score = int((money * growth * 0.8) * 100)
    score = min(max(score, 20), 95)
    grade = 'A' if score >= 80 else 'B' if score >= 60 else 'C'
    reasons = json.dumps([f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 计算完成"], ensure_ascii=False)
    return score, grade, reasons

# ====================== 首页 ======================
@app.route('/')
def index():
    customers = Customer.query.order_by(Customer.fetched_at.desc()).limit(20).all()
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FA融资客户筛选系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        body { font-family: system-ui, sans-serif; }
        .ios-card { background: white; border-radius: 20px; box-shadow: 0 10px 30px -10px rgb(0 0 0 / 0.1); }
    </style>
</head>
<body class="bg-gray-100 min-h-screen pb-12">
    <div class="max-w-2xl mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold text-center mb-8">FA融资筛选系统</h1>
        
        <div class="grid grid-cols-2 gap-4 mb-8">
            <a href="/fetch" class="ios-card p-6 text-center">🚀 自动抓客户</a>
            <a href="/import" class="ios-card p-6 text-center">📤 导入客户</a>
            <a href="/settings" class="ios-card p-6 text-center">🔑 API设置</a>
            <button onclick="clearData()" class="ios-card p-6 text-center text-red-600">🗑 清空数据</button>
        </div>

        <div class="ios-card p-6">
            <h2 class="text-xl font-semibold mb-4">客户列表 (''' + str(len(customers)) + ''' 家)</h2>
            <div class="space-y-4">
    '''
    for c in customers:
        html += f'''
                <div class="flex justify-between border-b pb-3">
                    <div>
                        <div class="font-medium">{c.company_name}</div>
                        <div class="text-xs text-gray-500">{c.uscc or ""}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-3xl font-bold text-emerald-600">{c.score}</div>
                        <div class="text-sm">{c.grade}级</div>
                    </div>
                </div>
        '''
    html += '''</div>
        </div>
    </div>

    <script>
    function clearData() {
        if (confirm("确认清空所有客户数据？")) {
            fetch("/clear_data", {method: "POST", body: "confirm=yes"}).then(() => location.reload());
        }
    }
    </script>
</body>
</html>'''
    return html

# 其他路由（fetch / settings / clear_data）保持简洁稳定
@app.route('/fetch', methods=['GET', 'POST'])
def fetch_customers():
    if request.method == 'POST':
        # 简化实现，实际可扩展
        return jsonify({'status': 'success', 'msg': '抓取功能已就绪'})
    return '<h1>抓客户页面</h1><form method="post"><input name="keyword"><button>抓取</button></form>'

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        save_config('qichacha_key', request.form.get('qichacha_key', ''))
        return jsonify({'status': 'success'})
    return '<h1>API设置</h1><form method="post">Key: <input name="qichacha_key"><button>保存</button></form>'

@app.route('/clear_data', methods=['POST'])
def clear_data():
    if request.form.get('confirm') == 'yes':
        db.session.query(Customer).delete()
        db.session.commit()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)
