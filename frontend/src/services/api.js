async function request(path, options = {}) {
    const response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`)
    }
  
    return response.json()
  }
  
  export const getStats = () => request('/stats')
  export const getEvents = () => request('/events')
  export const getAlerts = () => request('/alerts')
  export const getAlert = (id) => request(`/alerts/${id}`)
  
  export const updateAlertStatus = (id, status) =>
    request(`/alerts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    })