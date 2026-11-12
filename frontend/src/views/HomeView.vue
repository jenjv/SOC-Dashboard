<script setup>
import { computed, onMounted, ref } from 'vue'
import { getEvents, getStats, getAlerts, getAlert, updateAlertStatus } from '@/services/api'

const search = ref('')
const severityFilter = ref('All')
const selectedEvent = ref(null)
const apiConnected = ref(false)
const apiError = ref('')
const stats = ref(null) 
const alerts = ref([])

const hosts = [
  { name: 'SOC-NGINX', role: 'Web server', status: 'Online', address: 'VM 01' },
  { name: 'SOC-DATABASE', role: 'Database server', status: 'Online', address: 'VM 02' },
  { name: 'SOC-APPLICATION', role: 'Application server', status: 'Online', address: 'VM 03' },
]

const events = ref([
  {
    id: 'EVT-1042',
    severity: 'High',
    name: 'Repeated SSH authentication failures',
    host: 'SOC-APPLICATION',
    time: '11:42 PM',
    status: 'Open',
    details: 'Sample event: several failed SSH sign-in attempts were recorded.',
  },
  {
    id: 'EVT-1041',
    severity: 'Medium',
    name: 'Unusual HTTP 404 request burst',
    host: 'SOC-NGINX',
    time: '11:36 PM',
    status: 'Investigating',
    details: 'Sample event: the web server recorded a burst of requests for missing pages.',
  },
  {
    id: 'EVT-1040',
    severity: 'Low',
    name: 'Database service restarted',
    host: 'SOC-DATABASE',
    time: '11:18 PM',
    status: 'Closed',
    details: 'Sample event: the database service restarted.',
  },
  {
    id: 'EVT-1039',
    severity: 'High',
    name: 'New user account created',
    host: 'SOC-APPLICATION',
    time: '10:54 PM',
    status: 'Open',
    details: 'Sample event: a new local user account was created.',
  },
  {
    id: 'EVT-1038',
    severity: 'Medium',
    name: 'Nginx configuration file changed',
    host: 'SOC-NGINX',
    time: '10:27 PM',
    status: 'Investigating',
    details: 'Sample event: a change to the Nginx configuration was detected.',
  },
])

