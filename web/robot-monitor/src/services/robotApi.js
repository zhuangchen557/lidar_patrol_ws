import axios from 'axios'

const host = window.location.hostname || 'localhost'
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || `${httpProtocol}//${host}:8080`,
  timeout: 5000,
})

export function getHistory(params = {}) {
  return api.get('/api/history', { params }).then(({ data }) => data)
}

export function connectRobotStream({ onData, onState, onCommandResult, onAuthResult }) {
  const url = import.meta.env.VITE_WS_URL || `${wsProtocol}//${host}:8080/ws`
  const socket = new WebSocket(url)
  let closedByClient = false

  socket.addEventListener('open', () => onState?.('online'))
  socket.addEventListener('close', () => {
    if (!closedByClient) onState?.('offline')
  })
  socket.addEventListener('error', () => onState?.('error'))
  socket.addEventListener('message', (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'robot_status') onData?.(message)
      if (message.type === 'command_result') onCommandResult?.(message)
      if (message.type === 'auth_result') onAuthResult?.(message)
    } catch {
      onState?.('bad-data')
    }
  })

  function send(message) {
    if (socket.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(message))
    return true
  }

  return {
    close() {
      closedByClient = true
      socket.close()
    },
    authenticate(password) {
      return send({ type: 'auth', password })
    },
    lock() {
      return send({ type: 'lock' })
    },
    sendCommand(command, payload = {}) {
      return send({ type: 'command', command, ...payload })
    },
  }
}
