import flask
from flask_socketio import SocketIO, join_room, leave_room, emit
import os

app = flask.Flask(__name__, static_folder='public')
app.config['SECRET_KEY'] = 'chat-secret-key'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# {room: [{sid, username}, ...]}
rooms = {}


@app.route('/')
def index():
    return flask.send_from_directory('public', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return flask.send_from_directory('public', filename)


@socketio.on('join')
def on_join(data):
    from flask import request
    room = data.get('room', '').strip()
    username = data.get('username', '').strip()
    if not room or not username:
        emit('error', {'message': 'Room and username are required'})
        return

    # Check if room is full BEFORE adding
    members = rooms.get(room, [])
    if len(members) >= 2:
        emit('room-full')
        return

    # Add user to room
    join_room(room)
    rooms.setdefault(room, []).append({'sid': request.sid, 'username': username})
    members = rooms[room]

    # Verify we didn't exceed capacity (defense against race conditions)
    if len(members) > 2:
        rooms[room] = [m for m in members if m['sid'] != request.sid]
        leave_room(room)
        emit('room-full')
        return

    emit('join-success', {'room': room, 'username': username})
    emit('user-joined', {
        'username': username,
        'count': len(members),
        'users': [m['username'] for m in members]
    }, to=room)


@socketio.on('message')
def on_message(data):
    from flask import request
    from datetime import datetime
    room = data.get('room')
    text = data.get('text', '').strip()
    if not room or not text:
        return

    members = rooms.get(room, [])
    if not members:
        emit('error', {'message': 'Room not found'})
        return

    # Find sender by sid
    sender = next((m['username'] for m in members if m['sid'] == request.sid), None)
    if not sender:
        emit('error', {'message': 'You are not in this room'})
        return

    timestamp = datetime.now().strftime('%I:%M %p')
    emit('message', {'from': sender, 'text': text, 'timestamp': timestamp}, to=room)


@socketio.on('typing')
def on_typing(data):
    room = data.get('room')
    username = data.get('username')
    if room and username:
        emit('typing', {'username': username}, to=room, include_self=False)


@socketio.on('stop-typing')
def on_stop_typing(data):
    from flask import request
    room = data.get('room')
    if room:
        # Verify user is in this room
        members = rooms.get(room, [])
        if any(m['sid'] == request.sid for m in members):
            emit('stop-typing', to=room, include_self=False)


@socketio.on('disconnect')
def on_disconnect():
    from flask import request
    for room, members in list(rooms.items()):
        for member in members:
            if member['sid'] == request.sid:
                username = member['username']
                rooms[room] = [m for m in members if m['sid'] != request.sid]
                if not rooms[room]:
                    del rooms[room]
                else:
                    emit('user-left', {'username': username, 'count': len(rooms[room])}, to=room)
                return


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'Chat server running at http://localhost:{port}')
    print('Share this address with your friend on the same network.')
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

import os
from flask import Flask, send_from_directory, send_file
from flask_socketio import SocketIO, join_room, leave_room, emit
from datetime import datetime

# Get the absolute path to the public folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'public')

# Create Flask app with proper static folder configuration
app = flask.Flask(__name__,
            static_folder=STATIC_DIR,
            static_url_path='/static')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chat-secret-key-prod')
app.config['JSON_SORT_KEYS'] = False

# Initialize Socket.io with production-safe settings
socketio = SocketIO(
    app,
    async_mode='threading',
    cors_allowed_origins='*',
    ping_timeout=60,
    ping_interval=25
)

# Store active rooms: {room: [{sid, username}, ...]}
rooms = {}


# ==================== ROUTES ====================

@app.route('/')
def serve_index():
    """Serve index.html at root"""
    try:
        return send_file(os.path.join(STATIC_DIR, 'index.html'))
    except Exception as e:
        return f"Error loading index.html: {str(e)}", 500