function displayLabel(value) {
  if (!value) return 'Unknown'
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatTime(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function mapApiEvent(event) {
  return {
    id: event.event_id || `EVT-${event.id}`,
    severity: displayLabel(event.severity),
    name: displayLabel(event.event_type),
    host: event.source_machine || 'Unknown host',
    time: formatTime(event.timestamp),
    status: displayLabel(event.status),
    details: event.description || 'No description provided.',
  }
}

async function openAlertDetails(alert) {
  try {
    const apiAlert = await getAlert(alert.id)

    selectedEvent.value = {
      id: `ALERT-${apiAlert.id}`,
      severity: displayLabel(apiAlert.severity),
      name: apiAlert.title,
      host: apiAlert.source_machine,
      time: formatTime(apiAlert.created_at),
      status: displayLabel(apiAlert.status),
      details: apiAlert.description || 'No description provided.',
      alertId: apiAlert.id,
      alertStatus: apiAlert.status,
    }
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : String(error)
  }
}

async function changeAlertStatus(status) {
  const alertId = selectedEvent.value?.alertId
  if (!alertId) return

  try {
    const updatedAlert = await updateAlertStatus(alertId, status)
    selectedEvent.value.alertStatus = updatedAlert.status
    selectedEvent.value.status = displayLabel(updatedAlert.status)
    alerts.value = await getAlerts()
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : String(error)
  }
}

onMounted(async () => {
  try {
    const [apiEvents, apiStats, apiAlerts] = await Promise.all([
      getEvents(),
      getStats(),
      getAlerts(),
    ])

    if (!Array.isArray(apiEvents) || !Array.isArray(apiAlerts)) {
      throw new Error('Unexpected API response')
    }

    events.value = apiEvents.map(mapApiEvent)
    stats.value = apiStats
    alerts.value = apiAlerts
    apiConnected.value = true
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : String(error)
  }
})

const filteredEvents = computed(() => {
  const query = search.value.trim().toLowerCase()

  return events.value.filter((event) => {
    const matchesSeverity =
      severityFilter.value === 'All' || event.severity === severityFilter.value
    const matchesSearch =
      !query ||
      `${event.id} ${event.name} ${event.host} ${event.status}`.toLowerCase().includes(query)

    return matchesSeverity && matchesSearch
  })
})

const highSeverityCount = computed(() => {
  const counts = stats.value?.severity_counts

  if (!counts) {
    return events.value.filter((event) =>
      ['High', 'Critical'].includes(event.severity),
    ).length
  }

  return (counts.critical ?? 0) + (counts.high ?? 0)
})

const openEventCount = computed(() => {
  if (stats.value) return stats.value.new_alerts ?? 0

  return events.value.filter(
    (event) => !['Closed', 'Resolved'].includes(event.status),
  ).length
})

const totalEvents = computed(
  () => stats.value?.total_events ?? events.value.length,
)
</script>

<template>
  <div class="dashboard">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">S</div>
        <div>
          <strong>Sentinel</strong>
          <span>SOC DASHBOARD</span>
        </div>
      </div>

      <p class="nav-label">WORKSPACE</p>
      <nav>
        <a class="nav-link active" href="#overview"><span>◫</span> Overview</a>
        <a class="nav-link" href="#events"><span>▤</span> Events &amp; alerts</a>
        <a class="nav-link" href="#hosts"><span>◉</span> Hosts</a>
      </nav>

      <div class="sidebar-bottom">
        <span class="status-dot"></span>
        <div><strong>Lab status</strong><small>Sample dashboard data</small></div>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <span>Security Operations <span class="muted">/ Dashboard</span></span>
        <span class="demo-label"><i></i> {{ apiConnected ? 'API CONNECTED' : 'DEMO DATA' }}</span>
      </header>

      <main id="overview" class="content">
        <section class="page-heading">
          <div>
            <p class="eyebrow">MONITORING</p>
            <h1>Security overview</h1>
            <p class="subheading">A sample view of your monitored lab systems and events.</p>
          </div>
          <span class="time-range">Last 24 hours</span>
        </section>

        <section class="metrics">
  <article class="metric-card">
    <span class="metric-icon blue">◉</span>
    <p>Connected hosts</p>
    <strong>{{ hosts.length }}</strong>
    <small>Sample hosts, not live status</small>
  </article>

  <article class="metric-card">
    <span class="metric-icon red">!</span>
    <p>High + critical alerts</p>
    <strong>{{ highSeverityCount }}</strong>
    <small>{{ stats ? 'Count from SOC API' : 'Sample count' }}</small>
  </article>

  <article class="metric-card">
    <span class="metric-icon amber">⌁</span>
    <p>New alerts</p>
    <strong>{{ openEventCount }}</strong>
    <small>{{ stats ? 'Alerts with status new' : 'Sample count' }}</small>
  </article>

  <article class="metric-card">
    <span class="metric-icon green">▤</span>
    <p>Total events</p>
    <strong>{{ totalEvents }}</strong>
    <small>{{ stats ? 'All stored events' : 'Sample count' }}</small>
  </article>
</section>

<section id="events" class="panel">
  <div class="panel-heading">
    <div>
      <h2>Recent security events</h2>
      <p>Events received from the SOC backend</p>
    </div>
    <div class="filters">
      <input v-model="search" type="search" placeholder="Search events..." />
      <select v-model="severityFilter" aria-label="Filter by severity">
        <option>All</option>
        <option>Critical</option>
        <option>High</option>
        <option>Medium</option>
        <option>Low</option>
      </select>
    </div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>SEVERITY</th>
          <th>EVENT</th>
          <th>HOST</th>
          <th>TIME</th>
          <th>STATUS</th>
          <th></th>
          
        </tr>
      </thead>
      <tbody>
        <tr v-for="event in filteredEvents" :key="event.id">
          <td>
            <span class="severity" :class="event.severity.toLowerCase()">
              {{ event.severity }}
            </span>
          </td>
          <td>
            <strong class="event-name">{{ event.name }}</strong>
            <small class="event-id">{{ event.id }}</small>
          </td>
          <td>{{ event.host }}</td>
          <td>{{ event.time }}</td>
          <td><span class="event-status">{{ event.status }}</span></td>
          <td>
            <button class="details-button" @click="selectedEvent = event">
              Details
            </button>
          </td>
        </tr>
        <tr v-if="filteredEvents.length === 0">
          <td colspan="6" class="empty-state">No matching events.</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>

<section id="alerts" class="panel">
  <div class="panel-heading">
    <div>
      <h2>Recent alerts</h2>
      <p>Alerts generated by backend detection rules</p>
    </div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>SEVERITY</th>
          <th>ALERT</th>
          <th>HOST</th>
          <th>CREATED</th>
          <th>STATUS</th>
          <th>RELATED EVENT</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="alert in alerts" :key="alert.id">
          <td>
            <span class="severity" :class="String(alert.severity).toLowerCase()">
              {{ displayLabel(alert.severity) }}
            </span>
          </td>
          <td>
            <strong class="event-name">{{ alert.title }}</strong>
            <small class="event-id">{{ alert.rule_id }}</small>
          </td>
          <td>{{ alert.source_machine }}</td>
          <td>{{ formatTime(alert.created_at) }}</td>
          <td><span class="event-status">{{ displayLabel(alert.status) }}</span></td>
          <td>{{ alert.event_id || '—' }}</td>
          <td>
            <button class="details-button" @click="openAlertDetails(alert)">
              Details
            </button>
          </td>
        </tr>
        <tr v-if="alerts.length === 0">
          <td colspan="7" class="empty-state">No alerts from the API yet.</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>

        

        <section id="hosts" class="panel hosts-panel">
          <div class="panel-heading">
            <div>
              <h2>Monitored hosts</h2>
              <p>Sample inventory for the project lab</p>
            </div>
          </div>
          <div class="host-list">
            <article v-for="host in hosts" :key="host.name" class="host-card">
              <div class="host-symbol">⌘</div>
              <div class="host-info">
                <strong>{{ host.name }}</strong>
                <span>{{ host.role }} · {{ host.address }}</span>
              </div>
              <span class="host-status"><i></i>{{ host.status }}</span>
            </article>
          </div>
        </section>

        <p class="disclaimer">
  {{ apiConnected ? 'Events are loaded from SOC-Core. Host inventory is still sample data.' : 'Showing sample events because the SOC API could not be reached.' }}
  <span v-if="apiError">({{ apiError }})</span>
</p>
      </main>
    </div>

    <div v-if="selectedEvent" class="modal-backdrop" @click.self="selectedEvent = null">
      <section class="details-modal" role="dialog" aria-modal="true" aria-label="Event details">
        <button class="close-button" aria-label="Close details" @click="selectedEvent = null">×</button>
        <p class="eyebrow">EVENT DETAILS · {{ selectedEvent.id }}</p>
        <h2>{{ selectedEvent.name }}</h2>
        <p class="modal-description">{{ selectedEvent.details }}</p>
        <dl>
          <div><dt>Severity</dt><dd>{{ selectedEvent.severity }}</dd></div>
          <div><dt>Host</dt><dd>{{ selectedEvent.host }}</dd></div>
          <div><dt>Time</dt><dd>{{ selectedEvent.time }}</dd></div>
          <div>
          <dt>Status</dt>
          <dd v-if="!selectedEvent.alertId">{{ selectedEvent.status }}</dd>
          <dd v-else>
            <select
              :value="selectedEvent.alertStatus"
              aria-label="Update alert status"
              @change="changeAlertStatus($event.target.value)"
            >
              <option value="new">New</option>
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </dd>
        </div>
        </dl>
      </section>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #0b1020;
  color: #e6eaf2;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
}

.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  display: flex;
  flex-direction: column;
  width: 238px;
  padding: 24px 16px;
  background: #101729;
  border-right: 1px solid #222c40;
}

