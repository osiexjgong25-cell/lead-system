import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
import requests
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Railway 优化：正确读取 PORT
port = int(os.environ.get('PORT', 5000))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///customers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'fa-secret-key-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ====================== 数据库模型 ======================
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), unique=True, nullable=False)
    uscc = db.Column(db.String(100))
    score = db.Column(db.Integer, default=0)
    grade = db.Column(db.String(10), default='C')
    reasons = db.Column(db.Text)
    news_count = db.Column(db.Integer, default=0)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))

# 安全初始化数据库
with app.app_context():
    try:
        db.create_all()
        for key_name in ['qichacha_key', 'kaidanguo_key', 'news_key']:
            if not Config.query.filter_by(name=key_name).first():
                db.session.add(Config(name=key_name, value=''))
        db.session.commit()
    except Exception:
        pass  # 防止初始化失败导致崩溃

# ====================== 配置工具 ======================
def get_config(name):
    try:
        cfg = Config.query.filter_by(name=name).first()
        return cfg.value if cfg else ''
    except:
        return ''

def save_config(name, value):
    try:
        cfg = Config.query.filter_by(name=name).first()
        if cfg:
            cfg.value = value
        else:
            db.session.add(Config(name=name, value=value))
        db.session.commit()
    except:
        pass

# ====================== API 函数（加强防崩） ======================
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

def calculate_score_and_reasons(basic_data, news_count=0):
    try:
        money_pressure = 0.9 if basic_data.get('RegStatus') in ['吊销', '注销'] else 0.4
        growth = 0.9 if any(kw in (basic_data.get('Scope', '') or '') for kw in ['高新', '半导体', '新能源', '专精特新']) else 0.5
        score = int((money_pressure * growth * 0.8) * 100)
        score = min(max(score, 15), 95)
        grade = 'A' if score >= 80 else 'B' if score >= 60 else 'C'
        reasons = json.dumps([
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 评分计算完成",
            f"资金压力: {'强' if money_pressure > 0.7 else '中'}",
            f"成长信号: {'强' if growth > 0.7 else '中'}",
            f"新闻信号: {news_count} 条"
        ], ensure_ascii=False)
        return score, grade, reasons, news_count
    except:
        return 50, 'C', json.dumps(["[系统] 评分计算异常，使用默认值"]), 0

