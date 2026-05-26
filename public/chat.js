const socket = io();

// DOM refs
const joinScreen   = document.getElementById('join-screen');
const chatScreen   = document.getElementById('chat-screen');
const usernameInput = document.getElementById('username-input');
const roomInput    = document.getElementById('room-input');
const joinBtn      = document.getElementById('join-btn');
const joinError    = document.getElementById('join-error');
const messagesEl   = document.getElementById('messages');
const msgInput     = document.getElementById('msg-input');
const sendBtn      = document.getElementById('send-btn');
const uploadBtn    = document.getElementById('upload-btn');
const imageInput   = document.getElementById('image-input');
const roomNameEl   = document.getElementById('room-name');
const statusEl     = document.getElementById('status-indicator');
const usersEl      = document.getElementById('users-display');
const typingEl     = document.getElementById('typing-indicator');

let currentRoom = null;
let currentUser = null;
let typingTimer  = null;
// E2EE state
let ecdhKeyPair = null;
let sharedKey = null; // CryptoKey for AES-GCM
let waitingForKey = false;
let pendingRemotePubkey = null;
let pendingEncryptedMessages = [];

// Helpers: base64 <-> ArrayBuffer
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}
function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

async function initE2EESetup() {
  try {
    ecdhKeyPair = await window.crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey']);
    const pub = await window.crypto.subtle.exportKey('raw', ecdhKeyPair.publicKey);
    const pubB64 = arrayBufferToBase64(pub);
    waitingForKey = true;
    socket.emit('pubkey', { room: currentRoom, pubkey: pubB64 });
    // If a remote pubkey arrived earlier, derive now
    if (pendingRemotePubkey) {
      await deriveSharedKeyFrom(pendingRemotePubkey);
      pendingRemotePubkey = null;
      appendSystem('Secure session established. Messages are end-to-end encrypted.');
      flushPendingEncryptedMessages();
    }
  } catch (err) {
    console.error('E2EE init failed', err);
  }
}

async function deriveSharedKeyFrom(b64RemotePub) {
  const raw = base64ToArrayBuffer(b64RemotePub);
  const remoteKey = await window.crypto.subtle.importKey('raw', raw, { name: 'ECDH', namedCurve: 'P-256' }, true, []);
  sharedKey = await window.crypto.subtle.deriveKey({ name: 'ECDH', public: remoteKey }, ecdhKeyPair.privateKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  waitingForKey = false;
  console.debug('Shared key derived, flushing pending messages', pendingEncryptedMessages.length);
  flushPendingEncryptedMessages();
}

function sendCurrentPublicKey() {
  if (!ecdhKeyPair || !currentRoom) {
    return;
  }
  window.crypto.subtle.exportKey('raw', ecdhKeyPair.publicKey)
    .then(pub => {
      const pubB64 = arrayBufferToBase64(pub);
      socket.emit('pubkey', { room: currentRoom, pubkey: pubB64 });
      console.debug('Resent public key to room', currentRoom);
    })
    .catch(err => {
      console.error('Failed to resend public key', err);
    });
}

function flushPendingEncryptedMessages() {
  if (!sharedKey || pendingEncryptedMessages.length === 0) {
    return;
  }

  pendingEncryptedMessages.forEach(payload => {
    appendMessage({ ...payload, isSelf: false });
  });
  pendingEncryptedMessages = [];
}

async function encryptText(plain) {
  const enc = new TextEncoder().encode(plain);
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const cipher = await window.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, sharedKey, enc);
  return { cipher: arrayBufferToBase64(cipher), iv: arrayBufferToBase64(iv) };
}

async function decryptText(b64cipher, b64iv) {
  const cipher = base64ToArrayBuffer(b64cipher);
  const iv = new Uint8Array(base64ToArrayBuffer(b64iv));
  const plainBuf = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, sharedKey, cipher);
  return new TextDecoder().decode(plainBuf);
}

async function encryptBytes(buffer) {
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const cipherBuf = await window.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, sharedKey, buffer);
  return { cipherBuffer: new Uint8Array(cipherBuf), iv: arrayBufferToBase64(iv) };
}

