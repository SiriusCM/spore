const API = 'http://localhost:8765';
let selected = '';
let abortController = null;
let isSending = false;

document.getElementById('welcomeTime').textContent = new Date().toLocaleTimeString();

function togglePanel() {
    const panel = document.getElementById('controlPanel');
    const icon = document.getElementById('toggleIcon');
    panel.classList.toggle('expanded');
    icon.innerHTML = panel.classList.contains('expanded') ? '&#9650;' : '&#9660;';
    if (panel.classList.contains('expanded')) loadSnapshots();
}

function toast(msg, err = false) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show ' + (err ? 'error' : 'success');
    setTimeout(() => t.classList.remove('show'), 3000);
}

async function loadSnapshots() {
    try {
        const d = await (await fetch(`${API}/api/snapshots`)).json();
        document.getElementById('snapshotList').innerHTML =
            d.success && d.snapshots.length
                ? d.snapshots.map(s => `<div class="snapshot-item" onclick="selectSnap('${s}',this)">${s}</div>`).join('')
                : '<span style="color:#b2bec3">暂无快照</span>';
    } catch { document.getElementById('snapshotList').innerHTML = '<span style="color:#d63031">加载失败</span>'; }
}

function selectSnap(tag, el) {
    document.querySelectorAll('.snapshot-item').forEach(i => i.classList.remove('selected'));
    el.classList.add('selected');
    selected = tag;
}

async function doEvolve(apply) {
    const btn = document.getElementById(apply ? 'btn-apply' : 'btn-evolve');
    btn.disabled = true;
    toast(apply ? '执行进化中...' : '预览进化中...');
    try {
        const d = await (await fetch(`${API}/api/evolve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({apply})
        })).json();
        toast(d.success ? (apply ? '进化已执行' : '预览完成') : '操作失败', !d.success);
        addMsg('system', apply ? '进化执行完成' : '进化预览完成');
    } catch (e) { toast('请求失败: ' + e.message, true); }
    finally { btn.disabled = false; }
}

async function takeSnapshot() {
    toast('创建快照中...');
    try {
        const d = await (await fetch(`${API}/api/snapshot/take`, {method: 'POST'})).json();
        if (d.success) { toast('快照已创建'); addMsg('system', '快照: ' + d.snapshot); loadSnapshots(); }
        else toast('创建失败', true);
    } catch (e) { toast('请求失败', true); }
}

async function doRollback() {
    if (!selected) { toast('请先选择快照', true); return; }
    if (!confirm(`确定回滚到 ${selected}？`)) return;
    toast('回滚中...');
    try {
        const d = await (await fetch(`${API}/api/rollback`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tag: selected})
        })).json();
        if (d.success) { toast('回滚成功'); addMsg('system', d.result); selected = ''; loadSnapshots(); }
        else toast('回滚失败', true);
    } catch (e) { toast('请求失败', true); }
}

function addMsg(type, content) {
    const c = document.getElementById('chatContainer');
    const m = document.createElement('div');
    m.className = 'message ' + (type === 'user' ? 'user' : type === 'error' ? 'error' : type === 'system' ? 'system' : 'assistant');
    m.innerHTML = content + `<span class="time">${new Date().toLocaleTimeString()}</span>`;
    c.appendChild(m);
    c.scrollTop = c.scrollHeight;
}

async function send() {
    const input = document.getElementById('userInput');
    const btn = document.getElementById('sendBtn');

    // 如果正在发送，点击则停止
    if (isSending) {
        if (abortController) {
            abortController.abort();
        }
        return;
    }

    const msg = input.value.trim();
    if (!msg) return;

    addMsg('user', msg);
    input.value = '';
    isSending = true;
    btn.innerHTML = '&#9632;'; // 停止方块图标
    btn.classList.add('stop');

    const loading = document.createElement('div');
    loading.className = 'loading';
    loading.id = 'loadingIndicator';
    loading.innerHTML = '思考中 <div class="loading-dots"><span></span><span></span><span></span></div>';
    document.getElementById('chatContainer').appendChild(loading);
    document.getElementById('chatContainer').scrollTop = 1e9;

    abortController = new AbortController();

    try {
        const d = await (await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg}),
            signal: abortController.signal
        })).json();
        loading.remove();
        if (d.success) addMsg('assistant', d.response);
        else addMsg('error', d.detail || '请求失败');
    } catch (e) {
        loading.remove();
        if (e.name === 'AbortError') {
            addMsg('system', '已终止当前会话');
        } else {
            addMsg('error', '连接失败，请确保服务已启动');
        }
    } finally {
        isSending = false;
        abortController = null;
        btn.innerHTML = '&#10148;'; // 发送箭头图标
        btn.classList.remove('stop');
        input.focus();
    }
}

function handleKey(e) { if (e.key === 'Enter' && !isSending) send(); }

// 设置弹窗
function openSettings() {
    // 加载当前设置
    fetch(`${API}/api/settings`)
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                document.getElementById('settingModel').value = d.settings.model || '';
                document.getElementById('settingBaseUrl').value = d.settings.base_url || '';
                document.getElementById('settingApiKey').value = d.settings.api_key || '';
            }
        })
        .catch(() => {});
    document.getElementById('settingsModal').classList.add('show');
}

function closeSettings() {
    document.getElementById('settingsModal').classList.remove('show');
}

function closeSettingsOnOverlay(e) {
    if (e.target === document.getElementById('settingsModal')) {
        closeSettings();
    }
}

async function saveSettings() {
    const model = document.getElementById('settingModel').value.trim();
    const baseUrl = document.getElementById('settingBaseUrl').value.trim();
    const apiKey = document.getElementById('settingApiKey').value.trim();

    try {
        const d = await (await fetch(`${API}/api/settings`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model, base_url: baseUrl, api_key: apiKey})
        })).json();

        if (d.success) {
            toast('设置已保存');
            closeSettings();
        } else {
            toast(d.detail || '保存失败', true);
        }
    } catch (e) {
        toast('保存失败: ' + e.message, true);
    }
}