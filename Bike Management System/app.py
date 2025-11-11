import os  # 添加在这里
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL CHECK(role IN ('user', 'admin', 'maintenance')),
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 单车表
    c.execute('''CREATE TABLE IF NOT EXISTS bikes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  bike_id TEXT UNIQUE NOT NULL,
                  latitude REAL NOT NULL,
                  longitude REAL NOT NULL,
                  status TEXT DEFAULT 'available' CHECK(status IN ('available', 'rented', 'maintenance')),
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 订单表
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id TEXT UNIQUE NOT NULL,
                  user_id INTEGER NOT NULL,
                  bike_id INTEGER NOT NULL,
                  start_time TIMESTAMP NOT NULL,
                  end_time TIMESTAMP,
                  start_lat REAL NOT NULL,
                  start_lng REAL NOT NULL,
                  end_lat REAL,
                  end_lng REAL,
                  cost REAL DEFAULT 0,
                  status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed')),
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (bike_id) REFERENCES bikes (id))''')
    
    # 报修表
    c.execute('''CREATE TABLE IF NOT EXISTS repairs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  repair_id TEXT UNIQUE NOT NULL,
                  user_id INTEGER NOT NULL,
                  bike_id INTEGER NOT NULL,
                  latitude REAL NOT NULL,
                  longitude REAL NOT NULL,
                  description TEXT NOT NULL,
                  status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  completed_at TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (bike_id) REFERENCES bikes (id))''')
    
    # 调度表
    c.execute('''CREATE TABLE IF NOT EXISTS dispatches
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  dispatch_id TEXT UNIQUE NOT NULL,
                  bike_id INTEGER NOT NULL,
                  from_lat REAL NOT NULL,
                  from_lng REAL NOT NULL,
                  to_lat REAL NOT NULL,
                  to_lng REAL NOT NULL,
                  status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  completed_at TIMESTAMP,
                  FOREIGN KEY (bike_id) REFERENCES bikes (id))''')
    
    # 已完成任务历史表（用于维护人员查看已完成任务）
    c.execute('''CREATE TABLE IF NOT EXISTS task_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id TEXT UNIQUE NOT NULL,
                  task_type TEXT NOT NULL CHECK(task_type IN ('repair', 'dispatch')),
                  bike_id TEXT NOT NULL,
                  task_details TEXT NOT NULL,
                  completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 插入默认测试数据
    try:
        c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
                 ('admin', 'admin123', 'admin'))
        c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
                 ('maintenance', 'maint123', 'maintenance'))
        c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
                 ('user1', 'user123', 'user'))
        
        # 在新的运行区域内的单车分布 - 只保留四个重要地点的12辆车
        bikes_data = [
            # 河南科技大学西苑校区 (3辆)
            ('B001', 34.662808, 112.374521, 'available'),
            ('B002', 34.663000, 112.374800, 'available'),
            ('B003', 34.662600, 112.374200, 'available'),
            
            # 西苑公园 (3辆)
            ('B004', 34.649274, 112.404774, 'available'),
            ('B005', 34.649500, 112.405000, 'available'),
            ('B006', 34.649000, 112.404500, 'available'),
            
            # 东方红农耕博物馆 (3辆)
            ('B007', 34.671810, 112.379333, 'available'),
            ('B008', 34.672000, 112.379600, 'available'),
            ('B009', 34.671600, 112.379000, 'available'),
            
            # 周山森林公园南门 (3辆)
            ('B010', 34.623446, 112.387759, 'available'),
            ('B011', 34.623700, 112.388000, 'available'),
            ('B012', 34.623200, 112.387500, 'available')
        ]
        c.executemany("INSERT OR IGNORE INTO bikes (bike_id, latitude, longitude, status) VALUES (?, ?, ?, ?)", bikes_data)
        
        # 插入一些测试任务数据
        # 维修任务
        c.execute('''INSERT OR IGNORE INTO repairs (repair_id, user_id, bike_id, latitude, longitude, description) 
                     SELECT 'REP001', u.id, b.id, b.latitude, b.longitude, '车胎漏气需要更换'
                     FROM users u, bikes b 
                     WHERE u.username = 'user1' AND b.bike_id = 'B001' 
                     AND NOT EXISTS (SELECT 1 FROM repairs WHERE repair_id = 'REP001')''')
        
        # 调度任务
        c.execute('''INSERT OR IGNORE INTO dispatches (dispatch_id, bike_id, from_lat, from_lng, to_lat, to_lng) 
                     SELECT 'DISP001', b.id, b.latitude, b.longitude, 34.6500, 112.4000
                     FROM bikes b 
                     WHERE b.bike_id = 'B002' 
                     AND NOT EXISTS (SELECT 1 FROM dispatches WHERE dispatch_id = 'DISP001')''')
                     
    except Exception as e:
        print(f"初始化数据时出错: {e}")
    
    conn.commit()
    conn.close()

init_db()

# 登录页面
@app.route('/')
def index():
    return render_template('login.html')

# 登录处理
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = c.fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['role'] = user[3]
        
        if user[3] == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user[3] == 'maintenance':
            return redirect(url_for('maintenance_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    else:
        return "登录失败，请检查用户名和密码"

# 注册页面
@app.route('/register')
def register():
    return render_template('register.html')

# 注册处理
@app.route('/register', methods=['POST'])
def register_post():
    username = request.form['username']
    password = request.form['password']
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'user')", (username, password))
        conn.commit()
        conn.close()
        return "注册成功！<a href='/'>返回登录</a>"
    except:
        conn.close()
        return "用户名已存在，请选择其他用户名"

# 用户仪表板
@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session or session['role'] != 'user':
        return redirect(url_for('index'))
    
    # 检查用户是否有正在进行的订单
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id = ? AND status = 'active'", (session['user_id'],))
    active_order = c.fetchone()
    conn.close()
    
    has_active_order = active_order is not None
    current_order_id = active_order[1] if active_order else None
    
    return render_template('user_dashboard.html', 
                         username=session['username'],
                         has_active_order=has_active_order,
                         current_order_id=current_order_id)

# 获取附近单车
@app.route('/api/nearby_bikes')
def get_nearby_bikes():
    lat = request.args.get('lat', default=34.6000, type=float)
    lng = request.args.get('lng', default=112.2917, type=float)
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT bike_id, latitude, longitude, status FROM bikes")
    bikes = c.fetchall()
    conn.close()
    
    bike_list = []
    for bike in bikes:
        bike_list.append({
            'bike_id': bike[0],
            'latitude': bike[1],
            'longitude': bike[2],
            'status': bike[3]
        })
    
    return jsonify(bike_list)

# 开始租车
@app.route('/api/rent_bike', methods=['POST'])
def rent_bike():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'success': False, 'message': '请先登录'})
    
    bike_id = request.json.get('bike_id')
    lat = request.json.get('lat')
    lng = request.json.get('lng')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 检查单车是否存在且可用
    c.execute("SELECT id FROM bikes WHERE bike_id = ? AND status = 'available'", (bike_id,))
    bike = c.fetchone()
    
    if not bike:
        conn.close()
        return jsonify({'success': False, 'message': '单车不存在或不可用'})
    
    # 检查用户是否已有进行中的订单
    c.execute("SELECT id FROM orders WHERE user_id = ? AND status = 'active'", (session['user_id'],))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': '您已有进行中的订单'})
    
    # 创建新订单
    order_id = str(uuid.uuid4())[:8]
    c.execute('''INSERT INTO orders 
                 (order_id, user_id, bike_id, start_time, start_lat, start_lng, status) 
                 VALUES (?, ?, ?, datetime('now'), ?, ?, 'active')''',
              (order_id, session['user_id'], bike[0], lat, lng))
    
    # 更新单车状态
    c.execute("UPDATE bikes SET status = 'rented' WHERE bike_id = ?", (bike_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'order_id': order_id, 'message': '租车成功'})

# 还车
@app.route('/api/return_bike', methods=['POST'])
def return_bike():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'success': False, 'message': '请先登录'})
    
    lat = request.json.get('lat')
    lng = request.json.get('lng')
    
    # 新的运行区域：东经112°10′至112°25′，北纬34°30′至34°42′
    jianxi_bounds = {
        'min_lat': 34.5000, 'max_lat': 34.7000,   # 北纬34°30′至34°42′
        'min_lng': 112.1667, 'max_lng': 112.4167  # 东经112°10′至112°25′
    }
    
    if not (jianxi_bounds['min_lat'] <= lat <= jianxi_bounds['max_lat'] and
            jianxi_bounds['min_lng'] <= lng <= jianxi_bounds['max_lng']):
        return jsonify({'success': False, 'message': '还车失败：请在指定区域内还车（东经112°10′至112°25′，北纬34°30′至34°42′）'})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取用户当前订单
    c.execute('''SELECT o.id, o.order_id, o.start_time, b.bike_id 
                 FROM orders o 
                 JOIN bikes b ON o.bike_id = b.id 
                 WHERE o.user_id = ? AND o.status = 'active''', 
              (session['user_id'],))
    order = c.fetchone()
    
    if not order:
        conn.close()
        return jsonify({'success': False, 'message': '没有找到进行中的订单'})
    
    # 计算费用（2元/10分钟）
    start_time = datetime.fromisoformat(order[2].replace(' ', 'T'))
    end_time = datetime.now()
    duration_minutes = (end_time - start_time).total_seconds() / 60
    cost = (duration_minutes / 10) * 2  # 每10分钟2元
    
    # 更新订单
    c.execute('''UPDATE orders 
                 SET end_time = datetime('now'), end_lat = ?, end_lng = ?, cost = ?, status = 'completed' 
                 WHERE id = ?''', 
              (lat, lng, cost, order[0]))
    
    # 更新单车状态
    c.execute("UPDATE bikes SET status = 'available', latitude = ?, longitude = ? WHERE bike_id = ?", 
              (lat, lng, order[3]))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True, 
        'message': f'还车成功！使用时间：{duration_minutes:.1f}分钟，费用：{cost:.2f}元',
        'duration': duration_minutes,
        'cost': cost
    })

