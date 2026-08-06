<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { connectRobotStream } from './services/robotApi'

const sourceMode = ref('robot')
const connectionState = ref('connecting')
const controlUnlocked = ref(false)
const showUnlock = ref(false)
const unlockPassword = ref('')
const unlockPending = ref(false)
const unlockError = ref('')
const missionState = ref('待命')
const commandMessage = ref('正在连接小车后端。控制功能默认锁定。')
const lastUpdatedAt = ref(0)
const clock = ref(Date.now())
const readings = ref({
  temperature: 25.6,
  humidity: 58,
  noise: 46,
  x: 0,
  y: 0,
  yaw: 0,
  battery: null,
  speed: 0,
})
const history = ref([])
const alarmLog = ref([])
const chartEl = ref()
const trackEl = ref()

let dataTimer
let clockTimer
let robotConnection
let chart
let track
let activeAlarmKeys = new Set()

const limits = { temperature: 35, humidity: 80, noise: 85 }
const sensorCards = computed(() => [
  { label: '温度', value: readings.value.temperature, unit: '℃', key: 'temperature', hint: `阈值 ${limits.temperature}℃` },
  { label: '湿度', value: readings.value.humidity, unit: '%', key: 'humidity', hint: `阈值 ${limits.humidity}%` },
  { label: '噪声', value: readings.value.noise, unit: 'dB', key: 'noise', hint: `阈值 ${limits.noise}dB` },
])
const activeAlarms = computed(() => sensorCards.value.filter((item) => Number(item.value) > limits[item.key]))
const sourceText = computed(() => sourceMode.value === 'mock' ? '浏览器演示数据' : '真实小车后端')
const isDataStale = computed(() => sourceMode.value === 'robot' && lastUpdatedAt.value > 0 && clock.value - lastUpdatedAt.value > 5000)
const statusText = computed(() => {
  if (isDataStale.value) return '数据已超时'
  return {
    demo: '演示运行中',
    connecting: '正在连接',
    online: '小车在线',
    offline: '小车离线',
    error: '连接异常',
    'bad-data': '数据异常',
  }[connectionState.value] || '状态未知'
})
const statusClass = computed(() => isDataStale.value ? 'stale' : connectionState.value)
const canControl = computed(() => sourceMode.value === 'mock' || (connectionState.value === 'online' && controlUnlocked.value && !isDataStale.value))
const lastUpdatedText = computed(() => lastUpdatedAt.value ? new Date(lastUpdatedAt.value).toLocaleTimeString() : '等待数据')
const dataAgeText = computed(() => {
  if (!lastUpdatedAt.value) return '—'
  const seconds = Math.max(0, Math.floor((clock.value - lastUpdatedAt.value) / 1000))
  return seconds < 2 ? '刚刚' : `${seconds} 秒前`
})
const batteryText = computed(() => readings.value.battery == null ? '待接入' : `${readings.value.battery}%`)

function recordAlarms() {
  const nextKeys = new Set(activeAlarms.value.map((item) => item.key))
  for (const alarm of activeAlarms.value) {
    if (!activeAlarmKeys.has(alarm.key)) {
      alarmLog.value.unshift({
        id: `${alarm.key}-${Date.now()}`,
        time: new Date().toLocaleTimeString(),
        message: `${alarm.label}达到 ${alarm.value}${alarm.unit}，超过阈值`,
      })
    }
  }
  activeAlarmKeys = nextKeys
  if (alarmLog.value.length > 20) alarmLog.value.length = 20
}

function acceptData(data) {
  const sensors = data.sensors || data
  const robot = data.robot || data
  const pose = data.pose || data
  readings.value = {
    ...readings.value,
    temperature: sensors.temperature ?? readings.value.temperature,
    humidity: sensors.humidity ?? readings.value.humidity,
    noise: sensors.noise ?? readings.value.noise,
    x: pose.x ?? readings.value.x,
    y: pose.y ?? readings.value.y,
    yaw: pose.yaw ?? readings.value.yaw,
    battery: robot.battery ?? readings.value.battery,
    speed: robot.speed ?? readings.value.speed,
  }
  if (robot.taskStatus || robot.task_status || data.mission_state) {
    missionState.value = robot.taskStatus || robot.task_status || data.mission_state
  }
  lastUpdatedAt.value = Number(data.timestamp) || Date.now()
  clock.value = Date.now()
  history.value.push({ time: new Date(lastUpdatedAt.value).toLocaleTimeString(), ...readings.value })
  if (history.value.length > 60) history.value.shift()
  recordAlarms()
  renderCharts()
}

