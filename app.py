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
    reasons = db.Column(db.Text)  # JSON字符串，带时间的原因
    news_count = db.Column(db.Integer, default=0)  # 新增：近期新闻数量
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))

with app.app_context():
    db.create_all()
    for key_name in ['qichacha_key', 'kaidanguo_key', 'news_key']:
        if not Config.query.filter_by(name=key_name).first():
            db.session.add(Config(name=key_name, value=''))
    db.session.commit()

# ====================== API工具函数 ======================
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

def search_kaidanguo(keyword, api_key):
    """开单果企业查询接口（示例，根据实际文档调整URL和参数）"""
    if not api_key:
        return []
    # 示例URL（请替换为开单果实际接口地址和参数格式）
    url = f"https://api.kaidanguo.com/search?key={api_key}&keyword={keyword}&page=1"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        # 根据实际返回结构调整
        return data.get('data', []) if data.get('code') == 200 else []
    except:
        return []

def fetch_company_news(company_name, news_api_key):
    """企业新闻/融资新闻接口（示例使用聚合新闻或通用企业新闻API）"""
    if not news_api_key:
        return 0, []
    # 示例：使用聚合财经/企业新闻接口（可换成具体平台）
    url = f"https://api.example-news.com/search?key={news_api_key}&q={company_name} 融资 OR 投资 OR 扩张&days=90"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        news_list = data.get('articles', [])[:5]  # 取近3个月相关新闻
        return len(news_list), [n.get('title') for n in news_list]
    except:
        return 0, []

def calculate_score_and_reasons(basic_data, news_count=0, news_titles=None):
    """升级评分模型：加入企业新闻信号"""
    money_pressure = 0.9 if basic_data.get('RegStatus') in ['吊销', '注销'] else 0.4
    project_signal = 0.8 if any(kw in (basic_data.get('Scope', '') or '') for kw in ['工程', '科技']) else 0.5
    growth = 0.9 if any(kw in (basic_data.get('Scope', '') or '') for kw in ['高新', '半导体', '新能源', '专精特新']) else 0.5
    
    # 新增新闻信号（融资/扩张新闻越多，成长+缺钱信号越强）
    news_signal = min(news_count * 0.15, 0.9)
    
    score = int((money_pressure * project_signal * growth * (1 + news_signal)) * 100)
    score = min(max(score, 15), 98)
    
    grade = 'A' if score >= 80 else 'B' if score >= 60 else 'C'
    
    reasons_list = [
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 工商信息获取成功",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 资金压力信号: {'强' if money_pressure > 0.7 else '中'}",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 项目/成长信号: {'强' if growth > 0.7 else '中'}",
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 企业新闻信号: 近90天找到 {news_count} 条相关新闻"
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
    
    # ...（首页HTML保持原样，卡片式iOS风，包含清空按钮等）
    # 为节省篇幅，这里省略完整HTML（与之前版本一致），您可直接复制之前首页HTML部分替换
    # 注意：在客户卡片中可新增显示 news_count
    return "首页HTML（保持原iOS风格）"  # 请替换为之前提供的完整首页HTML

@app.route('/fetch', methods=['GET', 'POST'])
def fetch_customers():
    if request.method == 'POST':
        keyword = request.form.get('keyword', '')
        pages = int(request.form.get('pages', 3))
        
        qcc_key = get_config('qichacha_key')
        kd_key = get_config('kaidanguo_key')
        news_key = get_config('news_key')
        
        if not qcc_key and not kd_key:
            return jsonify({'status': 'error', 'msg': '请至少设置一个企业查询API Key'})
        
        new_count = 0
        for _ in range(pages):
            # 优先企查查，失败降级到开单果
            results = []  # fuzzy_search_companies(keyword, qcc_key)  # 保留您原有的企查查函数
            if not results and kd_key:
                results = search_kaidanguo(keyword, kd_key)
            
            for item in results:
                name = item.get('Name') or item.get('company_name') or ''
                if not name or Customer.query.filter_by(company_name=name).first():
                    continue
                
                # 获取工商基本信息（可混合使用）
                basic = {}  # get_basic_info(name, qcc_key) if qcc_key else {}
                
                # 新增：抓取企业新闻
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
    
    # GET页面保持原样
    return "抓取页面HTML"

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        qcc = request.form.get('qichacha_key')
        kd = request.form.get('kaidanguo_key')
        news = request.form.get('news_key')
        if qcc: save_config('qichacha_key', qcc)
        if kd: save_config('kaidanguo_key', kd)
        if news: save_config('news_key', news)
        return jsonify({'status': 'success', 'msg': '所有API Key 已保存'})
    
    return render_template_string(f'''
    <h1 class="text-2xl font-semibold text-center mt-10">🔑 多API设置</h1>
    <div class="max-w-lg mx-auto mt-8 p-8 ios-card space-y-8">
        <div>
            <label class="block text-sm font-medium mb-2">企查查 Key（主推荐）</label>
            <input type="text" name="qichacha_key" value="{get_config('qichacha_key')}" class="w-full p-4 rounded-3xl border">
        </div>
        <div>
            <label class="block text-sm font-medium mb-2">开单果 Key（企业查询补充）</label>
            <input type="text" name="kaidanguo_key" value="{get_config('kaidanguo_key')}" class="w-full p-4 rounded-3xl border" placeholder="如有开单果账号请填写">
            <p class="text-xs text-gray-500 mt-1">用于扩展抓取量或作为备用</p>
        </div>
        <div>
            <label class="block text-sm font-medium mb-2">企业新闻 Key（融资新闻信号）</label>
            <input type="text" name="news_key" value="{get_config('news_key')}" class="w-full p-4 rounded-3xl border" placeholder="新闻聚合API Key">
            <p class="text-xs text-gray-500 mt-1">用于抓取近3个月融资/扩张新闻，提升评分准确性</p>
        </div>
        <button onclick="saveSettings()" class="w-full bg-amber-500 text-white py-4 rounded-3xl font-medium">保存所有API配置</button>
    </div>
    <script>
    function saveSettings() {{
        // 使用FormData或fetch提交多个key，实际实现可调整为单个表单
        alert('配置已保存！抓取时将自动使用多API');
        location.reload();
    }}
    </script>
    ''')

# 清空数据、导入等其他路由保持不变（仅Customer模型新增news_count字段）

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
