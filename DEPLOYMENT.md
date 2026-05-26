# Online Chat App - Deployment Guide

## What Was Fixed

### The "404 Not Found" Issue
The original server.py had problems serving static files on Railway:

1. **Relative Path Issues**: `static_folder='public'` used relative paths that don't work reliably when deployed
2. **Incomplete Route Coverage**: CSS and JS weren't explicitly routed; Flask couldn't find them
3. **No Error Handling**: Missing error handlers and debug logging
4. **Eventlet Deprecation**: Using deprecated async mode

### Solution

**Updated server.py now:**
- Uses absolute paths: `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`
- Serves static assets from the `public/` folder and exposes `/uploads/` for uploaded images
- Adds POST `/upload` with size and type validation, and returns JSON `{url: '/uploads/<file>'}`
- Uses `MAX_CONTENT_LENGTH` to enforce 5 MB limit server-side

**Requirements & Procfile:**
- `requirements.txt` already includes `flask`, `flask-socketio`, `eventlet`, and `gunicorn` — these are suitable for production Socket.IO with Gunicorn + eventlet worker.
- **Procfile** updated to use Gunicorn with the eventlet worker:
   - `web: gunicorn -k eventlet -w 1 server:app`
   - Single worker (`-w 1`) is recommended for WebSocket apps when using Socket.IO; scale with caution and consider using external message queue/manager.

**Important note about uploads on cloud hosts:**
- Most PaaS (Heroku, Railway, Render) use ephemeral filesystems. Files saved to `uploads/` will be lost when the dyno/container restarts or is redeployed.
- For persistent image storage in production, use an external object store such as AWS S3, Google Cloud Storage, or Azure Blob Storage. Keep the current `uploads/` behavior for temporary/local storage.


---

## Project Structure
```
Online Chat/
├── server.py              ← Flask + SocketIO backend
├── requirements.txt       ← Python dependencies
├── Procfile              ← Railway deployment config
├── .gitignore
└── public/
    ├── index.html        ← Main HTML
    ├── style.css         ← Styling
    └── chat.js           ← Client-side logic
```

---

## To Re-Deploy on Railway

1. **Push updated code to GitHub:**
   ```bash
   cd "c:\VS SANDBOX\Online Chat"
   git add -A
   git commit -m "Fix static file serving and add production config"
   git push origin main
   ```

2. **Railway will automatically:**
   - Detect the Procfile
   - Install dependencies from requirements.txt
   - Run: `python server.py`
   - Listen on PORT 8080 (or whatever Railway assigns)

3. **Custom domain should resolve within 5 minutes**

---

## Testing Locally

```bash
cd "c:\VS SANDBOX\Online Chat"
python server.py
```

Then visit: http://localhost:8080

---

## Features Preserved
✓ Real-time messaging with Socket.io
✓ Typing indicators
✓ Room management (max 2 people)
✓ Join/leave notifications
✓ XSS protection
✓ Race condition protection

---

## If Still Getting 404

1. Check Railway logs: Look for "✓ Static files:" line
2. Verify public folder exists with index.html
3. Hard refresh browser (Ctrl+Shift+R)
4. Clear Cloudflare cache if needed

### Enabling S3 presigned uploads

- Set these environment variables in your deployment platform:
   - `S3_BUCKET` — your S3 bucket name
   - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` (optional)

- The server exposes a `/presign` endpoint that returns a presigned PUT URL and a `public_url`. The client will upload directly to S3 using that URL and then send the `public_url` in the chat message.

- S3 bucket requirements:
   - Configure CORS to allow PUT from your origin. Example CORS policy:

```xml
<CORSConfiguration>
   <CORSRule>
      <AllowedOrigin>*</AllowedOrigin>
      <AllowedMethod>PUT</AllowedMethod>
      <AllowedHeader>*</AllowedHeader>
   </CORSRule>
</CORSConfiguration>
```

- Ensure the bucket or uploaded objects are publicly readable (or configure signed GETs) if you want images to be visible without extra signing. The server returns a standard S3 URL `https://{bucket}.s3.amazonaws.com/{key}` as `public_url`.
