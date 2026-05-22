from flask import Flask, send_from_directory
from flask_socketio import SocketIO, join_room, leave_room, emit
import os

app = Flask(__name__, static_folder='public')
app.config['SECRET_KEY'] = 'chat-secret-key'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# {room: [{sid, username}, ...]}
rooms = {}


@app.route('/')
def index():
    return send_from_directory('public', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('public', filename)


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