function mockTick() {
  const last = readings.value
  const moving = missionState.value === '巡检中'
  const nextX = moving ? last.x + 0.12 : last.x
  acceptData({
    source: 'simulator',
    timestamp: Date.now(),
    sensors: {
      temperature: +(last.temperature + (Math.random() - 0.5) * 0.8).toFixed(1),
      humidity: +(last.humidity + (Math.random() - 0.5) * 2).toFixed(1),
      noise: Math.max(0, +(last.noise + (Math.random() - 0.5) * 5).toFixed(1)),
    },
    robot: {
      taskStatus: missionState.value,
      battery: last.battery ?? 87,
      speed: moving ? 0.32 : 0,
    },
    pose: {
      x: +nextX.toFixed(2),
      y: +(Math.sin(nextX / 2) * 1.2).toFixed(2),
      yaw: +(Math.cos(nextX / 3) * 0.35).toFixed(2),
    },
  })
}

function renderCharts() {
  const axisText = { color: '#7f91aa' }
  const splitLine = { lineStyle: { color: 'rgba(123, 151, 185, .13)' } }
  chart?.setOption({
    animationDuration: 350,
    tooltip: { trigger: 'axis', backgroundColor: '#101f32', borderColor: '#2d4563', textStyle: { color: '#eef6ff' } },
    legend: { data: ['温度', '湿度', '噪声'], textStyle: { color: '#9aabc1' }, top: 4 },
    grid: { left: 44, right: 50, top: 46, bottom: 28 },
    xAxis: { type: 'category', data: history.value.map((point) => point.time), axisLabel: axisText, axisLine: { lineStyle: { color: '#2b405c' } } },
    yAxis: [
      { type: 'value', axisLabel: axisText, splitLine },
      { type: 'value', axisLabel: { ...axisText, formatter: '{value} dB' }, splitLine: { show: false } },
    ],
    series: [
      ['温度', 'temperature', '#36ddb9', 0],
      ['湿度', 'humidity', '#54a8ff', 0],
      ['噪声', 'noise', '#bd86ff', 1],
    ].map(([name, key, color, yAxisIndex]) => ({
      name,
      type: 'line',
      yAxisIndex,
      smooth: true,
      showSymbol: false,
      data: history.value.map((point) => point[key]),
      lineStyle: { width: 2, color },
      areaStyle: { color: `${color}14` },
    })),
  })

  const trackPoints = history.value.map((point) => [point.x, point.y])
  track?.setOption({
    animationDuration: 350,
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 24, top: 24, bottom: 34 },
    xAxis: { type: 'value', name: 'X / m', nameTextStyle: axisText, axisLabel: axisText, splitLine },
    yAxis: { type: 'value', name: 'Y / m', nameTextStyle: axisText, axisLabel: axisText, splitLine },
    series: [
      { type: 'line', symbol: 'none', lineStyle: { width: 3, color: '#36ddb9' }, data: trackPoints },
      { type: 'effectScatter', symbolSize: 12, itemStyle: { color: '#f7c75d' }, data: trackPoints.length ? [trackPoints.at(-1)] : [] },
    ],
  })
}

function stopDataSource() {
  clearInterval(dataTimer)
  dataTimer = undefined
  robotConnection?.close()
  robotConnection = undefined
}

function startDemo() {
  stopDataSource()
  sourceMode.value = 'mock'
  connectionState.value = 'demo'
  controlUnlocked.value = false
  missionState.value = '待命'
  history.value = []
  commandMessage.value = '演示控制只改变网页状态，不会向真实小车发送命令。'
  mockTick()
  dataTimer = setInterval(mockTick, 1000)
}

