<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

// 模块级缓存，再次打开秒开
const builtinTools = ref([])           // 始终立即可见
const mcpTools = ref([])
const mcpStatus = ref('idle')          // idle | loading | ready | error
const mcpError = ref('')
const keyword = ref('')

let pollTimer = null

async function loadBuiltin() {
    const d = await api.toolsBuiltin()
    builtinTools.value = d.success ? d.tools : []
}

async function fetchMcpOnce(force = false) {
    const d = await api.toolsMcp(force)
    if (!d.success) {
        mcpStatus.value = 'error'
        mcpError.value = d.detail || '请求失败'
        return
    }
    mcpStatus.value = d.status
    mcpError.value = d.error || ''
    if (d.status === 'ready') mcpTools.value = d.tools || []
}

function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
        if (mcpStatus.value !== 'loading') {
            stopPolling()
            return
        }
        await fetchMcpOnce(false)
        if (mcpStatus.value !== 'loading') stopPolling()
    }, 1000)
}

function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function refreshAll() {
    await loadBuiltin()
    mcpStatus.value = 'loading'
    mcpTools.value = []
    await fetchMcpOnce(true)        // force
    if (mcpStatus.value === 'loading') startPolling()
}

async function open() {
    // 内置：每次打开都拉，反正是毫秒级
    await loadBuiltin()
    // MCP：拿当前状态，若还在 loading 就开轮询
    await fetchMcpOnce(false)
    if (mcpStatus.value === 'loading') startPolling()
}

// 过滤 / 分组
function applyFilter(list) {
    const kw = keyword.value.trim().toLowerCase()
    if (!kw) return list
    return list.filter(t =>
        (t.name || '').toLowerCase().includes(kw) ||
        (t.full_name || '').toLowerCase().includes(kw) ||
        (t.description || '').toLowerCase().includes(kw)
    )
}

const filteredBuiltin = computed(() => applyFilter(builtinTools.value))
const filteredMcpByServer = computed(() => {
    const groups = {}
    applyFilter(mcpTools.value).forEach(t => {
        const k = t.server || '(unknown)'
        ;(groups[k] ||= []).push(t)
    })
    return groups
})

const totalCount = computed(() => builtinTools.value.length + mcpTools.value.length)

function shortDesc(desc) {
    const s = (desc || '').replace(/\s+/g, ' ').trim()
    if (!s) return ''
    return s.length > 80 ? s.slice(0, 80) + '…' : s
}
function isLong(desc) {
    return (desc || '').replace(/\s+/g, ' ').trim().length > 80
}

watch(() => props.modelValue, (v) => {
    if (v) open()
    else stopPolling()
})

onBeforeUnmount(stopPolling)
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="工具列表（只读）"
    >
        <div class="tip-text" style="margin-bottom:8px;">
            这里展示 Agent 当前实际可调用的所有工具。<br>
            · <b>内置工具</b>来自 <code>script/tools.py</code>，同步加载，秒开<br>
            · <b>MCP 工具</b>异步加载，可能因为服务连不上而较慢/失败，但不会阻塞页面
        </div>

        <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap;">
            <el-input v-model="keyword" placeholder="按名称或描述搜索…" clearable size="small" style="max-width:280px;" />
            <el-button size="small" @click="refreshAll">刷新</el-button>
            <span class="tip-text">合计 {{ totalCount }} 个</span>
        </div>

        <!-- 内置工具：始终展示 -->
        <div style="margin-bottom:14px;">
            <div style="font-weight:500;margin-bottom:6px;">🛠 内置工具
                <span class="tip-text">({{ filteredBuiltin.length }})</span>
            </div>
            <div v-if="!filteredBuiltin.length" class="tip-text">无</div>
            <div v-for="t in filteredBuiltin" :key="'b-'+t.name" class="tool-item">
                <div style="font-weight:500;color:#2d3436;"><code>{{ t.full_name || t.name }}</code></div>
                <div style="color:#666;font-size:13px;margin-top:2px;">{{ shortDesc(t.description) || '(无描述)' }}</div>
                <details v-if="isLong(t.description)" style="margin-top:4px;">
                    <summary class="tip-text" style="cursor:pointer;">展开完整描述</summary>
                    <pre style="white-space:pre-wrap;background:#f7f7f7;border-radius:6px;padding:8px;font-size:12px;color:#333;margin-top:4px;">{{ t.description }}</pre>
                </details>
            </div>
        </div>

        <!-- MCP 工具：按状态分别渲染 -->
        <div>
            <div style="font-weight:500;margin-bottom:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                🔌 MCP 工具
                <el-tag v-if="mcpStatus === 'loading'" type="warning" size="small">加载中…</el-tag>
                <el-tag v-else-if="mcpStatus === 'error'" type="danger" size="small">加载失败</el-tag>
                <el-tag v-else-if="mcpStatus === 'ready'" type="success" size="small">已就绪 ({{ mcpTools.length }})</el-tag>
            </div>

            <el-skeleton v-if="mcpStatus === 'loading'" :rows="3" animated />

            <div v-else-if="mcpStatus === 'error'" class="tip-text" style="color:#d63031;">
                {{ mcpError || '未知错误，请检查 MCP 配置或重试' }}
            </div>

            <template v-else-if="mcpStatus === 'ready'">
                <div v-if="!Object.keys(filteredMcpByServer).length" class="tip-text">无</div>
                <div v-for="(list, server) in filteredMcpByServer" :key="server" style="margin-bottom:10px;">
                    <div style="font-weight:500;margin:6px 0;">· <code>{{ server }}</code>
                        <span class="tip-text">({{ list.length }})</span>
                    </div>
                    <div v-for="t in list" :key="'m-'+t.full_name" class="tool-item">
                        <div style="font-weight:500;color:#2d3436;"><code>{{ t.full_name || t.name }}</code></div>
                        <div style="color:#666;font-size:13px;margin-top:2px;">{{ shortDesc(t.description) || '(无描述)' }}</div>
                        <details v-if="isLong(t.description)" style="margin-top:4px;">
                            <summary class="tip-text" style="cursor:pointer;">展开完整描述</summary>
                            <pre style="white-space:pre-wrap;background:#f7f7f7;border-radius:6px;padding:8px;font-size:12px;color:#333;margin-top:4px;">{{ t.description }}</pre>
                        </details>
                    </div>
                </div>
            </template>
        </div>
    </AppDialog>
</template>

<style>
.tool-item { border:1px solid #eee; border-radius:8px; padding:8px 10px; margin-bottom:6px; background:#fafafa; }
</style>