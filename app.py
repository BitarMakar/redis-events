import json
import time
import math
import sqlite3
from flask import Flask, request, jsonify, render_template
import redis
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
DB_PATH = 'events.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            subtitle TEXT DEFAULT '',
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            radius REAL NOT NULL,
            start_time INTEGER NOT NULL,
            end_time INTEGER NOT NULL,
            special_participants TEXT DEFAULT '',
            audience TEXT DEFAULT ''
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS log_entries (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            action TEXT NOT NULL,
            event_id TEXT,
            email TEXT,
            details TEXT DEFAULT ''
        )
    ''')

    conn.commit()
    conn.close()

def write_log(action, event_id=None, email=None, details=''):
    conn = get_db()
    conn.execute(
        'INSERT INTO log_entries (timestamp, action, event_id, email, details) VALUES (?, ?, ?, ?, ?)',
        (time.time(), action, event_id, email, details)
    )
    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def is_user_allowed(email, event_data):
    special = event_data.get('special_participants', '')
    audience = event_data.get('audience', '')

    if special:
        special_list = [e.strip() for e in special.split(',') if e.strip()]
        if email in special_list:
            return True

    if not audience:
        return True

    audience_list = [e.strip() for e in audience.split(',') if e.strip()]
    return email in audience_list

def load_event_to_redis(event_row):
    eid = event_row['event_id']
    pipe = r.pipeline()

    pipe.hset(f'event:{eid}', mapping={
        'title': event_row['title'],
        'subtitle': event_row['subtitle'],
        'lat': str(event_row['lat']),
        'lon': str(event_row['lon']),
        'radius': str(event_row['radius']),
        'start_time': str(event_row['start_time']),
        'end_time': str(event_row['end_time']),
        'special_participants': event_row['special_participants'] or '',
        'audience': event_row['audience'] or ''
    })

    pipe.sadd('active_events', eid)
    pipe.execute()

def unload_event_from_redis(event_id):
    pipe = r.pipeline()
    pipe.delete(f'event:{event_id}')
    pipe.delete(f'event:{event_id}:participants')
    pipe.delete(f'event:{event_id}:chat')
    pipe.srem('active_events', event_id)
    pipe.execute()

def scheduler_job():
    now = int(time.time())
    conn = get_db()

    rows = conn.execute(
        'SELECT * FROM events WHERE start_time <= ? AND end_time >= ?',
        (now, now)
    ).fetchall()

    currently_active = r.smembers('active_events')

    for row in rows:
        if row['event_id'] not in currently_active:
            load_event_to_redis(row)

    for eid in currently_active:
        event_data = r.hgetall(f'event:{eid}')
        if event_data:
            end_time = int(event_data.get('end_time', 0))
            if now > end_time:
                unload_event_from_redis(eid)

    conn.close()

@app.route('/api/start-event', methods=['POST'])
def start_event():
    data = request.get_json()
    event_id = data.get('event_id')

    conn = get_db()
    row = conn.execute('SELECT * FROM events WHERE event_id = ?', (event_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'result': 'nok', 'reason': 'Event not found'})

    now = int(time.time())
    if now < row['start_time'] or now > row['end_time']:
        return jsonify({'result': 'nok', 'reason': 'Event not within time window'})

    load_event_to_redis(row)
    return jsonify({'result': 'ok'})

@app.route('/api/stop-event', methods=['POST'])
def stop_event():
    data = request.get_json()
    event_id = data.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    unload_event_from_redis(event_id)
    write_log('stop-event', event_id=event_id)
    return jsonify({'result': 'ok'})

@app.route('/api/checkin', methods=['POST'])
def checkin():
    data = request.get_json()
    email = data.get('email')
    event_id = data.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    event_data = r.hgetall(f'event:{event_id}')

    if not is_user_allowed(email, event_data):
        return jsonify({'result': 'nok', 'reason': 'Not allowed'})

    if r.zscore(f'event:{event_id}:participants', email) is not None:
        return jsonify({'result': 'nok', 'reason': 'Already checked in'})

    r.zadd(f'event:{event_id}:participants', {email: time.time()})
    write_log('checkin', event_id=event_id, email=email)
    return jsonify({'result': 'ok'})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.get_json()
    email = data.get('email')
    event_id = data.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    if r.zscore(f'event:{event_id}:participants', email) is None:
        return jsonify({'result': 'nok', 'reason': 'Not checked in'})

    r.zrem(f'event:{event_id}:participants', email)
    write_log('checkout', event_id=event_id, email=email)
    return jsonify({'result': 'ok'})

@app.route('/api/find-events', methods=['GET'])
def find_events():
    email = request.args.get('email')
    x = float(request.args.get('x'))
    y = float(request.args.get('y'))

    active_ids = r.smembers('active_events')
    result = []

    for eid in active_ids:
        event_data = r.hgetall(f'event:{eid}')
        if not event_data:
            continue

        event_lat = float(event_data['lat'])
        event_lon = float(event_data['lon'])
        event_radius = float(event_data['radius'])

        distance = haversine(x, y, event_lat, event_lon)

        if distance <= event_radius and is_user_allowed(email, event_data):
            result.append(eid)

    return jsonify({'event_ids': result})

@app.route('/api/get-participants', methods=['GET'])
def get_participants():
    event_id = request.args.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    participants = r.zrange(f'event:{event_id}:participants', 0, -1, withscores=True)
    result = [{'email': email, 'timestamp': ts} for email, ts in participants]
    return jsonify({'participants': result})

@app.route('/api/num-participants', methods=['GET'])
def num_participants():
    event_id = request.args.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    count = r.zcard(f'event:{event_id}:participants')
    return jsonify({'count': count})

@app.route('/api/checkout-byadmin', methods=['POST'])
def checkout_byadmin():
    data = request.get_json()
    email = data.get('email')
    event_id = data.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    if r.zscore(f'event:{event_id}:participants', email) is None:
        return jsonify({'result': 'nok', 'reason': 'Not checked in'})

    r.zrem(f'event:{event_id}:participants', email)
    write_log('checkout-byadmin', event_id=event_id, email=email)
    return jsonify({'result': 'ok'})

@app.route('/api/checkin-byadmin', methods=['POST'])
def checkin_byadmin():
    data = request.get_json()
    email = data.get('email')
    event_id = data.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    if r.zscore(f'event:{event_id}:participants', email) is not None:
        return jsonify({'result': 'nok', 'reason': 'Already checked in'})

    r.zadd(f'event:{event_id}:participants', {email: time.time()})
    write_log('checkin-byadmin', event_id=event_id, email=email)
    return jsonify({'result': 'ok'})

@app.route('/api/get-events', methods=['GET'])
def get_events():
    active_ids = r.smembers('active_events')
    events = []
    for eid in active_ids:
        data = r.hgetall(f'event:{eid}')
        if data:
            count = r.zcard(f'event:{eid}:participants')
            events.append({
                'event_id': eid,
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'lat': float(data.get('lat', 0)),
                'lon': float(data.get('lon', 0)),
                'radius': float(data.get('radius', 0)),
                'start_time': int(data.get('start_time', 0)),
                'end_time': int(data.get('end_time', 0)),
                'special_participants': data.get('special_participants', ''),
                'audience': data.get('audience', ''),
                'participant_count': count
            })
    return jsonify({'events': events})

@app.route('/api/post-to-chat', methods=['POST'])
def post_to_chat():
    data = request.get_json()
    email = data.get('email')
    event_id = data.get('event_id')
    text = data.get('text')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    if r.zscore(f'event:{event_id}:participants', email) is None:
        return jsonify({'result': 'nok', 'reason': 'Not a participant'})

    ts = time.time()
    message = json.dumps({'email': email, 'text': text, 'timestamp': ts})
    r.zadd(f'event:{event_id}:chat', {message: ts})
    return jsonify({'result': 'ok'})

@app.route('/api/get-posts', methods=['GET'])
def get_posts():
    event_id = request.args.get('event_id')

    if not r.sismember('active_events', event_id):
        return jsonify({'result': 'nok', 'reason': 'Event not active'})

    messages = r.zrange(f'event:{event_id}:chat', 0, -1)
    result = []
    for msg in messages:
        parsed = json.loads(msg)
        result.append({
            'timestamp': parsed['timestamp'],
            'email': parsed['email'],
            'text': parsed['text']
        })
    return jsonify({'posts': result})

@app.route('/api/get-user-posts', methods=['GET'])
def get_user_posts():
    email = request.args.get('email')

    active_ids = r.smembers('active_events')
    all_posts = []

    for eid in active_ids:
        messages = r.zrange(f'event:{eid}:chat', 0, -1)
        for msg in messages:
            parsed = json.loads(msg)
            if parsed['email'] == email:
                all_posts.append({
                    'timestamp': parsed['timestamp'],
                    'text': parsed['text']
                })

    all_posts.sort(key=lambda x: x['timestamp'])
    return jsonify({'posts': all_posts})

@app.route('/api/seed', methods=['POST'])
def seed_data():
    now = int(time.time())
    conn = get_db()

    events = [
        ('evt-001', 'Python Workshop', 'Intro to Flask', 37.9838, 23.7275, 500, now, now + 7200, 'admin@aueb.gr', ''),
        ('evt-002', 'AI Seminar', 'Machine Learning Basics', 37.9855, 23.7330, 300, now, now + 7200, '', 'student@aueb.gr,prof@aueb.gr'),
        ('evt-003', 'Math Lecture', 'Linear Algebra', 37.9800, 23.7200, 1000, now, now + 7200, '', '')
    ]

    for e in events:
        conn.execute(
            'INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', e
        )

    conn.commit()
    conn.close()

    scheduler_job()
    return jsonify({'result': 'ok', 'message': '3 sample events created and loaded'})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    init_db()

    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduler_job, 'interval', seconds=60)
    scheduler.start()

    app.run(debug=True, use_reloader=False)