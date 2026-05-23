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
const roomNameEl   = document.getElementById('room-name');
const statusEl     = document.getElementById('status-indicator');
const usersEl      = document.getElementById('users-display');
const typingEl     = document.getElementById('typing-indicator');

let currentRoom = null;
let currentUser = null;
let typingTimer  = null;

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
  }
});

socket.on('user-left', ({ username, count }) => {
  appendSystem(`${username} left the room.`);
  if (count < 2) {
    statusEl.textContent = 'Waiting for partner…';
    statusEl.classList.remove('online');
  }
});

socket.on('message', ({ from, text, timestamp }) => {
  const isSelf = from === currentUser;
  appendMessage({ from, text, timestamp, isSelf });
});

socket.on('typing', ({ username }) => {
  typingEl.textContent = `${username} is typing…`;
  typingEl.classList.remove('hidden');
});

socket.on('stop-typing', () => {
  typingEl.classList.add('hidden');
  typingEl.textContent = '';
});

// ── Sending messages ──────────────────────────────────────
sendBtn.addEventListener('click', sendMessage);
msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) sendMessage();
});

function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || !currentRoom) return;
  socket.emit('message', { room: currentRoom, text });
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
function appendMessage({ from, text, timestamp, isSelf }) {
  const msg = document.createElement('div');
  msg.className = `msg ${isSelf ? 'self' : 'other'}`;
  msg.innerHTML = `
    <span class="msg-sender">${isSelf ? 'You' : escapeHtml(from)}</span>
    <div class="msg-bubble">${escapeHtml(text)}</div>
    <span class="msg-time">${timestamp}</span>
  `;
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
