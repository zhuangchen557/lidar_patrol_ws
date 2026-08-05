<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { connectRobotStream } from './services/robotApi'

const publicDemo = import.meta.env.VITE_PUBLIC_DEMO === 'true'
const mode = ref(publicDemo ? 'mock' : (localStorage.getItem('robot-data-mode') || import.meta.env.VITE_DATA_MODE || 'mock'))
const connectionState = ref(mode.value === 'mock' ? 'demo' : 'connecting')
const missionState = ref('待命')
const commandMessage = ref('控制按钮当前仅用于通信测试，不会驱动真实电机。')
const lastUpdated = ref('—')
const readings = ref({ temperature: 25.6, humidity: 58, co: 12, noise: 46, x: 0, y: 0 })
const history = ref([])
const chartEl = ref()
const trackEl = ref()
let timer
let robotConnection
let chart
let track

const limits = { temperature: 35, humidity: 80, co: 50, noise: 85 }
const cards = computed(() => [
  ['温度', readings.value.temperature, '℃', 'temperature'],
  ['湿度', readings.value.humidity, '%', 'humidity'],
  ['CO 浓度', readings.value.co, 'ppm', 'co'],
  ['噪声', readings.value.noise, 'dB', 'noise'],
])
const alarms = computed(() => cards.value.filter(([, value, , key]) => Number(value) > limits[key]))
const statusText = computed(() => ({ demo: '演示模式', connecting: '连接中', online: '后端在线', offline: '后端离线', error: '连接异常', 'bad-data': '数据异常' }[connectionState.value] || '未知'))
const canControl = computed(() => mode.value === 'mock' || connectionState.value === 'online')

function acceptData(data) {
  const pose = data.pose || {}
  readings.value = {
    ...readings.value,
    temperature: data.temperature ?? readings.value.temperature,
    humidity: data.humidity ?? readings.value.humidity,
    co: data.co ?? readings.value.co,
    noise: data.noise ?? readings.value.noise,
    x: data.x ?? pose.x ?? readings.value.x,
    y: data.y ?? pose.y ?? readings.value.y,
  }
  if (data.mission_state) missionState.value = data.mission_state
  lastUpdated.value = new Date(data.timestamp || Date.now()).toLocaleTimeString()
  history.value.push({ time: lastUpdated.value, ...readings.value })
  if (history.value.length > 30) history.value.shift()
  renderCharts()
}

function mockTick() {
  const last = readings.value
  const moving = missionState.value === '巡检中'
  const nextX = moving ? last.x + 0.12 : last.x
  acceptData({
    temperature: +(last.temperature + (Math.random() - 0.5) * 0.8).toFixed(1),
    humidity: +(last.humidity + (Math.random() - 0.5) * 2).toFixed(1),
    co: Math.max(0, +(last.co + (Math.random() - 0.5) * 4).toFixed(1)),
    noise: Math.max(0, +(last.noise + (Math.random() - 0.5) * 5).toFixed(1)),
    x: +nextX.toFixed(2),
    y: +(Math.sin(nextX / 2) * 1.2).toFixed(2),
  })
}

function renderCharts() {
  chart?.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['温度', '湿度', 'CO', '噪声'], textStyle: { color: '#a8b3c7' } },
    xAxis: { type: 'category', data: history.value.map((p) => p.time), axisLabel: { color: '#8390a5' } },
    yAxis: { type: 'value', axisLabel: { color: '#8390a5' }, splitLine: { lineStyle: { color: '#26334a' } } },
    series: [
      ['温度', 'temperature', '#35d6b5'], ['湿度', 'humidity', '#4ca8ff'],
      ['CO', 'co', '#ffb454'], ['噪声', 'noise', '#a78bfa'],
    ].map(([name, key, color]) => ({ name, type: 'line', smooth: true, showSymbol: false, data: history.value.map((p) => p[key]), lineStyle: { color } })),
  })
  track?.setOption({
    xAxis: { type: 'value', axisLabel: { color: '#8390a5' }, splitLine: { lineStyle: { color: '#26334a' } } },
    yAxis: { type: 'value', axisLabel: { color: '#8390a5' }, splitLine: { lineStyle: { color: '#26334a' } } },
    series: [{ type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 3, color: '#35d6b5' }, data: history.value.map((p) => [p.x, p.y]) }],
  })
}

function stopDataSource() {
  clearInterval(timer)
  timer = undefined
  robotConnection?.close()
  robotConnection = undefined
}

