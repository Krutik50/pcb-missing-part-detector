// Offline frontend client logic (zero external dependencies)
document.addEventListener('DOMContentLoaded', async () => {
    const statusIndicator = document.getElementById('connection-status');
    const statusBadge = document.getElementById('server-status-badge');

    try {
        const response = await fetch('/api/health');
        if (response.ok) {
            const data = await response.json();
            statusIndicator.classList.remove('offline');
            statusIndicator.classList.add('online');
            statusIndicator.title = `Connected to ${data.service} v${data.version}`;
            statusBadge.className = 'badge badge-success';
            statusBadge.textContent = 'Server Online';
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (err) {
        statusIndicator.classList.remove('online');
        statusIndicator.classList.add('offline');
        statusIndicator.title = 'Offline or Server Unavailable';
        statusBadge.className = 'badge badge-danger';
        statusBadge.textContent = 'Server Disconnected';
        console.warn('Backend health check error:', err);
    }
});
