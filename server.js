const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

const PORT = process.env.PORT || 3000;

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Track connected users per room
const rooms = {};

io.on('connection', (socket) => {
  let currentRoom = null;
  let currentUser = null;

  socket.on('join', ({ room, username }) => {
    // Check if room is full (max 2 users)
    if (rooms[room] && rooms[room].length >= 2) {
      socket.emit('room-full');
      return;
    }

    currentRoom = room;
    currentUser = username;

    socket.join(room);

    if (!rooms[room]) rooms[room] = [];
    rooms[room].push({ id: socket.id, username });

    // Notify everyone in the room
    io.to(room).emit('user-joined', {
      username,
      count: rooms[room].length,
      users: rooms[room].map(u => u.username)
    });

    socket.emit('join-success', { room, username });
  });

  socket.on('message', ({ room, text }) => {
    if (!currentRoom || !currentUser) return;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    io.to(room).emit('message', {
      from: currentUser,
      text,
      timestamp,
      self: false
    });
  });

  socket.on('typing', ({ room, username }) => {
    socket.to(room).emit('typing', { username });
  });

  socket.on('stop-typing', ({ room }) => {
    socket.to(room).emit('stop-typing');
  });

  socket.on('disconnect', () => {
    if (currentRoom && rooms[currentRoom]) {
      rooms[currentRoom] = rooms[currentRoom].filter(u => u.id !== socket.id);
      if (rooms[currentRoom].length === 0) {
        delete rooms[currentRoom];
      } else {
        io.to(currentRoom).emit('user-left', {
          username: currentUser,
          count: rooms[currentRoom].length
        });
      }
    }
  });
});

server.listen(PORT, () => {
  console.log(`Chat server running at http://localhost:${PORT}`);
});