function connectBackend() {
  stopDataSource()
  sourceMode.value = 'robot'
  connectionState.value = 'connecting'
  controlUnlocked.value = false
  history.value = []
  lastUpdatedAt.value = 0
  commandMessage.value = '正在连接小车后端。连接成功后可输入密码解锁控制。'
  robotConnection = connectRobotStream({
    onData: acceptData,
    onState: (state) => {
      connectionState.value = state
      if (state !== 'online') controlUnlocked.value = false
      if (state === 'offline' || state === 'error') commandMessage.value = '小车后端未连接。可重新连接，或启动演示数据。'
    },
    onCommandResult: (result) => {
      commandMessage.value = result.message || (result.ok ? '命令已接收' : '命令被拒绝')
      if (result.mission_state) missionState.value = result.mission_state
      if (result.code === 'unauthorized') controlUnlocked.value = false
    },
    onAuthResult: (result) => {
      unlockPending.value = false
      unlockPassword.value = ''
      if (result.ok) {
        controlUnlocked.value = true
        showUnlock.value = false
        unlockError.value = ''
        commandMessage.value = '控制权限已解锁。请确认现场安全后再发送命令。'
      } else {
        controlUnlocked.value = false
        unlockError.value = result.message || '密码错误，无法解锁控制。'
      }
    },
  })
}

function openUnlockDialog() {
  if (connectionState.value !== 'online') {
    commandMessage.value = '后端未在线，暂时无法解锁控制。'
    return
  }
  unlockPassword.value = ''
  unlockError.value = ''
  showUnlock.value = true
}

function submitUnlock() {
  if (!unlockPassword.value) {
    unlockError.value = '请输入控制密码。'
    return
  }
  unlockPending.value = true
  unlockError.value = ''
  if (!robotConnection?.authenticate(unlockPassword.value)) {
    unlockPending.value = false
    unlockError.value = '连接已断开，请重新连接后再试。'
  }
}

function lockControl() {
  robotConnection?.lock()
  controlUnlocked.value = false
  commandMessage.value = '控制权限已锁定。监控数据仍可正常查看。'
}

function sendCommand(command) {
  const labels = {
    start_patrol: '开始巡检',
    pause_patrol: '暂停巡检',
    stop_patrol: '结束巡检',
    emergency_stop: '紧急停止',
  }
  const states = {
    start_patrol: '巡检中',
    pause_patrol: '已暂停',
    stop_patrol: '待命',
    emergency_stop: '紧急停止',
  }
  if (!canControl.value) {
    commandMessage.value = '控制功能尚未解锁，命令没有发送。'
    return
  }
  if (sourceMode.value === 'mock') {
    missionState.value = states[command]
    commandMessage.value = `演示控制：已模拟“${labels[command]}”，没有向小车发送命令。`
    return
  }
  const sent = robotConnection?.sendCommand(command)
  commandMessage.value = sent ? `已发送“${labels[command]}”，等待后端确认。` : '连接已断开，命令没有发送。'
}

function clearAlarmLog() {
  alarmLog.value = []
}

function resize() {
  chart?.resize()
  track?.resize()
}

onMounted(async () => {
  await nextTick()
  chart = echarts.init(chartEl.value)
  track = echarts.init(trackEl.value)
  clockTimer = setInterval(() => { clock.value = Date.now() }, 1000)
  window.addEventListener('resize', resize)
  connectBackend()
})

