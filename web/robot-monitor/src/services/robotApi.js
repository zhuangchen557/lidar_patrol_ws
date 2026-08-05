import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080',
  timeout: 5000,
})

export function getHistory(params = {}) {
  return api.get('/api/history', { params }).then(({ data }) => data)
}

export function connectRobotStream({ onData, onState, onCommandResult }) {
  const url = import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws'
  const socket = new WebSocket(url)

  socket.addEventListener('open', () => onState?.('online'))
  socket.addEventListener('close', () => onState?.('offline'))
  socket.addEventListener('error', () => onState?.('error'))
  socket.addEventListener('message', (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'robot_status') onData?.(message)
      if (message.type === 'command_result') onCommandResult?.(message)
    } catch {
      onState?.('bad-data')
    }
  })

  return {
    close: () => socket.close(),
    sendCommand(command, payload = {}) {
      if (socket.readyState !== WebSocket.OPEN) return false
      socket.send(JSON.stringify({ type: 'command', command, ...payload }))
      return true
    },
  }
}