# 获取当前订单信息
@app.route('/api/current_order')
def get_current_order():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT o.order_id, o.start_time, b.bike_id 
                 FROM orders o 
                 JOIN bikes b ON o.bike_id = b.id 
                 WHERE o.user_id = ? AND o.status = 'active''', 
              (session['user_id'],))
    order = c.fetchone()
    conn.close()
    
    if order:
        start_time = datetime.fromisoformat(order[1].replace(' ', 'T'))
        duration_minutes = (datetime.now() - start_time).total_seconds() / 60
        current_cost = (duration_minutes / 10) * 2
        
        return jsonify({
            'success': True,
            'order_id': order[0],
            'bike_id': order[2],
            'start_time': order[1],
            'duration': duration_minutes,
            'current_cost': current_cost
        })
    else:
        return jsonify({'success': False})

# 车辆报修
@app.route('/api/report_repair', methods=['POST'])
def report_repair():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'success': False, 'message': '请先登录'})
    
    bike_id = request.json.get('bike_id')
    lat = request.json.get('lat')
    lng = request.json.get('lng')
    description = request.json.get('description')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 检查单车是否存在
    c.execute("SELECT id FROM bikes WHERE bike_id = ?", (bike_id,))
    bike = c.fetchone()
    
    if not bike:
        conn.close()
        return jsonify({'success': False, 'message': '单车不存在'})
    
    # 创建报修单
    repair_id = str(uuid.uuid4())[:8]
    c.execute('''INSERT INTO repairs 
                 (repair_id, user_id, bike_id, latitude, longitude, description) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (repair_id, session['user_id'], bike[0], lat, lng, description))
    
    # 更新单车状态为维修中
    c.execute("UPDATE bikes SET status = 'maintenance' WHERE bike_id = ?", (bike_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '报修成功'})

# 获取历史订单
@app.route('/api/user_orders')
def get_user_orders():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT o.order_id, o.start_time, o.end_time, o.cost, b.bike_id, 
                        o.start_lat, o.start_lng, o.end_lat, o.end_lng
                 FROM orders o 
                 JOIN bikes b ON o.bike_id = b.id 
                 WHERE o.user_id = ? AND o.status = 'completed'
                 ORDER BY o.start_time DESC''', 
              (session['user_id'],))
    orders = c.fetchall()
    conn.close()
    
    order_list = []
    for order in orders:
        order_list.append({
            'order_id': order[0],
            'start_time': order[1],
            'end_time': order[2],
            'cost': order[3],
            'bike_id': order[4],
            'start_lat': order[5],
            'start_lng': order[6],
            'end_lat': order[7],
            'end_lng': order[8]
        })
    
    return jsonify({'success': True, 'orders': order_list})

