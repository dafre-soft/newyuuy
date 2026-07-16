import os
import re
import json
import struct
import sqlite3
import hashlib
import secrets
import wave
from datetime import datetime, timezone, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template_string, request, jsonify, send_from_directory, redirect, url_for, session as flask_session
from werkzeug.utils import secure_filename
from functools import wraps

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
# FIXED: Max upload size set to 1GB (1024 * 1024 * 1024 bytes)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
DB_PATH = 'chat_database.db'

for folder in [UPLOAD_FOLDER, STATIC_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Ensure default avatar exists in /static/
DEFAULT_AVATAR_PATH = os.path.join(STATIC_FOLDER, 'default_avatar.png')
if not os.path.exists(DEFAULT_AVATAR_PATH):
    # Create a default 128x128 purple avatar with "U"
    img = Image.new('RGB', (128, 128), color=(139, 92, 246))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except IOError:
        font = ImageFont.load_default()
    draw.text((64, 64), "U", fill="white", font=font, anchor="mm")
    img.save(DEFAULT_AVATAR_PATH)

# --- DATABASE HELPERS ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        bio TEXT DEFAULT '',
        avatar_url TEXT DEFAULT '/static/default_avatar.png',
        theme_color TEXT DEFAULT '#a78bfa',
        bg_color TEXT DEFAULT '#0d0a1a',
        role TEXT DEFAULT 'user',
        is_banned INTEGER DEFAULT 0,
        mute_until TEXT DEFAULT '1970-01-01 00:00:00',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        is_online INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS friendships (
        requester_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (requester_id, target_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        subscriber_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (subscriber_id, target_user_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        chat_type TEXT NOT NULL, 
        target_id INTEGER,       
        type TEXT NOT NULL,      
        content TEXT,            
        filename TEXT,
        url TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        read_by TEXT DEFAULT '[]'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        owner_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS group_members (
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (group_id, user_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS global_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS wall_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        content TEXT,
        filename TEXT,
        url TEXT,
        post_type TEXT DEFAULT 'text',
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        html_content TEXT NOT NULL,
        is_public INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_wall_target ON wall_posts(target_user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sub_target ON subscriptions(target_user_id)')
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": "Unauthorized"}), 401
            return redirect('/login')
        
        conn = get_db()
        user = conn.execute('SELECT is_banned FROM users WHERE id=?', (flask_session['user_id'],)).fetchone()
        conn.close()
        if user and user['is_banned']:
            flask_session.clear()
            return redirect('/login?msg=banned')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            return redirect('/login')
        conn = get_db()
        user = conn.execute('SELECT role FROM users WHERE id=?', (flask_session['user_id'],)).fetchone()
        conn.close()
        if not user or user['role'] != 'admin':
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated_function

# --- INITIALIZATION ---
init_db()
conn = get_db()
conn.execute('UPDATE users SET is_online=0')
conn.commit()
conn.close()

SOUND_FILE = os.path.join(UPLOAD_FOLDER, 'notification.wav')
if not os.path.exists(SOUND_FILE):
    import math
    with wave.open(SOUND_FILE, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        samples = [int(32767 * (1 - i/6615) * (0.5 * math.sin(2*math.pi*800*i/44100))) for i in range(6615)]
        wav.writeframes(struct.pack('<' + 'h'*len(samples), *samples))

# --- ROUTES: AUTH ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json if request.is_json else request.form
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        
        if not username or not password or len(password) < 4:
             return jsonify({"error": "Invalid credentials"}), 400
        
        conn = get_db()
        count = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        role = 'admin' if count < 2 else 'user'
        
        # FIXED: Set default avatar path for all new users
        avatar_url = '/static/default_avatar.png'
        
        try:
            conn.execute('INSERT INTO users (username, password_hash, display_name, role, avatar_url) VALUES (?, ?, ?, ?, ?)',
                        (username, hash_password(password), username, role, avatar_url))
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            flask_session['user_id'] = user['id']
            flask_session['username'] = user['username']
            conn.close()
            return jsonify({"success": True, "redirect": "/"})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Username taken"}), 400
            
    return render_template_string(AUTH_HTML, mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json if request.is_json else request.form
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password_hash=?', 
                           (username, hash_password(password))).fetchone()
        if user and not user['is_banned']:
            flask_session['user_id'] = user['id']
            flask_session['username'] = user['username']
            conn.close()
            return jsonify({"success": True, "redirect": "/"})
        conn.close()
        return jsonify({"error": "Invalid credentials or Banned"}), 401
        
    return render_template_string(AUTH_HTML, mode='login')

@app.route('/logout')
def logout():
    if 'user_id' in flask_session:
        conn = get_db()
        conn.execute('UPDATE users SET is_online=0 WHERE id=?', (flask_session['user_id'],))
        conn.commit()
        conn.close()
        flask_session.clear()
    return redirect('/login')

# --- ROUTES: MAIN APP ---
@app.route('/')
@login_required
def index():
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (flask_session['user_id'],)).fetchone()
    conn.close()
    return render_template_string(MAIN_HTML, user=user)

@app.route('/api/me')
@login_required
def get_me():
    conn = get_db()
    user = conn.execute('SELECT id, username, display_name, bio, avatar_url, theme_color, bg_color, role FROM users WHERE id=?',
                       (flask_session['user_id'],)).fetchone()
    conn.close()
    return jsonify(dict(user))

@app.route('/api/user/<int:uid>')
@login_required
def get_user(uid):
    conn = get_db()
    me = flask_session['user_id']
    user = conn.execute('SELECT id, username, display_name, bio, avatar_url, theme_color, role, created_at, is_banned FROM users WHERE id=?',
                       (uid,)).fetchone()
    if user:
        req = conn.execute('SELECT status FROM friendships WHERE requester_id=? AND target_id=?', (me, uid)).fetchone()
        targ = conn.execute('SELECT status FROM friendships WHERE requester_id=? AND target_id=?', (uid, me)).fetchone()
        
        friend_status = 'none'
        if req and req['status'] == 'accepted': friend_status = 'friends'
        elif targ and targ['status'] == 'accepted': friend_status = 'friends'
        elif req and req['status'] == 'pending': friend_status = 'sent_request'
        elif targ and targ['status'] == 'pending': friend_status = 'received_request'
        
        is_subbed = bool(conn.execute('SELECT 1 FROM subscriptions WHERE subscriber_id=? AND target_user_id=?', (me, uid)).fetchone())
        subs_count = conn.execute('SELECT COUNT(*) as c FROM subscriptions WHERE target_user_id=?', (uid,)).fetchone()['c']
        
        res = dict(user)
        res['friend_status'] = friend_status
        res['is_subscribed'] = is_subbed
        res['subs_count'] = subs_count
        conn.close()
        return jsonify(res if user else {"error": "Not found"}), 200 if user else 404
    conn.close()
    return jsonify({"error": "Not found"}), 404

@app.route('/api/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = request.json if request.is_json else {}
    conn = get_db()
    updates = []
    params = []
    
    if 'display_name' in data:
         updates.append('display_name=?')
         params.append(str(data['display_name'])[:50])
    if 'bio' in data:
         updates.append('bio=?')
         params.append(str(data['bio'])[:500])
    if 'theme_color' in data:
         updates.append('theme_color=?')
         params.append(str(data['theme_color']))
    if 'bg_color' in data:
         updates.append('bg_color=?')
         params.append(str(data['bg_color']))
         
    if 'avatar' in request.files:
         file = request.files['avatar']
         if file and file.filename:
             ext = secure_filename(file.filename).split('.')[-1].lower()
             if ext in ['jpg', 'jpeg', 'png', 'webp']:
                 fname = f"avatar_{flask_session['user_id']}_{int(datetime.now().timestamp())}.{ext}"
                 path = os.path.join(UPLOAD_FOLDER, fname)
                 file.save(path)
                 img = Image.open(path)
                 img.thumbnail((256, 256))
                 img.save(path)
                 updates.append('avatar_url=?')
                 params.append(f"/uploads/{fname}")
                 
    if updates:
         params.append(flask_session['user_id'])
         conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
         conn.commit()
    conn.close()
    return jsonify({"success": True})

# --- ROUTES: FRIENDSHIPS & SUBSCRIPTIONS ---
@app.route('/api/friend_action', methods=['POST'])
@login_required
def friend_action():
    data = request.json
    action = data.get('action')
    target_uid = data.get('target_id')
    me = flask_session['user_id']
    
    if me == target_uid:
        return jsonify({"error": "Cannot interact with self"}), 400
        
    conn = get_db()
    if action == 'send_request':
        existing = conn.execute('SELECT status FROM friendships WHERE requester_id=? AND target_id=?', (me, target_uid)).fetchone()
        if existing:
            conn.close(); return jsonify({"error": "Request already sent"}), 400
        conn.execute('INSERT INTO friendships (requester_id, target_id, status) VALUES (?,?,?)', (me, target_uid, 'pending'))
        res = {"status": "sent"}
    elif action == 'accept':
        conn.execute("UPDATE friendships SET status='accepted' WHERE requester_id=? AND target_id=?", (target_uid, me))
        rev = conn.execute('SELECT 1 FROM friendships WHERE requester_id=? AND target_id=?', (me, target_uid)).fetchone()
        if not rev:
            conn.execute('INSERT OR IGNORE INTO friendships (requester_id, target_id, status) VALUES (?,?,?)', (me, target_uid, 'accepted'))
        res = {"status": "accepted"}
    elif action == 'decline':
        conn.execute('DELETE FROM friendships WHERE requester_id=? AND target_id=?', (target_uid, me))
        conn.execute('DELETE FROM friendships WHERE requester_id=? AND target_id=?', (me, target_uid))
        res = {"status": "declined"}
    elif action == 'unfriend':
        conn.execute('DELETE FROM friendships WHERE requester_id=? AND target_id=?', (me, target_uid))
        conn.execute('DELETE FROM friendships WHERE requester_id=? AND target_id=?', (target_uid, me))
        res = {"status": "unfriended"}
        
    conn.commit()
    conn.close()
    return jsonify(res)

@app.route('/api/all_users')
@login_required
def get_all_users():
    conn = get_db()
    me = flask_session['user_id']
    users = conn.execute('SELECT id, username, display_name, avatar_url FROM users WHERE id!=?', (me,)).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/notifications')
@login_required
def get_notifications():
    conn = get_db()
    me = flask_session['user_id']
    requests = conn.execute('''
        SELECT f.*, u.username, u.display_name, u.avatar_url
        FROM friendships f
        JOIN users u ON u.id = f.requester_id
        WHERE f.target_id = ? AND f.status = 'pending'
        ORDER BY f.created_at DESC
    ''', (me,)).fetchall()
    count = len(requests)
    conn.close()
    return jsonify({
        "count": count,
        "requests": [dict(r) for r in requests]
    })

@app.route('/api/subscribe/<int:uid>', methods=['POST'])
@login_required
def subscribe(uid):
    conn = get_db()
    me = flask_session['user_id']
    try:
        conn.execute('INSERT INTO subscriptions (subscriber_id, target_user_id) VALUES (?,?)', (me, uid))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except:
        conn.execute('DELETE FROM subscriptions WHERE subscriber_id=? AND target_user_id=?', (me, uid))
        conn.commit()
        conn.close()
        return jsonify({"unsubscribed": True})

# --- ROUTES: FEED (SUBSCRIPTIONS WALL) ---
@app.route('/api/feed')
@login_required
def get_feed():
    conn = get_db()
    me = flask_session['user_id']
    posts = conn.execute('''
        SELECT p.*, u.username, u.display_name, u.avatar_url, u.theme_color, t.username as target_username
        FROM wall_posts p
        JOIN users u ON u.id = p.author_id
        JOIN users t ON t.id = p.target_user_id
        JOIN subscriptions s ON s.target_user_id = p.target_user_id
        WHERE s.subscriber_id = ?
        ORDER BY p.timestamp DESC
        LIMIT 100
    ''', (me,)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])

# --- ROUTES: MESSAGING ---
@app.route('/api/chats')
@login_required
def get_chats():
    conn = get_db()
    uid = flask_session['user_id']
    
    # Get private chats (friends only)
    privates = conn.execute('''
         SELECT DISTINCT 
             CASE WHEN m.sender_id = ? THEN m.target_id ELSE m.sender_id END as other_id,
             u.username, u.display_name, u.avatar_url, u.is_online,
             (SELECT content FROM messages WHERE chat_type='private' 
              AND ((sender_id=? AND target_id=u.id) OR (sender_id=u.id AND target_id=?))
              ORDER BY timestamp DESC LIMIT 1) as last_msg,
             (SELECT timestamp FROM messages WHERE chat_type='private' 
              AND ((sender_id=? AND target_id=u.id) OR (sender_id=u.id AND target_id=?))
              ORDER BY timestamp DESC LIMIT 1) as last_ts
         FROM messages m
         JOIN users u ON u.id = CASE WHEN m.sender_id = ? THEN m.target_id ELSE m.sender_id END
         WHERE m.chat_type='private' AND (m.sender_id=? OR m.target_id=?)
         AND EXISTS (SELECT 1 FROM friendships WHERE requester_id=? AND target_id=u.id AND status='accepted'
                     UNION SELECT 1 FROM friendships WHERE requester_id=u.id AND target_id=? AND status='accepted')
         ORDER BY last_ts DESC
     ''', [uid]*10).fetchall()
     
    channels = conn.execute('SELECT * FROM global_channels ORDER BY name ASC').fetchall()
    
    groups = conn.execute('''
        SELECT g.*, gm.joined_at
        FROM groups g
        JOIN group_members gm ON gm.group_id = g.id
        WHERE gm.user_id = ?
        ORDER BY g.name ASC
    ''', (uid,)).fetchall()
    
    conn.close()
    return jsonify({
        "privates": [dict(p) for p in privates],
        "groups": [dict(g) for g in groups],
        "channels": [dict(c) for c in channels]
    })

@app.route('/api/messages/<ctype>/<int:tid>')
@login_required
def get_messages(ctype, tid):
    conn = get_db()
    uid = flask_session['user_id']
    
    if ctype == 'global':
         msgs = conn.execute('SELECT m.*, u.username, u.display_name, u.avatar_url, u.theme_color FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.chat_type="global" ORDER BY m.id ASC LIMIT 200').fetchall()
    elif ctype == 'channel':
         msgs = conn.execute('SELECT m.*, u.username, u.display_name, u.avatar_url, u.theme_color FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.chat_type="channel" AND m.target_id=? ORDER BY m.id ASC LIMIT 200', (tid,)).fetchall()
    elif ctype == 'private':
         # FIXED: Corrected SQL syntax for accepted status
         is_friend = conn.execute('''SELECT 1 FROM friendships 
                                    WHERE ((requester_id=? AND target_id=?) OR (requester_id=? AND target_id=?)) 
                                    AND status='accepted' ''' , (uid, tid, tid, uid)).fetchone()
         if not is_friend:
             conn.close(); return jsonify({"error": "Not friends"}), 403
         msgs = conn.execute('''SELECT m.*, u.username, u.display_name, u.avatar_url, u.theme_color 
                               FROM messages m JOIN users u ON u.id=m.sender_id 
                               WHERE m.chat_type="private" AND ((m.sender_id=? AND m.target_id=?) OR (m.sender_id=? AND m.target_id=?))
                               ORDER BY m.id ASC LIMIT 200''', (uid, tid, tid, uid)).fetchall()
         conn.execute("UPDATE messages SET read_by=json_insert(read_by, '$[#]', ?) WHERE chat_type='private' AND sender_id=? AND target_id=? AND json_array_length(read_by)=0", (str(uid), tid, uid))
         conn.commit()
    elif ctype == 'group':
         member = conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND user_id=?', (tid, uid)).fetchone()
         if not member:
             conn.close()
             return jsonify({"error": "Not a member"}), 403
         msgs = conn.execute('''SELECT m.*, u.username, u.display_name, u.avatar_url, u.theme_color 
                               FROM messages m JOIN users u ON u.id=m.sender_id 
                               WHERE m.chat_type="group" AND m.target_id=?
                               ORDER BY m.id ASC LIMIT 200''', (tid,)).fetchall()
    else:
        conn.close()
        return jsonify([])
        
    conn.close()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.json
    uid = flask_session['user_id']
    conn = get_db()
    
    user = conn.execute('SELECT is_banned, mute_until FROM users WHERE id=?', (uid,)).fetchone()
    if user['is_banned']:
        conn.close(); return jsonify({"error": "Banned"}), 403
    if datetime.now() < datetime.fromisoformat(user['mute_until']):
        conn.close(); return jsonify({"error": "Muted"}), 403
        
    ctype = data.get('type', 'global')
    target = data.get('target_id')
    text = data.get('text', '').strip()
    
    if not text: 
        conn.close(); return jsonify({"error": "Empty"}), 400
        
    if ctype == 'private':
        if target == uid: 
            conn.close(); return jsonify({"error": "Cannot msg self"}), 400
        # FIXED: Corrected SQL syntax
        is_friend = conn.execute('''SELECT 1 FROM friendships 
                                    WHERE ((requester_id=? AND target_id=?) OR (requester_id=? AND target_id=?)) 
                                    AND status='accepted' ''' , (uid, target, target, uid)).fetchone()
        if not is_friend:
            conn.close(); return jsonify({"error": "Must be friends to DM"}), 403
        conn.execute('INSERT INTO messages (sender_id, chat_type, target_id, type, content) VALUES (?,?,?,?,?)',
                    (uid, 'private', target, 'text', text))
    elif ctype == 'group':
        member = conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND user_id=?', (target, uid)).fetchone()
        if not member:
            conn.close(); return jsonify({"error": "Not member"}), 403
        conn.execute('INSERT INTO messages (sender_id, chat_type, target_id, type, content) VALUES (?,?,?,?,?)',
                    (uid, 'group', target, 'text', text))
    elif ctype == 'channel':
        conn.execute('INSERT INTO messages (sender_id, chat_type, target_id, type, content) VALUES (?,?,?,?,?)',
                    (uid, 'channel', target, 'text', text))
    else:
        conn.execute('INSERT INTO messages (sender_id, chat_type, type, content) VALUES (?,?,?,?)',
                    (uid, 'global', 'text', text))
                    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    uid = flask_session['user_id']
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "Empty"}), 400
    
    filename = secure_filename(file.filename)
    ts = int(datetime.now().timestamp())
    unique = f"{ts}_{uid}_{filename}"
    path = os.path.join(UPLOAD_FOLDER, unique)
    file.save(path)
    
    ext = filename.split('.')[-1].lower()
    mtype = 'file'
    preview = ''
    
    if ext in ['jpg','jpeg','png','gif','webp']: mtype = 'image'
    elif ext in ['txt','md','py','json']: 
        mtype = 'text_file'
        try: preview = open(path, 'r', encoding='utf-8', errors='ignore').read(500)
        except: pass
        
    conn = get_db()
    conn.execute('INSERT INTO messages (sender_id, chat_type, target_id, type, content, filename, url) VALUES (?,?,?,?,?,?,?)',
                (uid, 'global', None, mtype, preview, filename, f"/uploads/{unique}"))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "url": f"/uploads/{unique}"})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(STATIC_FOLDER, filename)

# --- ROUTES: GROUPS ---
@app.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    data = request.json
    name = str(data.get('name', '')).strip()
    members = data.get('members', [])
    if not name: return jsonify({"error": "Name required"}), 400
    
    conn = get_db()
    gid = conn.execute('INSERT INTO groups (name, owner_id) VALUES (?,?)', (name, flask_session['user_id'])).lastrowid
    conn.execute('INSERT INTO group_members (group_id, user_id) VALUES (?,?)', (gid, flask_session['user_id']))
    
    for mid in members:
        try: conn.execute('INSERT INTO group_members (group_id, user_id) VALUES (?,?)', (gid, int(mid)))
        except: pass
        
    conn.commit()
    conn.close()
    return jsonify({"id": gid, "success": True})

@app.route('/api/group/<int:gid>/info', methods=['GET', 'PUT'])
@login_required
def group_info(gid):
    conn = get_db()
    uid = flask_session['user_id']
    is_owner = conn.execute('SELECT 1 FROM groups WHERE id=? AND owner_id=?', (gid, uid)).fetchone()
    
    if request.method == 'GET':
        group = conn.execute('SELECT * FROM groups WHERE id=?', (gid,)).fetchone()
        members = conn.execute('''SELECT u.id, u.username, u.display_name, u.avatar_url 
                                 FROM group_members gm JOIN users u ON u.id=gm.user_id 
                                 WHERE gm.group_id=?''', (gid,)).fetchall()
        all_users = conn.execute('SELECT id, username, display_name, avatar_url FROM users WHERE id!=?', (uid,)).fetchall()
        conn.close()
        return jsonify({
            "group": dict(group) if group else None, 
            "members": [dict(m) for m in members], 
            "all_users": [dict(u) for u in all_users], 
            "is_owner": bool(is_owner)
        })
        
    if not is_owner:
        conn.close()
        return jsonify({"error": "Only owner can edit"}), 403
        
    data = request.json
    if 'name' in data:
        conn.execute('UPDATE groups SET name=? WHERE id=?', (data['name'], gid))
    if 'description' in data:
        conn.execute('UPDATE groups SET description=? WHERE id=?', (data['description'], gid))
        
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/group/<int:gid>/members', methods=['POST', 'DELETE'])
@login_required
def manage_group_members(gid):
    conn = get_db()
    uid = flask_session['user_id']
    is_owner = conn.execute('SELECT 1 FROM groups WHERE id=? AND owner_id=?', (gid, uid)).fetchone()
    
    if not is_owner:
        conn.close()
        return jsonify({"error": "Only owner can manage"}), 403
        
    target_uid = request.json.get('user_id')
    
    if request.method == 'POST':
        try: conn.execute('INSERT INTO group_members (group_id, user_id) VALUES (?,?)', (gid, target_uid))
        except: pass
    elif request.method == 'DELETE':
        if target_uid != uid: 
            conn.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (gid, target_uid))
            
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# --- ROUTES: ADMIN GLOBAL CHANNELS ---
@app.route('/api/admin/channels', methods=['GET', 'POST', 'DELETE'])
@admin_required
def admin_channels():
    conn = get_db()
    if request.method == 'GET':
        channels = conn.execute('SELECT * FROM global_channels ORDER BY id ASC').fetchall()
        conn.close()
        return jsonify([dict(c) for c in channels])
        
    if request.method == 'POST':
        data = request.json
        name = str(data.get('name', '')).strip()
        desc = str(data.get('description', '')).strip()
        if not name:
            conn.close(); return jsonify({"error": "Name required"}), 400
        conn.execute('INSERT INTO global_channels (name, description, created_by) VALUES (?,?,?)', 
                    (name, desc, flask_session['user_id']))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
        
    if request.method == 'DELETE':
        cid = request.json.get('id')
        conn.execute('DELETE FROM global_channels WHERE id=?', (cid,))
        conn.execute('DELETE FROM messages WHERE chat_type="channel" AND target_id=?', (cid,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

# --- ROUTES: WALL ---
@app.route('/api/wall/<int:uid>', methods=['GET', 'POST'])
@login_required
def wall(uid):
    conn = get_db()
    me = flask_session['user_id']
    
    if request.method == 'POST':
        if uid != me:
            conn.close()
            return jsonify({"error": "Can only post on your own wall"}), 403
            
        content = str(request.form.get('content', '')).strip()
        post_type = 'text'
        filename = None
        url = None
        
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                ext = secure_filename(file.filename).split('.')[-1].lower()
                if ext in ['jpg','jpeg','png','gif','webp']: post_type = 'image'
                fname = f"wall_{me}_{int(datetime.now().timestamp())}.{ext}"
                path = os.path.join(UPLOAD_FOLDER, fname)
                file.save(path)
                filename = file.filename
                url = f"/uploads/{fname}"
                
        if content or url:
            conn.execute('INSERT INTO wall_posts (author_id, target_user_id, content, filename, url, post_type) VALUES (?,?,?,?,?,?)',
                        (me, uid, content, filename, url, post_type))
            conn.commit()
            
    posts = conn.execute('''SELECT p.*, u.username, u.display_name, u.avatar_url 
                           FROM wall_posts p JOIN users u ON u.id=p.author_id 
                           WHERE p.target_user_id=? ORDER BY p.timestamp DESC LIMIT 50''', (uid,)).fetchall()
    conn.close()
    return jsonify({"posts": [dict(p) for p in posts]})

# --- ROUTES: CUSTOM PAGES ---
@app.route('/page/<slug>')
def view_page(slug):
    conn = get_db()
    page = conn.execute('SELECT * FROM custom_pages WHERE slug=?', (slug,)).fetchone()
    if not page:
        conn.close()
        return "Page not found", 404
        
    uid = flask_session.get('user_id')
    is_owner = (uid == page['user_id'])
    
    if not page['is_public']:
        if not uid:
            conn.close()
            return redirect('/login')
        is_friend = conn.execute('''SELECT 1 FROM friendships 
                                   WHERE ((requester_id=? AND target_id=?) OR (requester_id=? AND target_id=?)) 
                                   AND status='accepted' ''' , (uid, page['user_id'], page['user_id'], uid)).fetchone()
        if not is_owner and not is_friend:
            conn.close()
            return render_template_string(PAGE_403_HTML)
            
    conn.close()
    return render_template_string(CUSTOM_PAGE_HTML, page=page)

@app.route('/api/my_pages', methods=['GET', 'POST'])
@login_required
def manage_my_pages():
    conn = get_db()
    uid = flask_session['user_id']
    role = conn.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()['role']
    limit = 5 if role == 'admin' else 2
    
    if request.method == 'POST':
        if 'html_file' in request.files:
            file = request.files['html_file']
            if file and file.filename.endswith('.html'):
                current_count = conn.execute('SELECT COUNT(*) as c FROM custom_pages WHERE user_id=?', (uid,)).fetchone()['c']
                if current_count >= limit:
                    conn.close(); return jsonify({"error": f"Limit reached ({limit})"}), 400
                content = file.read().decode('utf-8', errors='ignore')
                title = str(request.form.get('title', 'My Page')).strip()
                slug = re.sub(r'[^a-z0-9\-]', '-', title.lower()) + f"-{uid}"
                is_pub = int(request.form.get('is_public', 1))
                conn.execute('INSERT INTO custom_pages (user_id, title, slug, html_content, is_public) VALUES (?,?,?,?,?)',
                            (uid, title, slug, content, is_pub))
                conn.commit()
                conn.close()
                return jsonify({"success": True})
                
        data = request.json
        if data:
            action = data.get('action', 'create')
            if action == 'delete':
                conn.execute('DELETE FROM custom_pages WHERE id=? AND user_id=?', (data.get('id'), uid))
                conn.commit()
                conn.close()
                return jsonify({"success": True})
                
            title = str(data.get('title','')).strip()
            html = str(data.get('html',''))
            is_pub = int(data.get('is_public', 1))
            slug = re.sub(r'[^a-z0-9\-]', '-', title.lower()) + f"-{uid}"
            
            if not title:
                conn.close(); return jsonify({"error": "Title required"}), 400
                
            current_count = conn.execute('SELECT COUNT(*) as c FROM custom_pages WHERE user_id=?', (uid,)).fetchone()['c']
            edit_id = data.get('id')
            
            if not edit_id and current_count >= limit:
                conn.close(); return jsonify({"error": f"Limit reached ({limit})"}), 400
                
            try:
                if edit_id:
                    conn.execute('UPDATE custom_pages SET title=?, slug=?, html_content=?, is_public=? WHERE id=? AND user_id=?',
                                (title, slug, html, is_pub, edit_id, uid))
                else:
                    conn.execute('INSERT INTO custom_pages (user_id, title, slug, html_content, is_public) VALUES (?,?,?,?,?)',
                                (uid, title, slug, html, is_pub))
                conn.commit()
                conn.close()
                return jsonify({"success": True})
            except Exception as e:
                conn.close()
                return jsonify({"error": str(e)}), 400
                
    pages = conn.execute('SELECT * FROM custom_pages WHERE user_id=? ORDER BY created_at DESC', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in pages])

# --- ADMIN PANEL ---
@app.route('/admin')
@admin_required
def admin_panel():
    conn = get_db()
    users = conn.execute('SELECT * FROM users ORDER BY id ASC').fetchall()
    conn.close()
    return render_template_string(ADMIN_HTML, users=[dict(u) for u in users])

@app.route('/admin/action', methods=['POST'])
@admin_required
def admin_action():
    data = request.json
    action = data.get('action')
    conn = get_db()
    
    if action == 'delete_user':
        conn.execute('DELETE FROM users WHERE id=?', (data.get('id'),))
    elif action == 'toggle_admin':
        curr = conn.execute('SELECT role FROM users WHERE id=?', (data.get('id'),)).fetchone()
        new_role = 'user' if curr['role'] == 'admin' else 'admin'
        conn.execute('UPDATE users SET role=? WHERE id=?', (new_role, data.get('id')))
    elif action == 'ban_user':
        curr = conn.execute('SELECT is_banned FROM users WHERE id=?', (data.get('id'),)).fetchone()
        new_status = 0 if curr['is_banned'] else 1
        conn.execute('UPDATE users SET is_banned=? WHERE id=?', (new_status, data.get('id')))
    elif action == 'mute_user':
        minutes = int(data.get('minutes', 60))
        mute_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        conn.execute('UPDATE users SET mute_until=? WHERE id=?', (mute_until, data.get('id')))
        
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# --- HTML TEMPLATES ---
AUTH_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YuuY Chat - {{ mode|capitalize }}</title>
<link rel="icon" href="/static/favicon.ico">
<style>
:root { --bg: #0d0a1a; --card: #1a1333; --accent: #a78bfa; --text: #f5f3ff; }
body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center; background: var(--bg); color:var(--text); font-family:sans-serif; }
.auth-box { background:var(--card); padding:2rem; border-radius:16px; width:100%; max-width:350px; box-shadow:0 10px 30px rgba(0,0,0,0.5); border:1px solid #2d2452; }
h2 { text-align:center; margin-bottom:1.5rem; color:var(--accent); }
input { width:100%; padding:12px; margin-bottom:1rem; border-radius: 8px; border:1px solid #2d2452; background:#0d0a1a; color:white; box-sizing:border-box; }
button { width:100%; padding:12px; border:none; border-radius:8px; background:var(--accent); color:white; font-weight:bold; cursor:pointer; transition:0.2s; }
button:hover { opacity:0.9; transform:translateY(-1px); }
.switch { text-align:center; margin-top:1rem; font-size:0.9rem; }
.switch a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<div class="auth-box">
<h2>YuuY {{ mode|capitalize }}</h2>
<form id="authForm">
<input type="text" id="username" placeholder="Username" required autocomplete="off">
<input type="password" id="password" placeholder="Password" required>
<button type="submit">{{ mode|capitalize }}</button>
</form>
<div class="switch">
{% if mode == 'login' %} No account? <a href="/register">Register</a>
{% else %} Have account? <a href="/login">Login</a> {% endif %}
</div>
</div>
<script>
document.getElementById('authForm').onsubmit = async (e) => {
e.preventDefault();
const u = document.getElementById('username').value;
const p = document.getElementById('password').value;
const res = await fetch(window.location.pathname, {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({username:u, password:p})
});
const d = await res.json();
if(d.success) window.location.href = d.redirect;
else alert(d.error);
};
</script>
</body>
</html>
"""

MAIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YuuY Chat</title>
<link rel="icon" href="/static/favicon.ico">
<style>
:root {
--bg: {{ user.bg_color }}; --card: #1a1333; --border: #2d2452;
--accent: {{ user.theme_color }}; --text: #f5f3ff; --sub: #a5a0c0;
}
* { box-sizing:border-box; margin:0; padding:0; outline:none; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,sans-serif; height:100vh; overflow:hidden; display:flex; transition:background 0.3s; }

/* Sidebar */
.sidebar { width:280px; background:var(--card); border-right:1px solid var(--border); display:flex; flex-direction:column; z-index:10; position:relative; }
.profile-header { padding:16px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:12px; cursor:pointer; transition:0.2s; }
.profile-header:hover { background:rgba(255,255,255,0.03); }
.avatar { width:48px; height:48px; border-radius:50%; object-fit:cover; border:2px solid var(--accent); }
.uname { font-weight:bold; font-size:0.95rem; }
.urole { font-size:0.7rem; color:var(--accent); text-transform:uppercase; letter-spacing:0.5px; }

.nav-tabs { display:flex; border-bottom:1px solid var(--border); flex-wrap:wrap; }
.nav-tab { flex:1; min-width:60px; padding:14px; text-align:center; cursor:pointer; font-size:0.8rem; color:var(--sub); transition:0.2s; font-weight:600; }
.nav-tab:hover { color:var(--text); background:rgba(255,255,255,0.02); }
.nav-tab.active { color:var(--accent); border-bottom:2px solid var(--accent); background:rgba(167,139,250,0.05); }

.list-container { flex:1; overflow-y:auto; position:relative; }
.list-item { padding:12px 16px; display:flex; align-items:center; gap:12px; cursor:pointer; border-bottom:1px solid rgba(45,36,82,0.3); transition:0.2s; }
.list-item:hover, .list-item.active { background:rgba(167,139,250,0.1); border-left:3px solid var(--accent); padding-left:13px; }
.list-item img { width:40px; height:40px; border-radius:50%; object-fit:cover; background:#231b42; }
.list-info { flex:1; min-width:0; }
.list-name { font-weight:600; font-size:0.9rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.list-preview { font-size:0.75rem; color:var(--sub); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
.online-dot { width:8px; height:8px; border-radius:50%; background:#6ee7b7; box-shadow:0 0 6px #6ee7b7; }

.sidebar-footer { padding:12px; border-top:1px solid var(--border); display:flex; gap:8px; }
.sidebar-footer button, .sidebar-footer a { flex:1; padding:8px; border-radius:8px; border:1px solid var(--border); background:transparent; color:var(--sub); cursor:pointer; font-size:0.8rem; text-align:center; text-decoration:none; display:flex; align-items:center; justify-content:center; transition:0.2s; }
.sidebar-footer button:hover, .sidebar-footer a:hover { background:var(--border); color:var(--text); }

/* Main Area */
.main-area { flex:1; display:flex; flex-direction:column; position:relative; background:linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.2) 100%); }
.chat-header { padding:14px 20px; background:var(--card); border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; backdrop-filter:blur(10px); }
.chat-title { font-weight:bold; font-size:1.1rem; display:flex; align-items:center; gap:10px; }
.header-actions { display:flex; align-items:center; gap:8px; }
.header-actions button { background:none; border:none; color:var(--sub); font-size:1.2rem; cursor:pointer; transition:0.2s; padding:4px; border-radius:4px; position:relative; }
.header-actions button:hover { color:var(--accent); background:rgba(167,139,250,0.1); }

.notif-badge { position:absolute; top:-2px; right:-2px; background:#ef4444; color:white; font-size:0.6rem; font-weight:bold; padding:2px 5px; border-radius:10px; min-width:16px; text-align:center; display:none; }

.messages { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:12px; scroll-behavior:smooth; }

/* Message Layout with Avatars */
.msg-row { display:flex; gap:10px; max-width:85%; animation:fadeIn 0.3s ease; }
.msg-row.mine { align-self:flex-end; flex-direction:row-reverse; }
.msg-row.theirs { align-self:flex-start; }
.msg-avatar { width:36px; height:36px; border-radius:50%; object-fit:cover; flex-shrink:0; cursor:pointer; border:2px solid var(--border); }
.msg-row.mine .msg-avatar { border-color:var(--accent); }
.msg-bubble { padding:10px 14px; border-radius:16px; font-size:0.9rem; line-height:1.4; word-wrap:break-word; position:relative; min-width:0; }
.msg-row.mine .msg-bubble { background:var(--accent); color:white; border-bottom-right-radius:4px; box-shadow:0 4px 12px rgba(167,139,250,0.2); }
.msg-row.theirs .msg-bubble { background:var(--card); border:1px solid var(--border); border-bottom-left-radius:4px; }
.msg-sender { font-size:0.7rem; opacity:0.8; margin-bottom:4px; font-weight:bold; }
.msg-time { font-size:0.65rem; opacity:0.7; text-align:right; margin-top:4px; }
.msg-bubble img { max-width:100%; border-radius:8px; margin-top:6px; cursor:pointer; transition:0.2s; }
.msg-bubble img:hover { transform:scale(1.02); }

@keyframes fadeIn { from{opacity:0;transform:translateY(10px);} to{opacity:1;transform:translateY(0);} }

/* Feed Styles */
.feed-post { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:12px; max-width:600px; align-self:center; width:100%; }
.feed-header { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.feed-avatar { width:32px; height:32px; border-radius:50%; object-fit:cover; cursor:pointer; }
.feed-author { font-weight:bold; font-size:0.9rem; }
.feed-target { font-size:0.8rem; color:var(--sub); }
.feed-content { font-size:0.95rem; line-height:1.5; word-wrap:break-word; margin-bottom:8px; }
.feed-img { max-width:100%; border-radius:8px; margin-top:8px; }
.feed-time { font-size:0.7rem; color:var(--sub); text-align:right; }

.input-bar { padding:16px; background:var(--card); border-top:1px solid var(--border); display:flex; gap:10px; }
.input-bar input { flex:1; padding:12px 16px; border-radius:24px; border:1px solid var(--border); background:var(--bg); color:white; transition:0.2s; }
.input-bar input:focus { border-color:var(--accent); box-shadow:0 0 0 3px rgba(167,139,250,0.1); }
.btn-send { width:44px; height:44px; border-radius:50%; border:none; background:var(--accent); color:white; cursor:pointer; font-size:1.2rem; transition:0.2s; display:flex; align-items:center; justify-content:center; }
.btn-send:hover { transform:scale(1.05); box-shadow:0 4px 12px rgba(167,139,250,0.3); }
.btn-file { width:44px; height:44px; border-radius:50%; border:1px solid var(--border); background:transparent; color:var(--sub); cursor:pointer; display:flex; align-items:center; justify-content:center; transition:0.2s; }
.btn-file:hover { background:var(--border); color:var(--text); }

/* Modal */
.modal-overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:100; display:none; align-items:center; justify-content:center; backdrop-filter:blur(4px); animation:fadeIn 0.2s; }
.modal { background:var(--card); padding:24px; border-radius:16px; width:90%; max-width:450px; border:1px solid var(--border); box-shadow:0 20px 40px rgba(0,0,0,0.4); max-height:90vh; overflow-y:auto; }
.modal h3 { margin-bottom:16px; color:var(--accent); font-size:1.2rem; }
.modal label { display:block; font-size:0.8rem; color:var(--sub); margin-bottom:6px; margin-top:12px; }
.modal input, .modal textarea, .modal select { width:100%; padding:10px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:white; box-sizing:border-box; transition:0.2s; }
.modal input:focus, .modal textarea:focus { border-color:var(--accent); }
.modal-btns { display:flex; gap:10px; justify-content:flex-end; margin-top:20px; }
.modal-btns button { padding:10px 20px; border-radius:8px; border:none; cursor:pointer; font-weight:bold; transition:0.2s; }
.btn-primary { background:var(--accent); color:white; }
.btn-primary:hover { opacity:0.9; transform:translateY(-1px); }
.btn-secondary { background:transparent; border:1px solid var(--border); color:var(--sub); }
.btn-secondary:hover { background:var(--border); color:var(--text); }
.btn-danger { background:#ef4444; color:white; }
.btn-danger:hover { background:#dc2626; }
.btn-success { background:#6ee7b7; color:#000; }
.btn-success:hover { background:#34d399; }

/* Profile View */
.pv-header { display:flex; align-items:center; gap:20px; margin-bottom:24px; padding-bottom:20px; border-bottom:1px solid var(--border); }
.pv-avatar { width:100px; height:100px; border-radius:50%; object-fit:cover; border:3px solid var(--accent); box-shadow:0 0 20px rgba(167,139,250,0.2); }
.pv-info h2 { margin-bottom:4px; font-size:1.5rem; }
.pv-bio { color:var(--sub); font-size:0.9rem; margin-bottom:8px; line-height:1.4; }
.pv-stats { display:flex; gap:16px; font-size:0.8rem; color:var(--accent); font-weight:600; align-items:center; flex-wrap:wrap; }
.wall-input { margin-bottom:20px; }
.wall-input textarea { width:100%; padding:12px; border-radius:12px; border:1px solid var(--border); background:var(--card); color:white; resize:none; height:80px; margin-bottom:8px; }
.wall-post { background:var(--card); padding:16px; border-radius:12px; margin-bottom:12px; border:1px solid var(--border); transition:0.2s; }
.wall-post:hover { border-color:var(--accent); }
.wp-author { font-weight:bold; font-size:0.85rem; margin-bottom:6px; display:flex; align-items:center; gap:8px; }
.wp-author img { width:24px; height:24px; border-radius:50%; }
.wp-content { font-size:0.9rem; line-height:1.5; word-wrap:break-word; margin-bottom:8px; }
.wp-img { max-width:100%; border-radius:8px; margin-top:8px; }
.wp-time { font-size:0.7rem; color:var(--sub); margin-top:8px; }

/* Pages List */
.pages-list { display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:12px; padding:20px; }
.page-card { background:var(--card); padding:16px; border-radius:12px; border:1px solid var(--border); cursor:pointer; transition:0.2s; text-decoration:none; color:inherit; display:block; position:relative; }
.page-card:hover { transform:translateY(-2px); border-color:var(--accent); box-shadow:0 4px 12px rgba(0,0,0,0.2); }
.page-card h4 { margin-bottom:4px; color:var(--accent); }
.page-card span { font-size:0.75rem; color:var(--sub); }
.page-badge { position:absolute; top:10px; right:10px; font-size:0.6rem; padding:2px 6px; border-radius:4px; background:var(--bg); border:1px solid var(--border); }
.page-badge.private { color:#fca5a5; border-color:#fca5a5; }
.page-badge.public { color:#6ee7b7; border-color:#6ee7b7; }

/* Notifications Panel */
.notif-panel { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:12px; max-width:600px; align-self:center; width:100%; }
.notif-item { display:flex; align-items:center; gap:12px; padding:12px; border-bottom:1px solid var(--border); }
.notif-item:last-child { border-bottom:none; }
.notif-avatar { width:40px; height:40px; border-radius:50%; object-fit:cover; }
.notif-text { flex:1; font-size:0.9rem; }
.notif-actions { display:flex; gap:8px; }

/* NEW DM GRID STYLES */
.dm-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
    padding: 20px;
}
.dm-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    cursor: pointer;
    transition: 0.2s;
    position: relative;
}
.dm-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.dm-card img {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    object-fit: cover;
    margin-bottom: 12px;
    border: 2px solid var(--border);
}
.dm-card:hover img {
    border-color: var(--accent);
}
.dm-name {
    font-weight: bold;
    font-size: 1rem;
    margin-bottom: 4px;
    color: var(--text);
}
.dm-last-msg {
    font-size: 0.8rem;
    color: var(--sub);
    max-height: 40px;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.dm-online {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #6ee7b7;
    box-shadow: 0 0 6px #6ee7b7;
}

/* Add Friend Button in DM Header */
.add-dm-btn {
    background: var(--accent);
    color: white;
    border: none;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.2rem;
    cursor: pointer;
    transition: 0.2s;
}
.add-dm-btn:hover {
    transform: scale(1.1);
    box-shadow: 0 0 10px rgba(167,139,250,0.5);
}

/* Group Menu Button (3 lines) */
.group-menu-btn {
    background: transparent;
    border: none;
    color: var(--sub);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0 8px;
    transition: 0.2s;
}
.group-menu-btn:hover {
    color: var(--accent);
}

/* Mobile Responsive */
@media(max-width:768px) {
    .sidebar { position:absolute; height:100%; transform:translateX(-100%); transition:0.3s cubic-bezier(0.16, 1, 0.3, 1); box-shadow:4px 0 20px rgba(0,0,0,0.5); }
    .sidebar.open { transform:translateX(0); }
    .msg-row { max-width:90%; }
    .burger-menu { display:block !important; }
    .dm-grid { grid-template-columns: 1fr; }
}
.burger-menu { display:none; }
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar" id="sidebar">
    <div class="profile-header" onclick="openProfile({{ user.id }})">
        <img src="{{ user.avatar_url }}" class="avatar" id="myAvatar">
        <div>
            <div class="uname">{{ user.display_name }}</div>
            <div class="urole">{{ user.role }}</div>
        </div>
    </div>
    <div class="nav-tabs">
        <div class="nav-tab active" onclick="switchTab('global', this)">Global</div>
        <div class="nav-tab" onclick="switchTab('private', this)">DMs</div>
        <div class="nav-tab" onclick="switchTab('groups', this)">Groups</div>
        <div class="nav-tab" onclick="switchTab('feed', this)">Feed</div>
        <div class="nav-tab" onclick="switchTab('pages', this)">Pages</div>
    </div>
    <div class="list-container" id="chatList"></div>
    <div class="sidebar-footer">
        <button onclick="openModal('createGroup')">+ Group</button>
        <button onclick="openModal('editProfile')">Edit</button>
        {% if user.role == 'admin' %}
        <a href="/admin">Admin</a>
        {% endif %}
        <a href="/logout">Exit</a>
    </div>
</div>

<!-- MAIN CHAT AREA -->
<div class="main-area">
    <div class="chat-header">
        <div style="display:flex;align-items:center;gap:10px;">
            <button class="burger-menu header-actions" onclick="toggleSidebar()" style="margin:0;padding:4px 8px;font-size:1.4rem;">☰</button>
            <div class="chat-title" id="chatTitle">Global Chat</div>
        </div>
        <div class="header-actions">
            <button onclick="openNotifications()" title="Notifications">
                🔔 <span class="notif-badge" id="notifBadge">0</span>
            </button>
            <button onclick="openProfile(currentChatId)" id="btnViewProfile" style="display:none;" title="View Profile">👤</button>
            <!-- NEW: Group Settings Button (3 lines) -->
            <button onclick="openGroupSettings()" id="btnGroupSettings" style="display:none;" title="Group Settings" class="group-menu-btn">⋮</button>
            <!-- NEW: Add DM Button -->
            <button onclick="openAddDmModal()" id="btnAddDm" style="display:none;" title="Start New Chat" class="add-dm-btn">+</button>
        </div>
    </div>
    <div class="messages" id="messagesArea"></div>
    <div class="input-bar" id="inputBar">
        <label class="btn-file"><input type="file" id="fileInput" style="display:none" onchange="uploadFile(this)">📎</label>
        <input type="text" id="msgInput" placeholder="Type a message..." onkeypress="if(event.key==='Enter')sendMsg()">
        <button class="btn-send" onclick="sendMsg()">➤</button>
    </div>
</div>

<!-- MODALS -->
<div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
    <div class="modal" id="modalContent"></div>
</div>

<script>
    const ME = {{ user.id }};
    let currentChat = { type: 'global', id: null };
    let currentChatId = null;
    let pollInterval;
    let lastMsgId = 0;
    
    // --- NAVIGATION ---
    function switchTab(tab, el) {
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        if(el) el.classList.add('active');
        else document.querySelector(`.nav-tab[onclick*="${tab}"]`).classList.add('active');
        
        loadChatList(tab);
    }

    async function loadChatList(type) {
        const list = document.getElementById('chatList');
        const inputBar = document.getElementById('inputBar');
        const btnViewProfile = document.getElementById('btnViewProfile');
        const btnGroupSettings = document.getElementById('btnGroupSettings');
        const btnAddDm = document.getElementById('btnAddDm');
        const messagesArea = document.getElementById('messagesArea');
        
        list.innerHTML = '';
        btnViewProfile.style.display = 'none';
        btnGroupSettings.style.display = 'none';
        btnAddDm.style.display = 'none';
        
        // Reset Chat State
        clearInterval(pollInterval);
        currentChat = { type: type, id: null };
        currentChatId = null;
        lastMsgId = 0;
        messagesArea.innerHTML = '';

        if (type === 'global') {
            inputBar.style.display = 'flex';
            document.getElementById('chatTitle').innerText = 'Global Chat';
            
            // Load Global + Admin Channels into Sidebar List
            const res = await fetch('/api/chats');
            const data = await res.json();
            
            list.innerHTML = `<div class="list-item active" onclick="selectChat('global', 0, this)">
                <div style="width:40px;height:40px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-size:1.2rem;">🌍</div>
                <div class="list-info"><div class="list-name">Global Chat</div><div class="list-preview">Public channel</div></div>
            </div>`;
            
            data.channels.forEach(c => {
                list.innerHTML += `<div class="list-item" onclick="selectChat('channel', ${c.id}, this)">
                    <div style="width:40px;height:40px;border-radius:50%;background:#2d2452;display:flex;align-items:center;justify-content:center;">#</div>
                    <div class="list-info"><div class="list-name">${esc(c.name)}</div><div class="list-preview">Admin Channel</div></div>
                </div>`;
            });
            
            // Auto-select Global
            selectChat('global', 0, list.firstChild);
            
        } else if (type === 'private') {
            inputBar.style.display = 'none'; // Hide input until a specific DM is selected
            document.getElementById('chatTitle').innerText = 'Direct Messages';
            btnAddDm.style.display = 'flex'; // Show + button
            
            const res = await fetch('/api/chats');
            const data = await res.json();
            
            // Render Grid of Friends/DMs in Main Area instead of Sidebar
            if(data.privates.length === 0) {
                messagesArea.innerHTML = `<div style="text-align:center;color:var(--sub);padding:40px;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                    <div style="font-size:3rem;margin-bottom:16px;">💬</div>
                    <div>No conversations yet.</div>
                    <div>Click the <b>+</b> button above to start chatting!</div>
                </div>`;
            } else {
                messagesArea.innerHTML = `<div class="dm-grid">
                    ${data.privates.map(p => `
                        <div class="dm-card" onclick="startPrivateChat(${p.other_id}, '${esc(p.display_name||p.username)}', '${p.avatar_url}')">
                            ${p.is_online ? '<div class="dm-online"></div>' : ''}
                            <img src="${p.avatar_url}">
                            <div class="dm-name">${esc(p.display_name||p.username)}</div>
                            <div class="dm-last-msg">${esc(p.last_msg || 'Say hello!')}</div>
                        </div>
                    `).join('')}
                </div>`;
            }
            
        } else if (type === 'groups') {
            inputBar.style.display = 'none';
            document.getElementById('chatTitle').innerText = 'My Groups';
            
            const res = await fetch('/api/chats');
            const data = await res.json();
            
            if(data.groups.length === 0) {
                 messagesArea.innerHTML = `<div style="text-align:center;color:var(--sub);padding:40px;">No groups yet.<br>Create one from the sidebar!</div>`;
            } else {
                messagesArea.innerHTML = `<div class="dm-grid">
                    ${data.groups.map(g => `
                        <div class="dm-card" onclick="selectChat('group', ${g.id}, null)">
                            <div style="width:64px;height:64px;border-radius:50%;background:#2d2452;display:flex;align-items:center;justify-content:center;font-size:1.5rem;margin-bottom:12px;">#</div>
                            <div class="dm-name">${esc(g.name)}</div>
                            <div class="dm-last-msg">Group Chat</div>
                        </div>
                    `).join('')}
                </div>`;
            }
            
        } else if (type === 'feed') {
            inputBar.style.display = 'none';
            document.getElementById('chatTitle').innerText = 'Subscriptions Feed';
            loadFeed();
            
        } else if (type === 'pages') {
            inputBar.style.display = 'none';
            document.getElementById('chatTitle').innerText = 'My Pages';
            
            const res = await fetch('/api/my_pages');
            const pages = await res.json();
            messagesArea.innerHTML = `
                <div class="pages-list">
                    ${pages.map(p => `<a href="/page/${p.slug}" target="_blank" class="page-card">
                        <span class="page-badge ${p.is_public?'public':'private'}">${p.is_public?'PUBLIC':'PRIVATE'}</span>
                        <h4>${esc(p.title)}</h4>
                        <span>/page/${p.slug}</span>
                    </a>`).join('')}
                    <div class="page-card" onclick="openModal('editPage')" style="border-style:dashed; display:flex; align-items:center; justify-content:center; flex-direction:column; color:var(--sub);">
                        <div style="font-size:2rem; margin-bottom:8px;">+</div>
                        <div>Create New Page</div>
                    </div>
                </div>`;
        }
    }
    
    // NEW: Start Private Chat Function
    function startPrivateChat(uid, name, avatar) {
        // Manually construct a "list item" element to pass to selectChat for visual consistency if needed, 
        // but here we just trigger the logic directly.
        
        // Update UI to look like a chat is selected
        document.getElementById('chatTitle').innerText = name;
        document.getElementById('btnViewProfile').style.display = 'block';
        document.getElementById('inputBar').style.display = 'flex';
        
        // Clear the grid view and prepare message area
        document.getElementById('messagesArea').innerHTML = '';
        
        selectChat('private', uid, null);
    }

    // NEW: Open Add DM Modal
    async function openAddDmModal() {
        const res = await fetch('/api/all_users');
        const users = await res.json();
        
        // Filter out people who are already friends/have chats? 
        // For simplicity, show all non-friends or just all users. Let's show all for now.
        
        const m = document.getElementById('modalContent');
        m.innerHTML = `
            <h3>Start New Chat</h3>
            <div style="max-height:300px;overflow-y:auto;">
                ${users.map(u => `
                    <div class="user-search-item" style="cursor:pointer;" onclick="startPrivateChat(${u.id}, '${esc(u.display_name||u.username)}', '${u.avatar_url}'); closeModal();">
                        <img src="${u.avatar_url}">
                        <div class="user-search-info">
                            <div class="user-search-name">${esc(u.display_name||u.username)}</div>
                            <div class="user-search-status">@${esc(u.username)}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
            <div class="modal-btns"><button class="btn-secondary" onclick="closeModal()">Close</button></div>
        `;
        document.getElementById('modalOverlay').style.display = 'flex';
    }

    async function loadFeed() {
        const res = await fetch('/api/feed');
        const posts = await res.json();
        const area = document.getElementById('messagesArea');
        if(posts.length === 0) {
            area.innerHTML = `<div style="text-align:center;color:var(--sub);padding:40px;">No posts from subscriptions yet.<br>Subscribe to users to see their wall posts here!</div>`;
            return;
        }
        area.innerHTML = posts.map(p => `
            <div class="feed-post">
                <div class="feed-header">
                    <img src="${p.avatar_url}" class="feed-avatar" onclick="openProfile(${p.author_id})">
                    <div>
                        <div class="feed-author" style="cursor:pointer;color:${p.theme_color}" onclick="openProfile(${p.author_id})">${esc(p.display_name||p.username)}</div>
                        <div class="feed-target">on ${esc(p.target_username || 'a user\'s')} wall</div>
                    </div>
                </div>
                <div class="feed-content">${linkify(esc(p.content||''))}</div>
                ${p.post_type==='image' && p.url ? `<img src="${p.url}" class="feed-img" onclick="window.open(this.src)">` : ''}
                ${p.post_type==='file' && p.url ? `<a href="${p.url}" download style="color:var(--accent);font-size:0.8rem;">📦 ${esc(p.filename)}</a>` : ''}
                <div class="feed-time">${new Date(p.timestamp).toLocaleString()}</div>
            </div>
        `).join('');
    }

    function selectChat(type, id, el) {
        currentChat = { type, id };
        currentChatId = id;
        lastMsgId = 0;
        
        // Visual selection in sidebar if it's a list item click
        if(el) {
            document.querySelectorAll('.list-item').forEach(i => i.classList.remove('active'));
            el.classList.add('active');
        }
        
        const title = document.getElementById('chatTitle');
        const btnProf = document.getElementById('btnViewProfile');
        const btnGrp = document.getElementById('btnGroupSettings');
        const inputBar = document.getElementById('inputBar');
        
        inputBar.style.display = 'flex'; // Show input for all chat types
        
        if (type === 'global' || type === 'channel') {
            title.innerText = type === 'channel' ? 'Channel' : 'Global Chat';
            btnProf.style.display = 'none';
            btnGrp.style.display = 'none';
        } else if (type === 'private') {
            btnProf.style.display = 'block';
            btnGrp.style.display = 'none';
            // Title is set by startPrivateChat usually, but if clicked from sidebar (legacy):
            if(!title.innerText.includes('@') && type === 'private') title.innerText = 'Private Message'; 
        } else if (type === 'group') {
            title.innerText = 'Group Chat';
            btnProf.style.display = 'none';
            btnGrp.style.display = 'block';
        }
        
        loadMessages(true);
        clearInterval(pollInterval);
        pollInterval = setInterval(() => loadMessages(false), 2000);
    }

    async function loadMessages(fullReload = false) {
        if(currentChat.type === 'pages' || currentChat.type === 'feed') return;
        if(!currentChat.id && currentChat.type !== 'global') return;
        
        const res = await fetch(`/api/messages/${currentChat.type}/${currentChat.id || 0}`);
        if (!res.ok) return;
        const msgs = await res.json();
        
        const area = document.getElementById('messagesArea');
        
        if (fullReload || area.children.length === 0) {
            area.innerHTML = msgs.map(m => createMsgHTML(m)).join('');
            lastMsgId = msgs.length > 0 ? msgs[msgs.length-1].id : 0;
            area.scrollTop = area.scrollHeight;
            return;
        }
        
        const newMsgs = msgs.filter(m => m.id > lastMsgId);
        if (newMsgs.length > 0) {
            const wasBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 100;
            newMsgs.forEach(m => area.insertAdjacentHTML('beforeend', createMsgHTML(m)));
            lastMsgId = msgs[msgs.length-1].id;
            if (wasBottom) area.scrollTop = area.scrollHeight;
        }
    }

    function createMsgHTML(m) {
        const isMine = m.sender_id === ME;
        const time = new Date(m.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        let content = '';
        
        if (m.type === 'text') content = linkify(esc(m.content));
        else if (m.type === 'image') content = `<img src="${m.url}" loading="lazy" onclick="window.open(this.src)">`;
        else if (m.type === 'text_file') content = `<div style="background:rgba(0,0,0,0.2);padding:8px;border-radius:6px;font-family:monospace;font-size:0.8rem;max-height:100px;overflow:auto;white-space:pre-wrap;">${esc(m.content)}</div><a href="${m.url}" download style="color:inherit;display:inline-block;margin-top:4px;font-size:0.8rem;text-decoration:none;background:rgba(255,255,255,0.1);padding:4px 8px;border-radius:4px;">📄 ${esc(m.filename)}</a>`;
        else content = `<a href="${m.url}" download style="color:inherit;font-weight:bold;text-decoration:none;background:rgba(255,255,255,0.1);padding:6px 12px;border-radius:6px;display:inline-flex;align-items:center;gap:6px;">📦 ${esc(m.filename)}</a>`;
        
        return `<div class="msg-row ${isMine?'mine':'theirs'}">
            <img src="${m.avatar_url}" class="msg-avatar" onclick="openProfile(${m.sender_id})">
            <div class="msg-bubble">
                ${(currentChat.type !== 'private') ? `<div class="msg-sender" style="color:${m.theme_color}">${esc(m.display_name||m.username)}</div>` : ''}
                ${content}
                <div class="msg-time">${time}</div>
            </div>
        </div>`;
    }

    async function sendMsg() {
        const inp = document.getElementById('msgInput');
        const txt = inp.value.trim();
        if (!txt) return;
        
        const res = await fetch('/api/send_message', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({type:currentChat.type, target_id:currentChat.id, text:txt})
        });
        const d = await res.json();
        if(d.error) {
            alert(d.error);
            if(d.error === 'Banned') window.location.reload();
        } else {
            inp.value = '';
            loadMessages(false);
        }
    }

    async function uploadFile(input) {
        if (!input.files.length) return;
        const fd = new FormData();
        fd.append('file', input.files[0]);
        await fetch('/api/upload', {method:'POST', body:fd});
        input.value = '';
        loadMessages(false);
    }

    // --- PROFILE & WALL ---
    async function openProfile(uid) {
        const res = await fetch(`/api/user/${uid}`);
        if(!res.ok) return;
        const user = await res.json();
        
        const wRes = await fetch(`/api/wall/${uid}`);
        const wallData = await wRes.json();
        const posts = wallData.posts;
        
        const modal = document.getElementById('modalContent');
        let friendBtn = '';
        
        if (uid !== ME) {
            if (user.friend_status === 'friends') {
                friendBtn = `<button onclick="friendAction('unfriend', ${uid})" style="background:transparent;border:1px solid #ef4444;color:#ef4444;padding:4px 12px;border-radius:12px;cursor:pointer;font-size:0.75rem;">Unfriend</button>`;
            } else if (user.friend_status === 'sent_request') {
                friendBtn = `<button disabled style="background:transparent;border:1px solid var(--sub);color:var(--sub);padding:4px 12px;border-radius:12px;font-size:0.75rem;">Request Sent</button>`;
            } else if (user.friend_status === 'received_request') {
                friendBtn = `
                    <button onclick="friendAction('accept', ${uid})" class="btn-success" style="padding:4px 12px;border-radius:12px;cursor:pointer;font-size:0.75rem;">Accept</button>
                    <button onclick="friendAction('decline', ${uid})" class="btn-danger" style="padding:4px 12px;border-radius:12px;cursor:pointer;font-size:0.75rem;">Decline</button>
                `;
            } else {
                friendBtn = `<button onclick="friendAction('send_request', ${uid})" style="background:transparent;border:1px solid var(--accent);color:var(--accent);padding:4px 12px;border-radius:12px;cursor:pointer;font-size:0.75rem;">+ Add Friend</button>`;
            }
        }
        
        const isOwnProfile = (uid === ME);
        
        modal.innerHTML = `
            <div class="pv-header">
                <img src="${user.avatar_url}" class="pv-avatar">
                <div class="pv-info">
                    <h2>${esc(user.display_name||user.username)}</h2>
                    <div class="pv-bio">${esc(user.bio)||'No bio yet.'}</div>
                    <div class="pv-stats">
                        <span>@${esc(user.username)}</span>
                        <span>${user.role.toUpperCase()}</span>
                        ${friendBtn}
                        <button onclick="toggleSub(${uid}, this)" style="background:transparent;border:1px solid var(--border);color:var(--sub);padding:4px 12px;border-radius:12px;cursor:pointer;font-size:0.75rem;">
                            ${user.is_subscribed ? '✓ Subscribed' : '+ Subscribe'} (${user.subs_count})
                        </button>
                    </div>
                </div>
            </div>
            ${isOwnProfile ? `
            <div class="wall-input">
                <textarea id="wallInput" placeholder="Write something on the wall..."></textarea>
                <div style="display:flex;gap:8px;align-items:center;">
                    <label class="btn-file" style="width:40px;height:40px;border-radius:8px;flex-shrink:0;"><input type="file" id="wallFile" style="display:none"></label>
                    <button class="btn-primary" onclick="postToWall(${uid})" style="flex:1;">Publish Post</button>
                </div>
            </div>
            ` : ''}
            <div style="max-height:300px;overflow-y:auto;">
                ${posts.length ? posts.map(p => `
                    <div class="wall-post">
                        <div class="wp-author"><img src="${p.avatar_url}"> ${esc(p.display_name||p.username)}</div>
                        <div class="wp-content">${linkify(esc(p.content||''))}</div>
                        ${p.post_type==='image' && p.url ? `<img src="${p.url}" class="wp-img" onclick="window.open(this.src)">` : ''}
                        ${p.post_type==='file' && p.url ? `<a href="${p.url}" download style="color:var(--accent);font-size:0.8rem;">📦 ${esc(p.filename)}</a>` : ''}
                        <div class="wp-time">${new Date(p.timestamp).toLocaleString()}</div>
                    </div>
                `).join('') : '<div style="text-align:center;color:var(--sub);padding:20px;">Wall is empty</div>'}
            </div>
            <div class="modal-btns">
                {% if user.role == 'admin' %}
                <button class="btn-danger" onclick="adminBan(${uid})">${user.is_banned ? 'Unban' : 'Ban User'}</button>
                <button class="btn-secondary" onclick="adminMute(${uid})">Mute (1h)</button>
                {% endif %}
                <button class="btn-secondary" onclick="closeModal()">Close</button>
            </div>
        `;
        document.getElementById('modalOverlay').style.display = 'flex';
    }

    async function friendAction(action, uid) {
        await fetch('/api/friend_action', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({action, target_id: uid})
        });
        openProfile(uid);
        if(action === 'accept' || action === 'unfriend') {
             // Refresh DMs if needed
             if(currentChat.type === 'private') loadChatList('private');
        }
        loadNotifications();
    }

    async function toggleSub(uid, el) {
        await fetch(`/api/subscribe/${uid}`, {method:'POST'});
        openProfile(uid);
        if(currentChat.type === 'feed') loadFeed();
    }

    async function postToWall(uid) {
        const txt = document.getElementById('wallInput').value;
        const fileInput = document.getElementById('wallFile');
        if(!txt && !fileInput.files.length) return;
        
        const fd = new FormData();
        fd.append('content', txt);
        if(fileInput.files.length) fd.append('file', fileInput.files[0]);
        
        await fetch(`/api/wall/${uid}`, {method:'POST', body:fd});
        openProfile(uid);
    }

    async function adminBan(uid) {
        await fetch('/admin/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'ban_user', id:uid})});
        openProfile(uid);
    }

    async function adminMute(uid) {
        await fetch('/admin/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'mute_user', id:uid, minutes:60})});
        alert('User muted for 1 hour');
        closeModal();
    }

    // --- NOTIFICATIONS ---
    async function openNotifications() {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        const m = document.getElementById('modalContent');
        m.innerHTML = `
            <h3>Notifications</h3>
            ${data.requests.length ? data.requests.map(r => `
                <div class="notif-item">
                    <img src="${r.avatar_url}" class="notif-avatar">
                    <div class="notif-text">
                        <strong>${esc(r.display_name||r.username)}</strong> wants to be your friend.
                    </div>
                    <div class="notif-actions">
                        <button class="btn-success" onclick="friendAction('accept', ${r.requester_id}); openNotifications();">Accept</button>
                        <button class="btn-danger" onclick="friendAction('decline', ${r.requester_id}); openNotifications();">Decline</button>
                    </div>
                </div>
            `).join('') : '<div style="text-align:center;color:var(--sub);padding:20px;">No new notifications</div>'}
            <div class="modal-btns"><button class="btn-secondary" onclick="closeModal()">Close</button></div>
        `;
        document.getElementById('modalOverlay').style.display = 'flex';
        document.getElementById('notifBadge').style.display = 'none';
    }

    async function loadNotifications() {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        const badge = document.getElementById('notifBadge');
        if(data.count > 0) {
            badge.textContent = data.count;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }
    }

    // --- GROUP SETTINGS (FIXED WITH 3 LINES BUTTON) ---
    async function openGroupSettings() {
        if(currentChat.type !== 'group') return;
        
        const res = await fetch(`/api/group/${currentChat.id}/info`);
        const data = await res.json();
        
        if(!data.is_owner) {
            alert("Only owner can edit group");
            return;
        }
        
        const m = document.getElementById('modalContent');
        m.innerHTML = `
            <h3>Edit Group: ${esc(data.group.name)}</h3>
            <label>Name</label><input id="g_name" value="${esc(data.group.name)}">
            <label>Description</label><textarea id="g_desc" rows="2">${esc(data.group.description||'')}</textarea>
            
            <label style="margin-top:16px;">Members</label>
            <div style="max-height:150px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:8px;margin-bottom:12px;">
                ${data.members.map(mem => `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;font-size:0.85rem;">
                        <span>${esc(mem.display_name||mem.username)}</span>
                        ${mem.id !== ME ? `<button onclick="removeMember(${mem.id})" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:0.7rem;">✕ Remove</button>` : ''}
                    </div>
                `).join('')}
            </div>
            
            <label>Add Member</label>
            <div style="display:flex;gap:8px;">
                <select id="g_add_member" style="flex:1;">
                    <option value="">Select User...</option>
                    ${data.all_users.filter(u => !data.members.find(m => m.id === u.id)).map(u => 
                        `<option value="${u.id}">${esc(u.display_name||u.username)}</option>`
                    ).join('')}
                </select>
                <button class="btn-primary" onclick="addGroupMember()" style="width:auto;padding:10px;">Add</button>
            </div>
            
            <div class="modal-btns">
                <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn-primary" onclick="saveGroupInfo()">Save Info</button>
            </div>
        `;
        document.getElementById('modalOverlay').style.display = 'flex';
    }
    
    async function addGroupMember() {
        const uid = document.getElementById('g_add_member').value;
        if(!uid) return;
        await fetch(`/api/group/${currentChat.id}/members`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({user_id: parseInt(uid)})
        });
        openGroupSettings(); // Refresh list
    }

    async function removeMember(uid) {
        if(!confirm('Remove this user?')) return;
        await fetch(`/api/group/${currentChat.id}/members`, {
            method:'DELETE', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({user_id: uid})
        });
        openGroupSettings();
    }

    async function saveGroupInfo() {
        const name = document.getElementById('g_name').value;
        const desc = document.getElementById('g_desc').value;
        await fetch(`/api/group/${currentChat.id}/info`, {
            method:'PUT', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({name, description: desc})
        });
        closeModal();
        // Refresh group list if needed
        if(currentChat.type === 'groups') loadChatList('groups');
        else document.getElementById('chatTitle').innerText = name;
    }

    // --- MODALS ---
    function openModal(type) {
        const m = document.getElementById('modalContent');
        if (type === 'editProfile') {
            m.innerHTML = `
                <h3>Edit Profile</h3>
                <label>Display Name</label><input id="p_name" value="{{ user.display_name }}">
                <label>Bio</label><textarea id="p_bio" rows="2">{{ user.bio }}</textarea>
                <label>Accent Color</label><input type="color" id="p_color" value="{{ user.theme_color }}" style="height:40px;padding:2px;">
                <label>Background Color</label><input type="color" id="p_bg" value="{{ user.bg_color }}" style="height:40px;padding:2px;">
                <label>Avatar</label><input type="file" id="p_avatar" accept="image/*">
                <div class="modal-btns">
                    <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                    <button class="btn-primary" onclick="saveProfile()">Save Changes</button>
                </div>`;
        } else if (type === 'createGroup') {
            m.innerHTML = `
                <h3>Create Group</h3>
                <label>Group Name</label><input id="g_name" placeholder="My Awesome Group">
                <label>Add Members (Optional)</label>
                <select id="g_members" multiple style="height:100px;"></select>
                <div class="modal-btns">
                    <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                    <button class="btn-primary" onclick="createGroup()">Create</button>
                </div>`;
            // Load users for selection
            fetch('/api/all_users').then(r=>r.json()).then(users => {
                 const sel = document.getElementById('g_members');
                 users.forEach(u => {
                     sel.innerHTML += `<option value="${u.id}">${esc(u.display_name||u.username)}</option>`;
                 });
            });
        } else if (type === 'editPage') {
            m.innerHTML = `
                <h3>Create/Edit Page</h3>
                <label>Title</label><input id="pg_title" placeholder="My Page Title">
                <label>Visibility</label>
                <select id="pg_vis">
                    <option value="1">Public (Everyone)</option>
                    <option value="0">Private (Friends Only)</option>
                </select>
                <label>OR Upload HTML File</label>
                <input type="file" id="pg_html_file" accept=".html">
                <label>HTML Content</label><textarea id="pg_html" rows="8" placeholder="<h1>Hello World</h1>"></textarea>
                <div class="modal-btns">
                    <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                    <button class="btn-primary" onclick="savePage()">Publish</button>
                </div>`;
        }
        document.getElementById('modalOverlay').style.display = 'flex';
    }

    function closeModal() { document.getElementById('modalOverlay').style.display = 'none'; }

    async function saveProfile() {
        const fd = new FormData();
        fd.append('display_name', document.getElementById('p_name').value);
        fd.append('bio', document.getElementById('p_bio').value);
        const color = document.getElementById('p_color').value;
        const bg = document.getElementById('p_bg').value;
        fd.append('theme_color', color);
        fd.append('bg_color', bg);
        
        // Apply immediately for preview
        document.documentElement.style.setProperty('--accent', color);
        document.documentElement.style.setProperty('--bg', bg);
        
        const av = document.getElementById('p_avatar').files[0];
        if(av) fd.append('avatar', av);
        
        await fetch('/api/update_profile', {method:'POST', body:fd});
        closeModal();
        // Reload page to update sidebar name/avatar properly or use JS to update DOM
        location.reload(); 
    }

    async function createGroup() {
        const name = document.getElementById('g_name').value;
        const sel = document.getElementById('g_members');
        const members = Array.from(sel.selectedOptions).map(o => o.value);
        
        const res = await fetch('/api/groups', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({name, members})
        });
        const d = await res.json();
        if(d.success) { 
            closeModal(); 
            switchTab('groups'); 
        } else {
            alert(d.error);
        }
    }

    async function savePage() {
        const title = document.getElementById('pg_title').value;
        const html = document.getElementById('pg_html').value;
        const vis = document.getElementById('pg_vis').value;
        const fileInput = document.getElementById('pg_html_file');
        
        if (fileInput.files.length > 0) {
            const fd = new FormData();
            fd.append('html_file', fileInput.files[0]);
            fd.append('title', title || fileInput.files[0].name.replace('.html',''));
            fd.append('is_public', vis);
            const res = await fetch('/api/my_pages', {method:'POST', body:fd});
            const d = await res.json();
            if(d.success) { closeModal(); switchTab('pages'); }
            else alert(d.error);
        } else {
            const res = await fetch('/api/my_pages', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({title, html, is_public: parseInt(vis)})
            });
            const d = await res.json();
            if(d.success) { closeModal(); switchTab('pages'); }
            else alert(d.error);
        }
    }

    // --- UTILS ---
    function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
    function linkify(t) { return t.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" style="color:inherit;text-decoration:underline">$1</a>'); }
    function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }

    // Init
    loadChatList('global');
    loadNotifications();
    setInterval(loadNotifications, 30000);
</script>
</body>
</html>
"""

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Panel</title>
<link rel="icon" href="/static/favicon.ico">
<style>
body { background:#0d0a1a; color:#f5f3ff; font-family:sans-serif; padding:20px; }
h1 { color:#a78bfa; margin-bottom:20px; }
table { width:100%; border-collapse:collapse; margin-bottom:30px; background:#1a1333; border-radius:8px; overflow:hidden; }
th, td { padding:12px; text-align:left; border-bottom:1px solid #2d2452; }
th { background:#231b42; color:#a78bfa; font-size:0.8rem; text-transform:uppercase; }
button { padding:6px 12px; border-radius:6px; border:none; cursor:pointer; font-size:0.8rem; margin-right:4px; transition:0.2s; } 
button:hover { opacity:0.8; transform:translateY(-1px); }
.btn-del { background:#fca5a5; color:#000; }
.btn-role { background:#6ee7b7; color:#000; }
.btn-ban { background:#ef4444; color:white; }
nav { margin-bottom:20px; display:flex; gap:15px; }
nav a { color:#a78bfa; text-decoration:none; font-weight:bold; padding:8px 16px; border-radius:8px; transition:0.2s; }
nav a:hover { background:rgba(167,139,250,0.1); }
.admin-section { margin-bottom:40px; background:#1a1333; padding:20px; border-radius:12px; border:1px solid #2d2452; }
.admin-section h2 { color:#a78bfa; margin-bottom:16px; font-size:1.2rem; }
input, textarea { padding:8px; border-radius:4px; border:1px solid #2d2452; background:#0d0a1a; color:white; margin-right:8px; }
</style>
</head>
<body>
<nav>
<a href="/">← Back to Chat</a>
</nav>
<div class="admin-section">
    <h2>Global Channels</h2>
    <div style="margin-bottom:16px;">
        <input id="ch_name" placeholder="Channel Name">
        <input id="ch_desc" placeholder="Description">
        <button onclick="createChannel()" style="background:#a78bfa; color:white; padding:8px 16px; border-radius:4px; border:none; cursor:pointer;">Create Channel</button>
    </div>
    <table>
        <thead><tr><th>ID</th><th>Name</th><th>Description</th><th>Actions</th></tr></thead>
        <tbody id="channelsList"></tbody>
    </table>
</div>
<div class="admin-section">
    <h2>User Management</h2>
    <table>
        <thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
            {% for u in users %}
            <tr>
                <td>{{ u.id }}</td>
                <td>{{ u.username }}</td>
                <td>{{ u.role }}</td>
                <td>{% if u.is_banned %}<span style="color:#ef4444">BANNED</span>{% else %}Active{% endif %}</td>
                <td>
                    <button class="btn-role" onclick="adminAction('toggle_admin', {{ u.id }})">Toggle Admin</button>
                    <button class="btn-ban" onclick="adminAction('ban_user', {{ u.id }})">{% if u.is_banned %}Unban{% else %}Ban{% endif %}</button>
                    <button class="btn-del" onclick="adminAction('delete_user', {{ u.id }})">Delete</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
<script>
    async function adminAction(action, id) {
        if(!confirm('Are you sure?')) return;
        await fetch('/admin/action', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({action, id})
        });
        location.reload();
    }
    async function loadChannels() {
        const res = await fetch('/api/admin/channels');
        const channels = await res.json();
        document.getElementById('channelsList').innerHTML = channels.map(c => `
            <tr>
                <td>${c.id}</td>
                <td>${c.name}</td>
                <td>${c.description||''}</td>
                <td><button class="btn-del" onclick="deleteChannel(${c.id})">Delete</button></td>
            </tr>
        `).join('');
    }
    async function createChannel() {
        const name = document.getElementById('ch_name').value;
        const desc = document.getElementById('ch_desc').value;
        await fetch('/api/admin/channels', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({name, description: desc})
        });
        loadChannels();
        document.getElementById('ch_name').value = '';
        document.getElementById('ch_desc').value = '';
    }
    async function deleteChannel(id) {
        if(!confirm('Delete this channel?')) return;
        await fetch('/api/admin/channels', {
            method:'DELETE', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({id})
        });
        loadChannels();
    }
    loadChannels();
</script>
</body>
</html>
"""

CUSTOM_PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ page.title }} - YuuY</title>
<link rel="icon" href="/static/favicon.ico">
<style>
body { background:#0d0a1a; color:#f5f3ff; font-family:sans-serif; max-width:800px; margin:0 auto; padding:40px 20px; line-height:1.6; }
h1 { color:#a78bfa; border-bottom:1px solid #2d2452; padding-bottom:10px; margin-bottom:20px; }
a { color:#a78bfa; text-decoration:none; }
a:hover { text-decoration:underline; }
.content { background:#1a1333; padding:30px; border-radius:12px; border:1px solid #2d2452; min-height:200px; }
.content img { max-width:100%; height:auto; }
</style>
</head>
<body>
<a href="/" style="font-size:0.9rem; opacity:0.7;">← Back to Chat</a>
<h1>{{ page.title }}</h1>
<div class="content">{{ page.html_content | safe }}</div>
<footer style="margin-top:40px; font-size:0.8rem; opacity:0.5; border-top:1px solid #2d2452; padding-top:10px;">
Personal Page
</footer>
</body>
</html>
"""

PAGE_403_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access Denied - YuuY</title>
<link rel="icon" href="/static/favicon.ico">
<style>
body { background:#0d0a1a; color:#f5f3ff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; flex-direction:column; }
h1 { color:#ef4444; margin-bottom:10px; }
p { color:#a5a0c0; }
a { color:#a78bfa; text-decoration:none; margin-top:20px; }
</style>
</head>
<body>
<h1>Private Page</h1>
<p>You are not friends with the owner of this page.</p>
<a href="/">← Back to Chat</a>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)