@app.route('/index.html')
def serve_index_explicit():
    """Serve index.html explicitly"""
    try:
        return send_file(os.path.join(STATIC_DIR, 'index.html'))
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS, etc.)"""
    try:
        return flask.send_from_directory(STATIC_DIR, filename)
    except Exception as e:
        return f"File not found: {filename}", 404


@app.route('/style.css')
def serve_css():
    """Direct CSS route for backwards compatibility"""
    try:
        return flask.send_from_directory(STATIC_DIR, 'style.css')
    except Exception as e:
        return f"CSS not found: {str(e)}", 404


@app.route('/chat.js')
def serve_js():
    """Direct JS route for backwards compatibility"""
    try:
        return flask.send_from_directory(STATIC_DIR, 'chat.js')
    except Exception as e:
        return f"JS not found: {str(e)}", 404


@app.errorhandler(404)
def not_found(error):
    """Fallback: serve index.html for SPA-style routing"""
    try:
        return send_file(os.path.join(STATIC_DIR, 'index.html'))
    except:
        return "Not Found", 404


@app.errorhandler(500)
def server_error(error):
    """Handle server errors gracefully"""
    return f"Server Error: {str(error)}", 500


# ==================== SOCKET.IO EVENTS ====================

@socketio.on('connect')
def on_connect():
    """Handle client connection"""
    pass


@socketio.on('join')
def on_join(data):
    """User joins a room"""
    from flask import request

    room = (data.get('room') or '').strip()
    username = (data.get('username') or '').strip()

    if not room or not username:
        emit('error', {'message': 'Room and username are required'})
        return

    # Check if room is full
    members = rooms.get(room, [])
    if len(members) >= 2:
        emit('room-full')
        return

    # Add user to room
    join_room(room)
    rooms.setdefault(room, []).append({'sid': request.sid, 'username': username})
    members = rooms[room]

    # Double-check capacity (race condition protection)
    if len(members) > 2:
        rooms[room] = [m for m in members if m['sid'] != request.sid]
        leave_room(room)
        emit('room-full')
        return

    # Notify user of successful join
    emit('join-success', {'room': room, 'username': username})

    # Notify all in room
    emit('user-joined', {
        'username': username,
        'count': len(members),
        'users': [m['username'] for m in members]
    }, to=room)


@socketio.on('message')
def on_message(data):
    """Handle incoming messages"""
    from flask import request

    room = data.get('room')
    text = (data.get('text') or '').strip()

    if not room or not text:
        return

    members = rooms.get(room, [])
    if not members:
        emit('error', {'message': 'Room not found'})
        return

    # Find sender by session ID
    sender = next((m['username'] for m in members if m['sid'] == request.sid), None)
    if not sender:
        emit('error', {'message': 'You are not in this room'})
        return

    timestamp = datetime.now().strftime('%I:%M %p')
    emit('message', {
        'from': sender,
        'text': text,
        'timestamp': timestamp
    }, to=room)


@socketio.on('typing')
def on_typing(data):
    """Broadcast typing indicator"""
    room = data.get('room')
    username = data.get('username')

    if room and username:
        emit('typing', {'username': username}, to=room, include_self=False)


@socketio.on('stop-typing')
def on_stop_typing(data):
    """Stop typing indicator"""
    from flask import request

    room = data.get('room')
    if room:
        members = rooms.get(room, [])
        if any(m['sid'] == request.sid for m in members):
            emit('stop-typing', to=room, include_self=False)


@socketio.on('disconnect')
def on_disconnect():
    """Handle client disconnection"""
    from flask import request

    for room, members in list(rooms.items()):
        for member in members:
            if member['sid'] == request.sid:
                username = member['username']
                rooms[room] = [m for m in members if m['sid'] != request.sid]

                if not rooms[room]:
                    del rooms[room]
                else:
                    emit('user-left', {
                        'username': username,
                        'count': len(rooms[room])
                    }, to=room)
                return


# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'

    print(f'✓ Chat server starting on port {port}')
    print(f'✓ Static folder: {STATIC_DIR}')
    print(f'✓ Static files: {os.listdir(STATIC_DIR) if os.path.exists(STATIC_DIR) else "NOT FOUND"}')

    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True
    )