# 管理员获取所有单车
@app.route('/api/all_bikes')
def get_all_bikes():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT bike_id, latitude, longitude, status FROM bikes''')
    bikes = c.fetchall()
    conn.close()
    
    bike_list = []
    for bike in bikes:
        bike_list.append({
            'bike_id': bike[0],
            'latitude': bike[1],
            'longitude': bike[2],
            'status': bike[3]
        })
    
    return jsonify({'success': True, 'bikes': bike_list})

# 管理员获取统计信息
@app.route('/api/admin_stats')
def get_admin_stats():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取单车统计
    c.execute("SELECT COUNT(*) FROM bikes")
    total_bikes = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bikes WHERE status = 'available'")
    available_bikes = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bikes WHERE status = 'maintenance'")
    maintenance_bikes = c.fetchone()[0]
    
    # 获取最近订单
    c.execute('''SELECT o.order_id, u.username, o.start_time, o.end_time, o.cost, 
                        o.start_lat, o.start_lng, o.end_lat, o.end_lng
                 FROM orders o 
                 JOIN users u ON o.user_id = u.id 
                 WHERE o.status = 'completed'
                 ORDER BY o.end_time DESC 
                 LIMIT 10''')
    recent_orders = c.fetchall()
    
    conn.close()
    
    orders_list = []
    for order in recent_orders:
        orders_list.append({
            'order_id': order[0],
            'username': order[1],
            'start_time': order[2],
            'end_time': order[3],
            'cost': order[4],
            'start_lat': order[5],
            'start_lng': order[6],
            'end_lat': order[7],
            'end_lng': order[8]
        })
    
    return jsonify({
        'success': True,
        'stats': {
            'total_bikes': total_bikes,
            'available_bikes': available_bikes,
            'maintenance_bikes': maintenance_bikes
        },
        'recent_orders': orders_list
    })

# 创建调度任务
@app.route('/api/create_dispatch', methods=['POST'])
def create_dispatch():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
    bike_id = request.json.get('bike_id')
    from_lat = request.json.get('from_lat')
    from_lng = request.json.get('from_lng')
    to_lat = request.json.get('to_lat')
    to_lng = request.json.get('to_lng')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 检查单车是否存在
    c.execute("SELECT id FROM bikes WHERE bike_id = ?", (bike_id,))
    bike = c.fetchone()
    
    if not bike:
        conn.close()
        return jsonify({'success': False, 'message': '单车不存在'})
    
    # 创建调度单
    dispatch_id = str(uuid.uuid4())[:8]
    c.execute('''INSERT INTO dispatches 
                 (dispatch_id, bike_id, from_lat, from_lng, to_lat, to_lng) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (dispatch_id, bike[0], from_lat, from_lng, to_lat, to_lng))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '调度任务创建成功'})