function startDataSource() {
  stopDataSource()
  history.value = []
  if (mode.value === 'mock') {
    connectionState.value = 'demo'
    mockTick()
    timer = setInterval(mockTick, 1000)
    return
  }
  connectionState.value = 'connecting'
  robotConnection = connectRobotStream({
    onData: acceptData,
    onState: (state) => { connectionState.value = state },
    onCommandResult: (result) => {
      commandMessage.value = result.message || (result.ok ? '命令已接收' : '命令被拒绝')
      if (result.mission_state) missionState.value = result.mission_state
    },
  })
}

function setMode(nextMode) {
  if (mode.value === nextMode) return
  mode.value = nextMode
  localStorage.setItem('robot-data-mode', nextMode)
  commandMessage.value = nextMode === 'mock' ? '正在使用浏览器模拟数据。' : '正在连接本机 C++ 模拟后端。'
  startDataSource()
}

function sendCommand(command) {
  const labels = { start_patrol: '开始巡检', pause_patrol: '暂停巡检', stop_patrol: '停止巡检' }
  const states = { start_patrol: '巡检中', pause_patrol: '已暂停', stop_patrol: '待命' }
  if (mode.value === 'mock') {
    missionState.value = states[command]
    commandMessage.value = `演示模式：已模拟“${labels[command]}”，未发送到小车。`
    return
  }
  const sent = robotConnection?.sendCommand(command)
  commandMessage.value = sent ? `已向 C++ 后端发送“${labels[command]}”。` : '后端未连接，命令没有发送。'
}

function resize() { chart?.resize(); track?.resize() }

onMounted(async () => {
  await nextTick()
  chart = echarts.init(chartEl.value)
  track = echarts.init(trackEl.value)
  window.addEventListener('resize', resize)
  startDataSource()
})

onBeforeUnmount(() => {
  stopDataSource()
  window.removeEventListener('resize', resize)
  chart?.dispose()
  track?.dispose()
})
</script>

<template>
  <main>
    <header>
      <div><p class="eyebrow">ROBOT OPERATIONS</p><h1>智能巡检车监控中心</h1></div>
      <div class="header-actions">
        <div v-if="!publicDemo" class="mode-switch" aria-label="数据来源切换">
          <button :class="{ active: mode === 'mock' }" @click="setMode('mock')">演示数据</button>
          <button :class="{ active: mode === 'backend' }" @click="setMode('backend')">C++ 后端</button>
        </div>
        <span v-else class="public-badge">公共只读演示</span>
        <span class="status" :class="connectionState"><i></i>{{ statusText }}</span>
      </div>
    </header>

    <section class="cards">
      <article v-for="([label, value, unit, key]) in cards" :key="key" :class="{ danger: value > limits[key] }">
        <p>{{ label }}</p><strong>{{ value }}</strong><span>{{ unit }}</span>
      </article>
    </section>

    <section v-if="alarms.length" class="alarm">⚠ {{ alarms.map((item) => item[0]).join('、') }}超过设定阈值</section>

    <section v-if="!publicDemo" class="control-panel">
      <div><p class="eyebrow">SAFE COMMAND TEST</p><h2>巡检任务控制</h2><p class="control-note">{{ commandMessage }}</p></div>
      <div class="control-buttons">
        <button :disabled="!canControl" @click="sendCommand('start_patrol')">开始巡检</button>
        <button :disabled="!canControl" class="secondary" @click="sendCommand('pause_patrol')">暂停</button>
        <button :disabled="!canControl" class="stop" @click="sendCommand('stop_patrol')">停止</button>
      </div>
    </section>

    <section class="grid">
      <article class="panel wide"><div class="panel-title"><h2>环境数据趋势</h2><span>最近 30 秒</span></div><div ref="chartEl" class="chart"></div></article>
      <article class="panel"><div class="panel-title"><h2>巡检轨迹</h2><span>x {{ readings.x }} / y {{ readings.y }}</span></div><div ref="trackEl" class="chart"></div></article>
      <article class="panel summary"><div class="panel-title"><h2>任务状态</h2></div><dl><div><dt>当前任务</dt><dd>{{ missionState }}</dd></div><div><dt>数据来源</dt><dd>{{ mode === 'mock' ? '浏览器模拟' : 'C++ 后端' }}</dd></div><div><dt>最后更新</dt><dd>{{ lastUpdated }}</dd></div><div><dt>报警数量</dt><dd>{{ alarms.length }}</dd></div></dl></article>
    </section>
  </main>
</template>