# ====================== 首页（完整 iOS 风格） ======================
@app.route('/')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        customers = Customer.query.order_by(Customer.fetched_at.desc()).paginate(page=page, per_page=10, error_out=False)
    except:
        customers = type('obj', (object,), {'items': [], 'total': 0, 'has_prev': False, 'has_next': False, 'page': 1, 'pages': 1})()

    html = f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FA融资客户筛选系统</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600&display=swap');
            body {{ font-family: 'SF Pro Display', system-ui, sans-serif; }}
            .ios-card {{ background: white; border-radius: 20px; box-shadow: 0 10px 30px -10px rgb(0 0 0 / 0.1); }}
        </style>
    </head>
    <body class="bg-gray-100 min-h-screen pb-12">
        <div class="max-w-2xl mx-auto px-4">
            <div class="flex items-center justify-between py-8">
                <h1 class="text-3xl font-semibold text-gray-900">FA融资筛选</h1>
                <div class="flex items-center gap-2 text-emerald-600">
                    <i class="fas fa-circle text-xs animate-pulse"></i>
                    <span class="text-sm font-medium">稳定运行</span>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4 mb-8">
                <a href="/fetch" class="ios-card p-6 flex flex-col items-center justify-center text-center hover:scale-105 transition">
                    <i class="fas fa-cloud-download-alt text-4xl text-blue-500 mb-3"></i>
                    <h3 class="font-semibold text-lg">🚀 自动抓客户</h3>
                </a>
                <a href="/import" class="ios-card p-6 flex flex-col items-center justify-center text-center hover:scale-105 transition">
                    <i class="fas fa-file-import text-4xl text-purple-500 mb-3"></i>
                    <h3 class="font-semibold text-lg">📤 导入客户</h3>
                </a>
                <a href="/settings" class="ios-card p-6 flex flex-col items-center justify-center text-center hover:scale-105 transition">
                    <i class="fas fa-cog text-4xl text-amber-500 mb-3"></i>
                    <h3 class="font-semibold text-lg">🔑 API设置</h3>
                </a>
                <button onclick="clearData()" class="ios-card p-6 flex flex-col items-center justify-center text-center hover:scale-105 transition border-2 border-red-200 hover:border-red-300">
                    <i class="fas fa-trash-alt text-4xl text-red-500 mb-3"></i>
                    <h3 class="font-semibold text-lg text-red-600">🗑 清空客户数据</h3>
                </button>
            </div>

            <div class="ios-card p-6">
                <h2 class="text-xl font-semibold mb-4">客户列表 ({customers.total} 家)</h2>
                <div class="space-y-4">
                    {''.join(f'''
                    <div class="flex justify-between items-center border-b pb-4 last:border-none">
                        <div class="flex-1">
                            <div class="font-medium">{c.company_name}</div>
                            <div class="text-xs text-gray-500">{c.uscc or '无信用代码'}</div>
                        </div>
                        <div class="text-right">
                            <div class="text-3xl font-bold {'text-emerald-500' if c.score >= 80 else 'text-amber-500' if c.score >= 60 else 'text-gray-400'}">{c.score}</div>
                            <div class="text-xs font-medium {'text-emerald-600' if c.grade == 'A' else 'text-amber-600'}">{c.grade}级</div>
                        </div>
                    </div>
                    ''') for c in customers.items}
                </div>
            </div>
        </div>

        <script>
        function clearData() {{
            if (confirm('⚠️ 确认清空所有客户数据？此操作不可恢复！')) {{
                fetch('/clear_data', {{method: 'POST', body: 'confirm=yes'}})
                .then(() => location.reload());
            }}
        }}
        </script>
    </body>
    </html>
    '''
    return render_template_string(html)

# ====================== 其他路由（简洁稳定版） ======================
@app.route('/fetch', methods=['GET', 'POST'])
def fetch_customers():
    if request.method == 'POST':
        try:
            keyword = request.form.get('keyword', '').strip()
            qcc_key = get_config('qichacha_key')
            if not qcc_key:
                return jsonify({'status': 'error', 'msg': '请先设置企查查 Key'})
            new_count = 0
            results = fuzzy_search_companies(keyword, qcc_key)
            for item in results[:20]:  # 限制数量防滥用
                name = item.get('Name') or ''
                if not name or Customer.query.filter_by(company_name=name).first():
                    continue
                basic = get_basic_info(name, qcc_key)
                score, grade, reasons, news_count = calculate_score_and_reasons(basic)
                cust = Customer(company_name=name, uscc=basic.get('CreditNo'), score=score, grade=grade, reasons=reasons, news_count=news_count)
                db.session.add(cust)
                new_count += 1
            db.session.commit()
            return jsonify({'status': 'success', 'msg': f'成功新增 {new_count} 家客户'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': '抓取过程中发生错误'})
    return render_template_string('''
    <h1 class="text-2xl font-semibold text-center mt-10">🚀 自动抓客户</h1>
    <form method="post" class="max-w-md mx-auto mt-8 p-6 ios-card">
        <input type="text" name="keyword" placeholder="输入关键词（如：半导体）" class="w-full p-4 rounded-3xl border mb-4" required>
        <button type="submit" class="w-full bg-blue-600 text-white py-4 rounded-3xl font-medium">开始抓取</button>
    </form>
    ''')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        try:
            save_config('qichacha_key', request.form.get('qichacha_key', ''))
            return jsonify({'status': 'success', 'msg': 'Key 已保存'})
        except:
            return jsonify({'status': 'error', 'msg': '保存失败'})
    return render_template_string(f'''
    <h1 class="text-2xl font-semibold text-center mt-10">🔑 API设置</h1>
    <div class="max-w-md mx-auto mt-8 p-6 ios-card">
        <form method="post">
            <input type="text" name="qichacha_key" value="{get_config('qichacha_key')}" placeholder="请输入企查查 Key" class="w-full p-4 rounded-3xl border mb-6">
            <button type="submit" class="w-full bg-amber-500 text-white py-4 rounded-3xl font-medium">保存</button>
        </form>
    </div>
    ''')

@app.route('/clear_data', methods=['POST'])
def clear_data():
    if request.form.get('confirm') == 'yes':
        try:
            db.session.query(Customer).delete()
            db.session.commit()
            return jsonify({'status': 'success'})
        except:
            return jsonify({'status': 'error'})
    return jsonify({'status': 'error'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)