# 删除单车
@app.route('/api/delete_bike', methods=['POST'])
def delete_bike():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
    bike_id = request.json.get('bike_id')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 检查单车是否存在
    c.execute("SELECT id FROM bikes WHERE bike_id = ?", (bike_id,))
    bike = c.fetchone()
    
    if not bike:
        conn.close()
        return jsonify({'success': False, 'message': '单车不存在'})
    
    # 检查单车是否正在被租用
    c.execute("SELECT id FROM orders WHERE bike_id = ? AND status = 'active'", (bike[0],))
    active_order = c.fetchone()
    
    if active_order:
        conn.close()
        return jsonify({'success': False, 'message': '无法删除正在租用中的单车'})
    
    try:
        # 删除单车
        c.execute("DELETE FROM bikes WHERE bike_id = ?", (bike_id,))
        
        # 同时删除相关的维修记录和调度记录
        c.execute("DELETE FROM repairs WHERE bike_id = ?", (bike[0],))
        c.execute("DELETE FROM dispatches WHERE bike_id = ?", (bike[0],))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '单车删除成功'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

# 创建新单车
@app.route('/api/create_bike', methods=['POST'])
def create_bike():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
    bike_id = request.json.get('bike_id')
    latitude = request.json.get('latitude')
    longitude = request.json.get('longitude')
    
    # 验证输入
    if not bike_id or not latitude or not longitude:
        return jsonify({'success': False, 'message': '请填写完整信息'})
    
    # 验证坐标范围
    jianxi_bounds = {
        'min_lat': 34.5000, 'max_lat': 34.7000,
        'min_lng': 112.1667, 'max_lng': 112.4167
    }
    
    if not (jianxi_bounds['min_lat'] <= latitude <= jianxi_bounds['max_lat'] and
            jianxi_bounds['min_lng'] <= longitude <= jianxi_bounds['max_lng']):
        return jsonify({'success': False, 'message': '单车位置必须在运行区域内'})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # 检查单车ID是否已存在
        c.execute("SELECT id FROM bikes WHERE bike_id = ?", (bike_id,))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '单车编号已存在'})
        
        # 创建新单车
        c.execute('''INSERT INTO bikes (bike_id, latitude, longitude, status) 
                     VALUES (?, ?, ?, 'available')''',
                  (bike_id, latitude, longitude))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '单车创建成功'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'})

