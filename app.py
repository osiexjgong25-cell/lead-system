import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
import requests
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
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
    news_count = db.Column(db.Integer, default=0)   # 新增：企业新闻数量
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))

# 初始化
with app.app_context():
    db.create_all()
    for key_name in ['qichacha_key', 'kaidanguo_key', 'news_key']:
        if not Config.query.filter_by(name=key_name).first():
            db.session.add(Config(name=key_name, value=''))
    db.session.commit()

# ====================== 配置工具 ======================
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

# ====================== API 函数（全部加了防崩保护） ======================
def fuzzy_search_companies(search_key, api_key):  # 企查查
    if not api_key:
        return []
    url = f"https://api.qichacha.com/FuzzySearch/GetList?key={api_key}&searchKey={search_key}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        return data.get('Result', []) if str(data.get('Status')) == '200' else []
    except:
        return []

def get_basic_info(name, api_key):  # 企查查工商信息
    if not api_key:
        return {}
    url = f"https://api.qichacha.com/ECIV4/GetBasicDetailsByName?key={api_key}&keyword={name}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        return data.get('Result', {}) if str(data.get('Status')) == '200' else {}
    except:
        return {}

def search_kaidanguo(keyword, api_key):  # 开单果（请替换为您的真实接口）
    if not api_key:
        return []
    # TODO: 替换为开单果官方接口地址和参数
    url = f"https://api.kaidanguo.com/search?key={api_key}&keyword={keyword}&page=1"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        return data.get('data', []) if data.get('code') == 200 else []
    except:
        return []

def fetch_company_news(company_name, news_api_key):  # 企业新闻
    if not news_api_key:
        return 0, []
    # TODO: 替换为您的真实新闻API（支持近90天融资新闻）
    url = f"https://api.example-news.com/search?key={news_api_key}&q={company_name} 融资 OR 投资 OR 扩张&days=90"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        news_list = data.get('articles', [])[:5]
        return len(news_list), [n.get('title') for n in news_list]
    except:
        return 0, []

def calculate_score_and_reasons(basic_data, news_count=0, news_titles=None):
    """升级版评分模型：加入新闻信号"""
    money_pressure = 0.9 if basic_data.get('RegStatus') in ['吊销', '注销'] else 0.4
    project_signal = 0.8 if any(kw in (basic_data.get('Scope', '') or '') for kw in ['工程', '科技']) else 0.5
    growth = 0.9 if any(kw in (basic_data.get('Scope', '') or '') for kw in ['高新', '半导体', '新能源', '专精特新']) else 0.5
    news_signal = min(news_count * 0.15, 0.9)

    score = int((money_pressure * project_signal * growth * (1 + news_signal)) * 100)
    score = min(max(score, 15), 98)
    grade = 'A' if score >= 80 else 'B' if score >= 60 else 'C'

    reasons_list = [
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 工商信息获取成功",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 资金压力: {'强' if money_pressure > 0.7 else '中'}",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 项目/成长信号: {'强' if growth > 0.7 else '中'}",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 新闻信号: 近90天 {news_count} 条融资/扩张新闻"
    ]
    if news_titles:
        reasons_list.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 关键新闻: {', '.join(news_titles[:2])}")

    return score, grade, json.dumps(reasons_list, ensure_ascii=False), news_count

