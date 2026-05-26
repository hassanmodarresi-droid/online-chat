import os
import uuid
import flask
from flask import send_file
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, join_room, leave_room, emit
from datetime import datetime

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'public')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# App
app = flask.Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chat-secret-key')
# Limit uploads to 5 MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Allowed image types
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MIMETYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}

# Socket.IO
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# Optional S3 configuration (for persistent uploads)
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_REGION = os.environ.get('AWS_REGION') or os.environ.get('S3_REGION')
if S3_BUCKET:
    try:
        import boto3
        s3_client = boto3.client('s3', region_name=S3_REGION)
    except Exception:
        s3_client = None
else:
    s3_client = None

# In-memory rooms: { room: [ {sid, username}, ... ] }
rooms = {}


### Routes ###

@app.route('/')
def index():
    return send_file(os.path.join(STATIC_DIR, 'index.html'))


@app.route('/<path:filename>')
def static_files(filename):
    return flask.send_from_directory(STATIC_DIR, filename, cache_timeout=0)


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    full = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(full):
        return "Not Found", 404
    return send_file(full)


@app.route('/upload', methods=['POST'])
def upload_file():
    from flask import request, jsonify
    from werkzeug.utils import secure_filename

    if 'file' not in request.files:
        return jsonify(error='No file part'), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify(error='No selected file'), 400

    # Basic validations
    filename = file.filename

    # Support encrypted uploads: client may send encrypted file named '<orig>.enc'
    # and include original filename and content type in form fields.
    orig_name = request.form.get('orig_name')
    orig_content_type = request.form.get('orig_content_type')

    # Determine validation name and mimetype
    validate_name = orig_name if orig_name else filename
    validate_mimetype = orig_content_type if orig_content_type else file.mimetype

    if '.' not in validate_name:
        return jsonify(error='Invalid file'), 400
    ext = validate_name.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify(error='Invalid file extension'), 400
    if validate_mimetype not in ALLOWED_MIMETYPES:
        return jsonify(error='Invalid MIME type'), 400

    safe_name = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    try:
        file.save(save_path)
    except Exception:
        return jsonify(error='Failed to save file'), 500

    # If S3 is configured, upload to S3 and remove local copy
    if s3_client:
        try:
            # upload_file preserves file from disk; set ContentType to the original/validated mimetype when available
            content_type_for_s3 = validate_mimetype if 'validate_mimetype' in locals() else file.mimetype
            s3_client.upload_file(save_path, S3_BUCKET, safe_name, ExtraArgs={'ContentType': content_type_for_s3, 'ACL': 'public-read'})
            public_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{safe_name}"
            try:
                os.remove(save_path)
            except Exception:
                pass
            return jsonify(url=public_url)
        except Exception:
            return jsonify(error='Failed to upload to S3'), 500

    return jsonify(url=f"/uploads/{safe_name}")


@app.route('/presign', methods=['POST'])
def presign():
    """Return a presigned PUT URL for direct upload to S3.

    Request JSON: { filename, content_type }
    Response JSON: { url: presigned_put_url, public_url }
    """
    from flask import request, jsonify

    if not s3_client:
        return jsonify(error='S3 not configured'), 400

    data = request.get_json() or {}
    filename = data.get('filename')
    content_type = data.get('content_type')
    if not filename or not content_type:
        return jsonify(error='filename and content_type required'), 400

    # Basic validation
    if '.' not in filename:
        return jsonify(error='Invalid file name'), 400
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify(error='Invalid file extension'), 400
    if content_type not in ALLOWED_MIMETYPES:
        return jsonify(error='Invalid MIME type'), 400

    key = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
    try:
        url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': S3_BUCKET, 'Key': key, 'ContentType': content_type},
            ExpiresIn=3600
        )
    except Exception as e:
        return jsonify(error='Failed to generate presigned URL'), 500

    public_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
    return jsonify(url=url, public_url=public_url)


### Socket events ###

@socketio.on('connect')
def on_connect():
    pass


@socketio.on('pubkey')
def on_pubkey(data):
    """Forward public key material to other participants in the room."""
    room = data.get('room')
    pubkey = data.get('pubkey')
    if not room or not pubkey:
        return
    # Forward to room excluding sender
    emit('pubkey', {'pubkey': pubkey}, to=room, include_self=False)


@socketio.on('join')
def on_join(data):
    from flask import request
    room = (data.get('room') or '').strip()
    username = (data.get('username') or '').strip()
    if not room or not username:
        emit('error', {'message': 'Room and username are required'})
        return

    members = rooms.get(room, [])
    if len(members) >= 2:
        emit('room-full')
        return

    join_room(room)
    rooms.setdefault(room, []).append({'sid': request.sid, 'username': username})
    members = rooms[room]

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
    room = data.get('room')
    text = (data.get('text') or '').strip()
    image = data.get('image')

    if not room or (not text and not image):
        return

    members = rooms.get(room, [])
    if not members:
        emit('error', {'message': 'Room not found'})
        return

    sender = next((m['username'] for m in members if m['sid'] == request.sid), None)
    if not sender:
        emit('error', {'message': 'You are not in this room'})
        return

    timestamp = datetime.now().strftime('%I:%M %p')
    payload = {'from': sender, 'text': text, 'timestamp': timestamp}
    if image:
        payload['image'] = image
    # forward encryption metadata if present so clients can decrypt
    if data.get('enc'):
        payload['enc'] = True
    if data.get('iv'):
        payload['iv'] = data.get('iv')
    if data.get('contentType'):
        payload['contentType'] = data.get('contentType')
    emit('message', payload, to=room)


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
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f'Chat server starting on port {port}')
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
