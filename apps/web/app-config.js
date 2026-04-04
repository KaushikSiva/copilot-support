(() => {
  const origin = window.location.origin || ''
  const isLocalApiOrigin = origin.includes('127.0.0.1:8787') || origin.includes('localhost:8787')
  const storedBaseUrl = window.localStorage.getItem('copilotSupportApiBaseUrl') || ''
  const defaultRemoteApiBaseUrl = 'https://unmythological-addyson-follicular.ngrok-free.dev'
  const hasLoopbackOverride = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/i.test(storedBaseUrl)
  const effectiveStoredBaseUrl = !isLocalApiOrigin && hasLoopbackOverride ? '' : storedBaseUrl

  window.APP_CONFIG = window.APP_CONFIG || {
    apiBaseUrl: isLocalApiOrigin ? '' : effectiveStoredBaseUrl || defaultRemoteApiBaseUrl
  }
})()