# ====================== 路由 ======================
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    customers = Customer.query.order_by(Customer.fetched_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

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
                    <h3 class="font-semibold text-lg text-red-600">🗑 清空所有客户数据</h3>
                </button>
            </div>

            <div class="ios-card p-6">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-semibold">客户列表 ({customers.total} 家)</h2>
                    <a href="/customers" class="text-blue-600 text-sm font-medium flex items-center gap-1">全部 <i class="fas fa-arrow-right"></i></a>
                </div>
                
                <div class="space-y-4">
                    {''.join(f'''
                    <div class="flex justify-between items-center border-b pb-4 last:border-none">
                        <div class="flex-1">
                            <div class="font-medium">{c.company_name}</div>
                            <div class="text-xs text-gray-500 flex items-center gap-2">
                                {c.uscc or '无信用代码'}
                                {f'<span class="bg-blue-100 text-blue-600 px-2 py-0.5 rounded-2xl text-[10px] ml-2">📰 {c.news_count}</span>' if c.news_count > 0 else ''}
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-3xl font-bold {'text-emerald-500' if c.score >= 80 else 'text-amber-500' if c.score >= 60 else 'text-gray-400'}">{c.score}</div>
                            <div class="text-xs font-medium {'text-emerald-600' if c.grade == 'A' else 'text-amber-600'}">{c.grade}级</div>
                        </div>
                    </div>
                    ''') for c in customers.items}
                </div>

                <div class="flex justify-center gap-4 mt-6 text-sm">
                    {f'<a href="?page={customers.prev_num}" class="px-4 py-2 bg-white rounded-3xl shadow">上一页</a>' if customers.has_prev else ''}
                    <span class="px-4 py-2">第 {customers.page} / {customers.pages} 页</span>
                    {f'<a href="?page={customers.next_num}" class="px-4 py-2 bg-white rounded-3xl shadow">下一页</a>' if customers.has_next else ''}
                </div>
            </div>
        </div>

        <script>
        function clearData() {{
            if (confirm('⚠️ 确认清空所有客户数据？\\n此操作不可恢复！\\nAPI配置将保留。')) {{
                fetch('/clear_data', {{ method: 'POST', headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }}, body: 'confirm=yes' }})
                .then(res => res.json())
                .then(data => {{
                    if (data.status === 'success') {{
                        alert('✅ 已清空！');
                        location.reload();
                    }}
                }});
            }}
        }}
        </script>
    </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/fetch', methods=['GET', 'POST'])
def fetch_customers():
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip()
        pages = int(request.form.get('pages', 3))
        
        qcc_key = get_config('qichacha_key')
        kd_key = get_config('kaidanguo_key')
        news_key = get_config('news_key')

        if not qcc_key and not kd_key:
            return jsonify({'status': 'error', 'msg': '请至少设置一个企业查询API Key'})

        new_count = 0
        for _ in range(pages):
            # 优先企查查，失败自动降级到开单果
            results = fuzzy_search_companies(keyword, qcc_key)
            if not results and kd_key:
                results = search_kaidanguo(keyword, kd_key)

            for item in results:
                name = item.get('Name') or item.get('company_name') or ''
                if not name or Customer.query.filter_by(company_name=name).first():
                    continue

                basic = get_basic_info(name, qcc_key) if qcc_key else {}
                news_count, news_titles = fetch_company_news(name, news_key)

                score, grade, reasons, _ = calculate_score_and_reasons(basic, news_count, news_titles)

                cust = Customer(
                    company_name=name,
                    uscc=item.get('CreditNo'),
                    score=score,
                    grade=grade,
                    reasons=reasons,
                    news_count=news_count
                )
                db.session.add(cust)
                new_count += 1

        db.session.commit()
        return jsonify({'status': 'success', 'msg': f'成功新增 {new_count} 家客户（含新闻信号）'})

    # GET 页面
    return render_template_string('''
    <h1 class="text-2xl font-semibold text-center mt-10">🚀 自动抓客户</h1>
    <form method="post" class="max-w-md mx-auto mt-8 p-6 ios-card">
        <input type="text" name="keyword" placeholder="输入行业/关键词（如：半导体 高新）" class="w-full p-4 rounded-3xl border mb-4" required>
        <input type="number" name="pages" value="3" min="1" class="w-full p-4 rounded-3xl border mb-6">
        <button type="submit" class="w-full bg-blue-600 text-white py-4 rounded-3xl font-medium">开始抓取</button>
    </form>
    ''')