onBeforeUnmount(() => {
  stopDataSource()
  clearInterval(clockTimer)
  window.removeEventListener('resize', resize)
  chart?.dispose()
  track?.dispose()
})
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div class="brand-block">
        <p class="eyebrow">ROBOT OPERATIONS CENTER</p>
        <h1>智能巡检车监控中心</h1>
        <p class="subtitle">环境监测、巡检轨迹与任务控制统一工作台</p>
      </div>
      <div class="header-actions">
        <button class="source-action" @click="sourceMode === 'mock' ? connectBackend() : startDemo()">
          {{ sourceMode === 'mock' ? '连接真实小车' : '启动演示数据' }}
        </button>
        <span class="source-badge">{{ sourceText }}</span>
        <span class="status" :class="statusClass"><i></i>{{ statusText }}</span>
        <button
          v-if="sourceMode === 'robot'"
          class="security-button"
          :class="{ unlocked: controlUnlocked }"
          :disabled="connectionState !== 'online'"
          @click="controlUnlocked ? lockControl() : openUnlockDialog()"
        >
          {{ controlUnlocked ? '锁定控制' : '解锁控制' }}
        </button>
        <span v-else class="demo-badge">演示控制可用</span>
      </div>
    </header>

    <section class="metrics-grid">
      <article
        v-for="card in sensorCards"
        :key="card.key"
        class="metric-card"
        :class="{ danger: card.value > limits[card.key] }"
      >
        <div class="metric-heading"><span>{{ card.label }}</span><small>{{ card.hint }}</small></div>
        <div class="metric-value"><strong>{{ card.value }}</strong><span>{{ card.unit }}</span></div>
      </article>
      <article class="metric-card task-card">
        <div class="metric-heading"><span>车辆任务</span><small>{{ sourceMode === 'mock' ? '演示状态' : '实时状态' }}</small></div>
        <div class="task-value">{{ missionState }}</div>
        <p>{{ readings.speed.toFixed(2) }} m/s · 电量 {{ batteryText }}</p>
      </article>
    </section>

    <section v-if="activeAlarms.length" class="alarm-banner">
      <strong>环境数据报警</strong>
      <span>{{ activeAlarms.map((item) => `${item.label} ${item.value}${item.unit}`).join(' · ') }}</span>
    </section>

    <section class="control-panel">
      <div>
        <p class="eyebrow">MISSION CONTROL</p>
        <h2>巡检任务控制</h2>
        <p class="control-note">{{ commandMessage }}</p>
      </div>
      <div class="control-buttons">
        <button :disabled="!canControl" @click="sendCommand('start_patrol')">开始巡检</button>
        <button :disabled="!canControl" class="secondary" @click="sendCommand('pause_patrol')">暂停</button>
        <button :disabled="!canControl" class="secondary" @click="sendCommand('stop_patrol')">结束巡检</button>
        <button :disabled="!canControl" class="emergency" @click="sendCommand('emergency_stop')">紧急停止</button>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="panel trajectory-panel">
        <div class="panel-title">
          <div><p class="panel-kicker">POSITION</p><h2>巡检轨迹</h2></div>
          <span>x {{ readings.x.toFixed(2) }} / y {{ readings.y.toFixed(2) }} / θ {{ readings.yaw.toFixed(2) }}</span>
        </div>
        <div ref="trackEl" class="chart chart-large"></div>
      </article>

      <article class="panel status-panel">
        <div class="panel-title"><div><p class="panel-kicker">STATUS</p><h2>车辆与连接</h2></div></div>
        <dl>
          <div><dt>当前任务</dt><dd>{{ missionState }}</dd></div>
          <div><dt>数据来源</dt><dd>{{ sourceText }}</dd></div>
          <div><dt>连接状态</dt><dd>{{ statusText }}</dd></div>
          <div><dt>最后更新</dt><dd>{{ lastUpdatedText }}</dd></div>
          <div><dt>数据时间</dt><dd>{{ dataAgeText }}</dd></div>
          <div><dt>控制权限</dt><dd>{{ sourceMode === 'mock' ? '演示控制' : (controlUnlocked ? '已解锁' : '已锁定') }}</dd></div>
        </dl>
      </article>

      <article class="panel trend-panel">
        <div class="panel-title">
          <div><p class="panel-kicker">ENVIRONMENT</p><h2>环境数据趋势</h2></div>
          <span>最近 60 秒</span>
        </div>
        <div ref="chartEl" class="chart"></div>
      </article>

      <article class="panel alarm-panel">
        <div class="panel-title">
          <div><p class="panel-kicker">ALERTS</p><h2>报警记录</h2></div>
          <button class="text-button" :disabled="!alarmLog.length" @click="clearAlarmLog">清空记录</button>
        </div>
        <div v-if="alarmLog.length" class="alarm-list">
          <div v-for="alarm in alarmLog" :key="alarm.id" class="alarm-item">
            <span class="alarm-dot"></span><p>{{ alarm.message }}</p><time>{{ alarm.time }}</time>
          </div>
        </div>
        <div v-else class="empty-state">当前没有报警记录</div>
      </article>
    </section>

    <div v-if="showUnlock" class="modal-backdrop" @click.self="showUnlock = false">
      <form class="unlock-dialog" @submit.prevent="submitUnlock">
        <p class="eyebrow">CONTROL AUTHORIZATION</p>
        <h2>解锁小车控制</h2>
        <p>密码将直接发送给 C++ 后端验证，不会保存在浏览器中。</p>
        <label for="control-password">控制密码</label>
        <input id="control-password" v-model="unlockPassword" type="password" autocomplete="current-password" autofocus />
        <p v-if="unlockError" class="form-error">{{ unlockError }}</p>
        <div class="dialog-actions">
          <button type="button" class="secondary" @click="showUnlock = false">取消</button>
          <button type="submit" :disabled="unlockPending">{{ unlockPending ? '验证中…' : '确认解锁' }}</button>
        </div>
      </form>
    </div>
  </main>
</template>