async function decryptToArrayBuffer(encryptedBuffer, b64iv) {
  const iv = new Uint8Array(base64ToArrayBuffer(b64iv));
  const plain = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, sharedKey, encryptedBuffer);
  return plain;
}

// ── Join ──────────────────────────────────────────────────
joinBtn.addEventListener('click', tryJoin);
[usernameInput, roomInput].forEach(el =>
  el.addEventListener('keydown', e => { if (e.key === 'Enter') tryJoin(); })
);

function tryJoin() {
  const username = usernameInput.value.trim();
  const room     = roomInput.value.trim();
  if (!username) return showError('Please enter your name.');
  if (!room)     return showError('Please enter a room code.');
  socket.emit('join', { room, username });
}

function showError(msg) {
  joinError.textContent = msg;
  joinError.classList.remove('hidden');
}

// ── Socket events ─────────────────────────────────────────
socket.on('join-success', ({ room, username }) => {
  currentRoom = room;
  currentUser = username;
  joinScreen.classList.add('hidden');
  chatScreen.classList.remove('hidden');
  roomNameEl.textContent = `# ${room}`;
  statusEl.textContent = 'Waiting for partner…';
  msgInput.focus();
  // initialize E2EE keypair and announce public key
  initE2EESetup().catch(console.error);
});

socket.on('room-full', () => {
  showError('Room is full. Max 2 people per room.');
});

socket.on('error', (data) => {
  showError(data.message || 'An error occurred.');
});

socket.on('user-joined', ({ username, count, users }) => {
  appendSystem(`${username} joined the room.`);
  usersEl.textContent = users.join(' & ');
  if (count === 2) {
    statusEl.textContent = 'Online';
    statusEl.classList.add('online');
    sendCurrentPublicKey();
  }
});

socket.on('user-left', ({ username, count }) => {
  appendSystem(`${username} left the room.`);
  if (count < 2) {
    statusEl.textContent = 'Waiting for partner…';
    statusEl.classList.remove('online');
  }
});

socket.on('message', (payload) => {
  const isSelf = payload.from === currentUser;
  if (payload.enc && !sharedKey && !isSelf) {
    pendingEncryptedMessages.push(payload);
    console.debug('Queued encrypted incoming message until shared key is ready', payload);
    appendSystem('Encrypted message received before the secure session was ready. It will be decrypted shortly.');
    return;
  }

  appendMessage({ ...payload, isSelf });
});

socket.on('typing', ({ username }) => {
  typingEl.textContent = `${username} is typing…`;
  typingEl.classList.remove('hidden');
});

socket.on('stop-typing', () => {
  typingEl.classList.add('hidden');
  typingEl.textContent = '';
});

socket.on('pubkey', async ({ pubkey }) => {
  try {
    if (!ecdhKeyPair) {
      // buffer until we generate our keypair
      pendingRemotePubkey = pubkey;
      return;
    }
    await deriveSharedKeyFrom(pubkey);
    appendSystem('Secure session established. Messages are end-to-end encrypted.');
  } catch (err) {
    console.error('Failed to process pubkey', err);
  }
});

// ── Sending messages ──────────────────────────────────────
sendBtn.addEventListener('click', sendMessage);
msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) sendMessage();
});

// Image upload flow
uploadBtn.addEventListener('click', () => imageInput.click());
imageInput.addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file || !currentRoom) return;

  const allowed = ['image/png','image/jpeg','image/gif','image/webp'];
  if (!allowed.includes(file.type)) {
    alert('Invalid file type. Allowed: png, jpg, jpeg, gif, webp.');
    imageInput.value = '';
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    alert('File is too large. Max 5 MB.');
    imageInput.value = '';
    return;
  }

  if (!sharedKey) { alert('Secure session not ready. Wait for partner to join.'); imageInput.value=''; return; }

  // Read file and encrypt bytes
  const buffer = await file.arrayBuffer();
  const { cipherBuffer, iv } = await encryptBytes(buffer);
  const encBlob = new Blob([cipherBuffer], { type: 'application/octet-stream' });
  const encFile = new File([encBlob], file.name + '.enc', { type: 'application/octet-stream' });
  const fd = new FormData();
  fd.append('file', encFile);
  fd.append('orig_name', file.name);
  fd.append('orig_content_type', file.type);
  uploadBtn.disabled = true;
  try {
    // Upload encrypted file to server (server will persist or upload to S3)
    let imageUrl = null;
    const res = await fetch('/upload', { method: 'POST', body: fd });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      alert(j.error || 'Upload failed');
      return;
    }
    const j = await res.json();
    imageUrl = j.url;
    // send message with image URL, iv, and original content type so recipient can decrypt and render
    socket.emit('message', { room: currentRoom, image: imageUrl, iv, enc: true, contentType: file.type });
    msgInput.value = '';
  } catch (err) {
    alert('Upload error');
  } finally {
    uploadBtn.disabled = false;
    imageInput.value = '';
  }
});

