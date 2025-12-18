import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
# ★mailここを設定してください★
MAIL_SENDER = os.getenv("MAIL_SENDER") # 
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") #



app = Flask(__name__)
app.secret_key = 'secret_key_ease_salon_v2'
DB_NAME = 'salon.db'

# --- 設定 ---
MENU_ITEMS = {
    'cut': {'name': 'カット', 'price': 5000, 'duration': 90},
    'perm': {'name': 'パーマ', 'price': 12000, 'duration': 150},
    'color': {'name': 'ヘアカラー', 'price': 8000, 'duration': 150}
}
OPEN_HOUR = 9
CLOSE_HOUR = 19

# 時間枠リスト作成 (9:00, 9:30, ..., 18:30)
def get_time_slots():
    slots = []
    # ※ datetime を使うため、ファイル先頭で from datetime import datetime が必要です
    current = datetime(2000, 1, 1, OPEN_HOUR, 0)
    end = datetime(2000, 1, 1, CLOSE_HOUR, 0)
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    return slots

TIME_SLOTS = get_time_slots()

def get_time_slots():
    slots = []
    current = datetime(2000, 1, 1, OPEN_HOUR, 0)
    end = datetime(2000, 1, 1, CLOSE_HOUR, 0)
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    return slots

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, email TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS reservations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                      menu TEXT, start_time TEXT, end_time TEXT, price INTEGER)''')

def get_current_user():
    if 'user_id' not in session:
        return None
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT username, email FROM users WHERE id = ?", (session['user_id'],))
        return c.fetchone()

#--- メール送信関数 (実装) ---
def send_email(to_email, user_name, reservation_text):
    if not to_email:
        return

    subject = "【美容室 Ease】ご予約ありがとうございます"
    body = f"""
{user_name} 様

この度はご予約ありがとうございます。
以下の内容で承りました。

--------------------------------------------------
{reservation_text}
--------------------------------------------------

ご来店を心よりお待ちしております。
当日お気をつけてお越しくださいませ。

美容室 Ease
Tel: 03-1234-5678
"""

# メールの作成
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = MAIL_SENDER
    msg['To'] = to_email

    # 送信処理
    try:
        # 10秒で諦める設定(timeout=10)を追加
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()

        # パスワード設定がない場合は送信しない（エラー回避）
        if not MAIL_SENDER or not MAIL_PASSWORD:
            print("★メール設定がないため、送信をスキップします")
            return

        server.login(MAIL_SENDER, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"メール送信成功: {to_email}")
    except Exception as e:
        # エラーが起きてもアプリを落とさず、ログにだけ残す
        print(f"★メール送信失敗（でも予約は完了させます）: {e}")

# ... (中略) ...



# --- ルート ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_info = get_current_user()
    username = user_info[0] if user_info else "ゲスト"

    # カート操作（追加・削除）
    if request.method == 'POST':
        if 'add_item' in request.form:
            date = request.form['date']
            time = request.form['time']
            menu_key = request.form['menu']
            
            if menu_key in MENU_ITEMS:
                menu_data = MENU_ITEMS[menu_key]
                # カートの初期化
                if 'cart' not in session:
                    session['cart'] = []
                
                # 一意のIDを作成（削除用）
                item_id = int(datetime.now().timestamp() * 1000)
                
                # セッションに追加
                cart = session['cart']
                cart.append({
                    'id': item_id,
                    'date': date,
                    'time': time,
                    'menu_key': menu_key,
                    'menu_name': menu_data['name'],
                    'price': menu_data['price'],
                    'duration': menu_data['duration']
                })
                session['cart'] = cart
                flash(f"{menu_data['name']}をリストに追加しました")
                
        elif 'delete_item' in request.form:
            item_id = int(request.form['item_id'])
            cart = session.get('cart', [])
            session['cart'] = [item for item in cart if item['id'] != item_id]
            flash("予約リストから削除しました")

        return redirect(url_for('index', date=date) + '#calendar')

# --- カレンダー表示用データの作成 (変更版) ---
    today = datetime.now().date()
    
    # 1. URLパラメータから表示開始日を取得 (?date=2025-XX-XX)
    req_date = request.args.get('date')
    base_date = today # デフォルトは今日

    if req_date:
        try:
            # 文字列を日付オブジェクトに変換
            base_date = datetime.strptime(req_date, "%Y-%m-%d").date()
        except ValueError:
            pass # エラーなら今日のまま

    # 2. 選択可能な範囲を設定（前後3ヶ月 = 90日）
    min_date = today - timedelta(days=90)
    max_date = today + timedelta(days=90)

    # 3. 表示する1週間分の日付リストを作成 (基準日から7日分)
    dates = [base_date + timedelta(days=i) for i in range(7)]
    
    # 4. 「前の週」と「次の週」の日付を計算（ナビゲーションボタン用）
    prev_week_date = base_date - timedelta(days=7)
    next_week_date = base_date + timedelta(days=7)
    
    # DBから既存予約を取得 (datesリストが変われば自動的に検索範囲も変わります)
    start_search = dates[0].strftime("%Y-%m-%d 00:00")
    end_search = (dates[-1] + timedelta(days=1)).strftime("%Y-%m-%d 00:00")
    
    db_reservations = []
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT start_time, end_time, menu FROM reservations WHERE start_time >= ? AND start_time < ?", 
                  (start_search, end_search))
        db_reservations = c.fetchall()
   

    # スケジュールグリッド構築
    schedule = {}
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        schedule[d_str] = {}
        for t in TIME_SLOTS:
            schedule[d_str][t] = {'status': 'available', 'span': 1}

    # DB予約の反映
    for r_start, r_end, r_menu in db_reservations:
        s_dt = datetime.strptime(r_start, "%Y-%m-%d %H:%M")
        e_dt = datetime.strptime(r_end, "%Y-%m-%d %H:%M")
        d_str = s_dt.strftime("%Y-%m-%d")
        if d_str in schedule:
            t_str = s_dt.strftime("%H:%M")
            if t_str in schedule[d_str]:
                duration = (e_dt - s_dt).total_seconds() / 60
                span = int(duration / 30)
                schedule[d_str][t_str] = {'status': 'booked_db', 'menu': r_menu, 'span': span}
                
                # 結合セル処理
                curr = s_dt + timedelta(minutes=30)
                for _ in range(span - 1):
                    c_t = curr.strftime("%H:%M")
                    if c_t in schedule[d_str]:
                        schedule[d_str][c_t]['status'] = 'booked_span'
                    curr += timedelta(minutes=30)

    # カート内（選択中）の予約もカレンダーに反映（重複防止表示のため）
    cart = session.get('cart', [])
    for item in cart:
        d_str = item['date']
        t_str = item['time']
        if d_str in schedule and t_str in schedule[d_str]:
            # すでにDB予約がない場合のみ上書き
            if schedule[d_str][t_str]['status'] == 'available':
                span = int(item['duration'] / 30)
                schedule[d_str][t_str] = {'status': 'booked_cart', 'menu': item['menu_name'], 'span': span}
                
                # 結合セル処理（簡易的な時間の加算）
                curr = datetime.strptime(f"{d_str} {t_str}", "%Y-%m-%d %H:%M") + timedelta(minutes=30)
                for _ in range(span - 1):
                    c_t = curr.strftime("%H:%M")
                    if c_t in schedule[d_str]:
                        schedule[d_str][c_t]['status'] = 'booked_span'
                    curr += timedelta(minutes=30)

    return render_template('index.html', 
                           dates=dates, 
                           time_slots=TIME_SLOTS, 
                           schedule=schedule, 
                           menu=MENU_ITEMS,
                           cart=cart,
                           username=username,
                           # ▼▼▼ 以下を追加してください ▼▼▼
                           current_date=base_date,
                           prev_date=prev_week_date,
                           next_date=next_week_date,
                           min_date=min_date,
                           max_date=max_date)

@app.route('/review')
def review():
    if 'user_id' not in session: return redirect(url_for('login'))
    cart = session.get('cart', [])
    if not cart:
        flash("予約リストが空です")
        return redirect(url_for('index'))
    
    user_info = get_current_user()
    total_price = sum(item['price'] for item in cart)
    
    return render_template('review.html', cart=cart, username=user_info[0], total_price=total_price)

# --- 予約確定処理の修正（メール送信機能付き） ---
@app.route('/book_confirm', methods=['POST'])
def book_confirm():
    if 'user_id' not in session: return redirect(url_for('login'))
    cart = session.get('cart', [])
   
    if not cart:
        return redirect(url_for('index'))

    # ユーザー情報の取得（メール送信のため）
    user_info = get_current_user() # (username, email) が返る
    user_name = user_info[0]
    user_email = user_info[1]
   
    # メール本文用のテキストを作成
    mail_details = ""

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for item in cart:
            start_dt = datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=item['duration'])
           
            # 重複チェック
            c.execute("SELECT id FROM reservations WHERE start_time < ? AND end_time > ?",
                      (end_dt.strftime("%Y-%m-%d %H:%M"), start_dt.strftime("%Y-%m-%d %H:%M")))
            if c.fetchone():
                flash(f"{item['date']} {item['time']} の予約は埋まってしまいました。")
                continue

            # DB保存
            c.execute("INSERT INTO reservations (user_id, menu, start_time, end_time, price) VALUES (?,?,?,?,?)",
                      (session['user_id'], item['menu_name'],
                       start_dt.strftime("%Y-%m-%d %H:%M"),
                       end_dt.strftime("%Y-%m-%d %H:%M"),
                       item['price']))
           
            # メール用テキストに追加
            mail_details += f"■日時: {item['date']} {item['time']}〜\n"
            mail_details += f"  メニュー: {item['menu_name']}\n"
            mail_details += f"  料金: ¥{item['price']}\n\n"

    # ★ここでメール送信を実行★
    if mail_details:
        total_price = sum(item['price'] for item in cart)
        mail_details += f"合計金額: ¥{total_price}"
        send_email(user_email, user_name, mail_details)
   
    session.pop('cart', None)
    flash("オーダー完了！予約確認メールをお送りしました。")
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        action = request.form.get('action')
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            if action == 'register':
                try:
                    c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                              (username, generate_password_hash(password), request.form['email']))
                    flash("登録完了")
                except:
                    flash("エラー: ユーザー名重複")
            elif action == 'login':
                c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
                user = c.fetchone()
                if user and check_password_hash(user[1], password):
                    session['user_id'] = user[0]
                    return redirect(url_for('index'))
                else:
                    flash("認証失敗")
    return render_template('login.html')
 
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# --- ↓↓↓ ここから管理者用機能を追加 ↓↓↓ ---

# 管理者パスワード（本番では環境変数などで管理してください）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("パスワードが違います")
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    # 予約データを日付順に取得（ユーザー情報も結合して取得）
    # 未来の予約のみ表示したい場合は WHERE start_time >= current_time を追加
    reservations = []
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        query = '''
            SELECT r.id, r.start_time, r.end_time, r.menu, r.price, u.username, u.email
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.start_time ASC
        '''
        c.execute(query)
        reservations = c.fetchall()

    return render_template('admin_dashboard.html', reservations=reservations)

@app.route('/admin/delete', methods=['POST'])
def admin_delete_reservation():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    res_id = request.form['res_id']
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM reservations WHERE id = ?", (res_id,))
    
    flash("予約を削除（キャンセル）しました")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))

# --- ↑↑↑ ここまで管理者用機能 ↑↑↑ ---

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