# 维护人员获取任务
@app.route('/api/maintenance_tasks')
def get_maintenance_tasks():
    if 'user_id' not in session or session['role'] != 'maintenance':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取维修任务
    c.execute('''SELECT r.repair_id, b.bike_id, r.latitude, r.longitude, r.description, r.created_at
                 FROM repairs r 
                 JOIN bikes b ON r.bike_id = b.id 
                 WHERE r.status = 'pending'
                 ORDER BY r.created_at DESC''')
    repair_tasks = c.fetchall()
    
    # 获取调度任务
    c.execute('''SELECT d.dispatch_id, b.bike_id, d.from_lat, d.from_lng, d.to_lat, d.to_lng, d.created_at
                 FROM dispatches d 
                 JOIN bikes b ON d.bike_id = b.id 
                 WHERE d.status = 'pending'
                 ORDER BY d.created_at DESC''')
    dispatch_tasks = c.fetchall()
    
    conn.close()
    
    repairs_list = []
    for task in repair_tasks:
        repairs_list.append({
            'task_id': task[0],
            'bike_id': task[1],
            'latitude': task[2],
            'longitude': task[3],
            'description': task[4],
            'created_at': task[5],
            'type': 'repair'
        })
    
    dispatches_list = []
    for task in dispatch_tasks:
        dispatches_list.append({
            'task_id': task[0],
            'bike_id': task[1],
            'from_lat': task[2],
            'from_lng': task[3],
            'to_lat': task[4],
            'to_lng': task[5],
            'created_at': task[6],
            'type': 'dispatch'
        })
    
    return jsonify({
        'success': True,
        'repair_tasks': repairs_list,
        'dispatch_tasks': dispatches_list
    })