.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 32px; }
.brand-mark { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; background: #173c39; color: #55e0b2; font-weight: 800; font-size: 20px; }
.brand strong, .brand span, .sidebar-bottom strong, .sidebar-bottom small { display: block; }
.brand strong { font-size: 16px; letter-spacing: .2px; }
.brand span { margin-top: 3px; color: #8290a6; font-size: 9px; letter-spacing: 1.4px; }
.nav-label, .eyebrow { color: #8190a8; font-size: 10px; font-weight: 700; letter-spacing: 1.4px; }
.nav-label { padding: 0 10px; margin: 0 0 10px; }
.sidebar nav { display: grid; gap: 6px; }
.nav-link { display: flex; align-items: center; gap: 12px; padding: 11px 12px; border-radius: 8px; color: #9ba8bc; text-decoration: none; }
.nav-link span { width: 18px; color: #8795aa; font-size: 16px; text-align: center; }
.nav-link:hover, .nav-link.active { background: #1c2940; color: #e8eef8; }
.nav-link.active span { color: #55e0b2; }
.sidebar-bottom { display: flex; align-items: center; gap: 10px; margin-top: auto; padding: 14px 10px; border-top: 1px solid #222c40; }
.sidebar-bottom strong { font-size: 12px; }
.sidebar-bottom small { margin-top: 3px; color: #8290a6; font-size: 10px; }
.status-dot, .demo-label i, .host-status i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #4bd6a5; }
.main-area { min-height: 100vh; margin-left: 238px; }
.topbar { display: flex; align-items: center; justify-content: space-between; height: 62px; padding: 0 34px; border-bottom: 1px solid #202a3d; color: #d6ddeb; font-size: 12px; }
.muted { color: #7e8ba0; }
.demo-label { display: inline-flex; align-items: center; gap: 8px; padding: 6px 9px; border: 1px solid #25463f; border-radius: 20px; color: #72ddb5; font-size: 9px; font-weight: 700; letter-spacing: 1px; }
.demo-label i { width: 6px; height: 6px; }
.content { max-width: 1280px; margin: 0 auto; padding: 34px; }
.page-heading { display: flex; align-items: end; justify-content: space-between; margin-bottom: 24px; }
.eyebrow { margin: 0 0 9px; }
h1 { margin: 0; font-size: 27px; letter-spacing: -.6px; }
.subheading, .panel-heading p { margin: 7px 0 0; color: #8491a6; font-size: 12px; }
.time-range { padding: 9px 12px; border: 1px solid #2a3549; border-radius: 7px; color: #b8c2d2; font-size: 11px; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.metric-card, .panel { border: 1px solid #222c40; border-radius: 11px; background: #111a2b; }
.metric-card { position: relative; min-height: 128px; padding: 17px; }
.metric-icon { display: grid; place-items: center; width: 29px; height: 29px; border-radius: 8px; font-weight: 700; }
.metric-icon.blue { background: #152e48; color: #6bbcff; }
.metric-icon.red { background: #3d202b; color: #ff7894; }
.metric-icon.amber { background: #392f1c; color: #f4c56b; }
.metric-icon.green { background: #17352f; color: #58d9ad; }
.metric-card p { margin: 14px 0 3px; color: #9aa7ba; font-size: 11px; }
.metric-card strong { font-size: 23px; }
.metric-card small { margin-left: 9px; color: #75839a; font-size: 9px; }
.panel { margin-bottom: 18px; overflow: hidden; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 20px; border-bottom: 1px solid #222c40; }
.panel-heading h2 { margin: 0; font-size: 14px; }
.filters { display: flex; gap: 8px; }
.filters input, .filters select { height: 34px; padding: 0 10px; border: 1px solid #2a3549; border-radius: 6px; outline: none; background: #0d1525; color: #dce4ef; font-size: 11px; }
.filters input { width: 180px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; white-space: nowrap; }
th { padding: 12px 16px; color: #718097; font-size: 9px; font-weight: 700; letter-spacing: 1px; }
td { padding: 13px 16px; border-top: 1px solid #202a3d; color: #aab5c6; font-size: 11px; }
.event-name, .event-id { display: block; }
.event-name { color: #e0e6ef; font-size: 11px; font-weight: 600; }
.event-id { margin-top: 4px; color: #718097; font-size: 9px; }
.severity { display: inline-block; min-width: 55px; padding: 5px 7px; border-radius: 5px; text-align: center; font-size: 9px; font-weight: 700; }
.severity.high { background: #40202d; color: #ff829a; }
.severity.medium { background: #3a301e; color: #f2c46e; }
.severity.low { background: #19342f; color: #69dcb4; }
.event-status { color: #aab5c6; }
.details-button { padding: 6px 9px; border: 1px solid #2d3a50; border-radius: 5px; background: transparent; color: #b8c5d8; font-size: 10px; cursor: pointer; }
.details-button:hover { border-color: #55cfa8; color: #75e1ba; }
.empty-state { padding: 28px; color: #8794a8; text-align: center; }
.host-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 16px; }
.host-card { display: flex; align-items: center; gap: 11px; padding: 13px; border: 1px solid #273247; border-radius: 8px; background: #0d1525; }
.host-symbol { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 8px; background: #1a2940; color: #83b9ec; }
.host-info { min-width: 0; flex: 1; }
.host-info strong, .host-info span { display: block; }
.host-info strong { font-size: 10px; }
.host-info span { margin-top: 4px; color: #7e8ba0; font-size: 9px; }
.host-status { display: flex; align-items: center; gap: 5px; color: #6bd8af; font-size: 9px; }
.host-status i { width: 6px; height: 6px; }
.disclaimer { margin: 4px 0 0; color: #748198; font-size: 10px; }
.modal-backdrop { position: fixed; inset: 0; z-index: 5; display: grid; place-items: center; padding: 20px; background: #050914bb; }
.details-modal { position: relative; width: min(100%, 480px); padding: 26px; border: 1px solid #2b3850; border-radius: 12px; background: #121c2e; box-shadow: 0 18px 60px #0008; }
.details-modal h2 { margin: 0; font-size: 18px; }
.modal-description { color: #a6b2c4; line-height: 1.6; }
.details-modal dl { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 22px; }
.details-modal dt { color: #7e8ba0; font-size: 10px; }
.details-modal dd { margin: 5px 0 0; color: #e3e9f2; font-size: 12px; }
.close-button { position: absolute; top: 14px; right: 16px; border: 0; background: none; color: #9ba8bc; font-size: 24px; cursor: pointer; }
@media (max-width: 900px) {
  .metrics { grid-template-columns: repeat(2, 1fr); }
  .host-list { grid-template-columns: 1fr; }
}
@media (max-width: 650px) {
  .sidebar { position: static; width: 100%; padding: 14px; }
  .brand { padding-bottom: 14px; }
  .sidebar nav { grid-template-columns: repeat(3, 1fr); }
  .nav-label, .sidebar-bottom { display: none; }
  .nav-link { justify-content: center; padding: 9px 4px; font-size: 10px; }
  .main-area { margin-left: 0; }
  .topbar { padding: 0 16px; }
  .content { padding: 22px 14px; }
  .metrics { gap: 9px; }
  .metric-card { padding: 13px; }
  .metric-card small { display: block; margin: 5px 0 0; }
  .page-heading { align-items: start; flex-direction: column; gap: 12px; }
  .panel-heading { align-items: start; flex-direction: column; }
  .filters { width: 100%; }
  .filters input { flex: 1; min-width: 0; }
}
</style>