@app.route('/import', methods=['GET', 'POST'])
def import_customers():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return jsonify({'status': 'error', 'msg': '未上传文件'})
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
            qcc_key = get_config('qichacha_key')
            news_key = get_config('news_key')
            new_count = 0
            
            for _, row in df.iterrows():
                name = str(row.get('company_name') or row.get('公司名称') or row.iloc[0]).strip()
                if not name or len(name) < 3 or Customer.query.filter_by(company_name=name).first():
                    continue
                
                basic = get_basic_info(name, qcc_key) if qcc_key else {}
                news_count, news_titles = fetch_company_news(name, news_key)
                score, grade, reasons, _ = calculate_score_and_reasons(basic, news_count, news_titles)
                
                cust = Customer(company_name=name, uscc=basic.get('CreditNo'), score=score, grade=grade, reasons=reasons, news_count=news_count)
                db.session.add(cust)
                new_count += 1
            db.session.commit()
            return jsonify({'status': 'success', 'msg': f'成功导入 {new_count} 家客户'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': f'文件解析失败: {str(e)[:100]}'})

    return render_template_string('''
    <h1 class="text-2xl font-semibold text-center mt-10">📤 导入客户</h1>
    <form method="post" enctype="multipart/form-data" class="max-w-md mx-auto mt-8 p-6 ios-card">
        <input type="file" name="file" accept=".csv,.xlsx" class="w-full p-4 rounded-3xl border mb-6">
        <button type="submit" class="w-full bg-purple-600 text-white py-4 rounded-3xl font-medium">立即导入并自动评分</button>
    </form>
    ''')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        save_config('qichacha_key', request.form.get('qichacha_key', ''))
        save_config('kaidanguo_key', request.form.get('kaidanguo_key', ''))
        save_config('news_key', request.form.get('news_key', ''))
        return jsonify({'status': 'success', 'msg': '所有API Key 已保存'})

    return render_template_string(f'''
    <h1 class="text-2xl font-semibold text-center mt-10">🔑 多API设置</h1>
    <div class="max-w-lg mx-auto mt-8 p-8 ios-card space-y-8">
        <form method="post">
            <div class="mb-6">
                <label class="block text-sm font-medium mb-2">企查查 Key（主推荐）</label>
                <input type="text" name="qichacha_key" value="{get_config('qichacha_key')}" class="w-full p-4 rounded-3xl border" placeholder="请输入企查查Key">
            </div>
            <div class="mb-6">
                <label class="block text-sm font-medium mb-2">开单果 Key（备用抓取）</label>
                <input type="text" name="kaidanguo_key" value="{get_config('kaidanguo_key')}" class="w-full p-4 rounded-3xl border" placeholder="开单果Key（可选）">
            </div>
            <div class="mb-8">
                <label class="block text-sm font-medium mb-2">企业新闻 Key（融资信号）</label>
                <input type="text" name="news_key" value="{get_config('news_key')}" class="w-full p-4 rounded-3xl border" placeholder="新闻API Key（可选）">
                <p class="text-xs text-gray-500 mt-1">用于抓取近3个月融资/扩张新闻</p>
            </div>
            <button type="submit" class="w-full bg-amber-500 text-white py-4 rounded-3xl font-medium">保存所有API配置</button>
        </form>
    </div>
    ''')

@app.route('/customers')
def customers_list():
    page = request.args.get('page', 1, type=int)
    customers = Customer.query.order_by(Customer.fetched_at.desc()).paginate(page=page, per_page=20)
    return render_template_string(f'''
    <h1 class="text-2xl font-semibold text-center mt-10">全部客户列表（{customers.total} 家）</h1>
    <div class="max-w-2xl mx-auto mt-6 p-6 ios-card">
        {"".join(f"<div class='py-3 border-b last:border-none'><strong>{c.company_name}</strong> <span class='text-emerald-500'>评分 {c.score}</span></div>" for c in customers.items)}
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
            return jsonify({'status': 'error', 'msg': '清空失败'})
    return jsonify({'status': 'error'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