# 维护人员获取已完成任务
@app.route('/api/completed_tasks')
def get_completed_tasks():
    if 'user_id' not in session or session['role'] != 'maintenance':
        return jsonify({'success': False})
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取已完成的维修任务
    c.execute('''SELECT r.repair_id, b.bike_id, r.description, r.completed_at
                 FROM repairs r 
                 JOIN bikes b ON r.bike_id = b.id 
                 WHERE r.status = 'completed'
                 ORDER BY r.completed_at DESC 
                 LIMIT 20''')
    completed_repairs = c.fetchall()
    
    # 获取已完成的调度任务
    c.execute('''SELECT d.dispatch_id, b.bike_id, d.from_lat, d.from_lng, d.to_lat, d.to_lng, d.completed_at
                 FROM dispatches d 
                 JOIN bikes b ON d.bike_id = b.id 
                 WHERE d.status = 'completed'
                 ORDER BY d.completed_at DESC 
                 LIMIT 20''')
    completed_dispatches = c.fetchall()
    
    conn.close()
    
    repairs_list = []
    for task in completed_repairs:
        repairs_list.append({
            'task_id': task[0],
            'bike_id': task[1],
            'description': task[2],
            'completed_at': task[3],
            'type': 'repair'
        })
    
    dispatches_list = []
    for task in completed_dispatches:
        dispatches_list.append({
            'task_id': task[0],
            'bike_id': task[1],
            'from_lat': task[2],
            'from_lng': task[3],
            'to_lat': task[4],
            'to_lng': task[5],
            'completed_at': task[6],
            'type': 'dispatch'
        })
    
    return jsonify({
        'success': True,
        'completed_repairs': repairs_list,
        'completed_dispatches': dispatches_list
    })

# 完成任务
@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    if 'user_id' not in session or session['role'] != 'maintenance':
        return jsonify({'success': False, 'message': '权限不足'})
    
    task_id = request.json.get('task_id')
    task_type = request.json.get('task_type')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if task_type == 'repair':
        # 完成维修任务
        c.execute('''UPDATE repairs SET status = 'completed', completed_at = datetime('now') 
                     WHERE repair_id = ?''', (task_id,))
        
        # 获取对应的单车ID并更新状态为可用
        c.execute('''SELECT bike_id FROM repairs WHERE repair_id = ?''', (task_id,))
        repair = c.fetchone()
        if repair:
            c.execute('''UPDATE bikes SET status = 'available' WHERE id = ?''', (repair[0],))
    
    elif task_type == 'dispatch':
        # 完成调度任务
        c.execute('''UPDATE dispatches SET status = 'completed', completed_at = datetime('now') 
                     WHERE dispatch_id = ?''', (task_id,))
        
        # 获取调度信息并更新单车位置
        c.execute('''SELECT bike_id, to_lat, to_lng FROM dispatches WHERE dispatch_id = ?''', (task_id,))
        dispatch = c.fetchone()
        if dispatch:
            c.execute('''UPDATE bikes SET latitude = ?, longitude = ? WHERE id = ?''', 
                      (dispatch[1], dispatch[2], dispatch[0]))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '任务完成'})

# 管理员仪表板
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('index'))
    return render_template('admin_dashboard.html', username=session['username'])

# 维护人员仪表板
@app.route('/maintenance_dashboard')
def maintenance_dashboard():
    if 'user_id' not in session or session['role'] != 'maintenance':
        return redirect(url_for('index'))
    return render_template('maintenance_dashboard.html', username=session['username'])

# 退出登录
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 获取环境变量中的端口，如果没有则使用5000
    port = int(os.environ.get("PORT", 5000))
    # 必须设置 host='0.0.0.0' 才能外部访问
    app.run(host='0.0.0.0', port=port, debug=False)
