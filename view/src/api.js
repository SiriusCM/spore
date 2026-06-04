// 统一 API 调用封装。开发期通过 vite proxy /api 转发到 8765；生产期同源。
const BASE = ''

async function jsonFetch(url, opts = {}) {
    const r = await fetch(BASE + url, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    })
    return r.json()
}

export const api = {
    // 聊天
    chat: (message, signal) => jsonFetch('/api/chat', {
        method: 'POST', body: JSON.stringify({ message }), signal,
    }),
    chatHistory: () => jsonFetch('/api/chat/history'),

    // 进化
    evolve: (apply) => jsonFetch('/api/evolve', {
        method: 'POST', body: JSON.stringify({ apply }),
    }),
    evolveReports: () => jsonFetch('/api/evolve/reports'),
    evolveLatestReport: () => jsonFetch('/api/evolve/reports/latest'),
    evolveReport: (id) => jsonFetch(`/api/evolve/reports/${id}`),

    // 设置
    getSettings: () => jsonFetch('/api/settings'),
    saveSettings: (data) => jsonFetch('/api/settings', {
        method: 'POST', body: JSON.stringify(data),
    }),

    // MCP
    mcpList:   () => jsonFetch('/api/mcp/servers'),
    mcpAdd:    (data) => jsonFetch('/api/mcp/servers', { method: 'POST', body: JSON.stringify(data) }),
    mcpUpdate: (id, data) => jsonFetch(`/api/mcp/servers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    mcpDelete: (id) => jsonFetch(`/api/mcp/servers/${id}`, { method: 'DELETE' }),
    mcpToggle: (id, enabled) => jsonFetch(`/api/mcp/servers/${id}/toggle`, {
        method: 'POST', body: JSON.stringify({ enabled }),
    }),
    mcpReload: () => jsonFetch('/api/mcp/reload', { method: 'POST' }),
    mcpTools:  () => jsonFetch('/api/mcp/tools'),

    // Skill
    skillList:   () => jsonFetch('/api/skills'),
    skillAdd:    (data) => jsonFetch('/api/skills', { method: 'POST', body: JSON.stringify(data) }),
    skillUpdate: (id, data) => jsonFetch(`/api/skills/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    skillDelete: (id) => jsonFetch(`/api/skills/${id}`, { method: 'DELETE' }),
    skillToggle: (id, enabled) => jsonFetch(`/api/skills/${id}/toggle`, {
        method: 'POST', body: JSON.stringify({ enabled }),
    }),
    skillExportUrl: (id) => `${BASE}/api/skills/${id}/export`,
    skillImport: (file, overwrite) => {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('overwrite', overwrite ? '1' : '0')
        return fetch(`${BASE}/api/skills/import`, { method: 'POST', body: fd }).then(r => r.json())
    },

    // Agent
    agentList:   () => jsonFetch('/api/agents'),
    agentAdd:    (data) => jsonFetch('/api/agents', { method: 'POST', body: JSON.stringify(data) }),
    agentUpdate: (id, data) => jsonFetch(`/api/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    agentDelete: (id) => jsonFetch(`/api/agents/${id}`, { method: 'DELETE' }),
    agentToggle: (id, enabled) => jsonFetch(`/api/agents/${id}/toggle`, {
        method: 'POST', body: JSON.stringify({ enabled }),
    }),

    tools: () => jsonFetch('/api/tools'),
    toolsBuiltin: () => jsonFetch('/api/tools/builtin'),
    toolsMcp: (force = false) => jsonFetch('/api/tools/mcp' + (force ? '?force=1' : '')),
}