function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || !currentRoom) return;
  if (!sharedKey) { alert('Secure session not ready. Wait for partner to join.'); return; }
  encryptText(text).then(({cipher, iv}) => {
    socket.emit('message', { room: currentRoom, text: cipher, iv, enc: true });
  }).catch(err => { console.error(err); alert('Encryption failed'); });
  msgInput.value = '';
  stopTypingSignal();
}

// ── Typing indicator ──────────────────────────────────────
msgInput.addEventListener('input', () => {
  if (!currentRoom || !currentUser) return; // Don't send before joining
  socket.emit('typing', { room: currentRoom, username: currentUser });
  clearTimeout(typingTimer);
  typingTimer = setTimeout(stopTypingSignal, 1500);
});

function stopTypingSignal() {
  clearTimeout(typingTimer);
  if (currentRoom) {
    socket.emit('stop-typing', { room: currentRoom });
  }
}

// ── DOM helpers ───────────────────────────────────────────
function appendMessage({ from, text, image, timestamp, isSelf, enc, iv, contentType }) {
  const msg = document.createElement('div');
  msg.className = `msg ${isSelf ? 'self' : 'other'}`;

  const sender = document.createElement('span');
  sender.className = 'msg-sender';
  sender.textContent = isSelf ? 'You' : from;

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (text) {
    // If message is encrypted, server will forward text and iv plus enc flag in the object
    if (enc && iv) {
      // decrypt
      if (sharedKey) {
        decryptText(text, iv).then(plain => {
          const p = document.createElement('div');
          p.textContent = plain;
          bubble.appendChild(p);
        }).catch(() => {
          const p = document.createElement('div');
          p.textContent = '[Encrypted message]';
          bubble.appendChild(p);
        });
      } else {
        const p = document.createElement('div');
        p.textContent = '[Encrypted message - key not ready]';
        bubble.appendChild(p);
      }
    } else {
      const p = document.createElement('div');
      p.textContent = text;
      bubble.appendChild(p);
    }
  }

  if (image) {
    if (enc && iv && contentType) {
      // Encrypted image: fetch, decrypt, and render
      fetch(image).then(r => r.arrayBuffer()).then(async (encrypted) => {
        try {
          const plainBuf = await decryptToArrayBuffer(encrypted, iv);
          const blob = new Blob([plainBuf], { type: contentType });
          const url = URL.createObjectURL(blob);
          const img = document.createElement('img');
          img.className = 'msg-image';
          img.src = url;
          img.alt = 'Shared image';
          bubble.appendChild(img);
        } catch (err) {
          const note = document.createElement('div');
          note.textContent = '[Encrypted image - failed to decrypt]';
          bubble.appendChild(note);
        }
      }).catch(() => {
        const note = document.createElement('div');
        note.textContent = '[Failed to load image]';
        bubble.appendChild(note);
      });
    } else {
      const img = document.createElement('img');
      img.className = 'msg-image';
      img.src = image;
      img.alt = 'Shared image';
      bubble.appendChild(img);
    }
  }

  const time = document.createElement('span');
  time.className = 'msg-time';
  time.textContent = timestamp;

  msg.appendChild(sender);
  msg.appendChild(bubble);
  msg.appendChild(time);

  messagesEl.appendChild(msg);
  scrollToBottom();
}

function appendSystem(text) {
  const el = document.createElement('div');
  el.className = 'system-msg';
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
