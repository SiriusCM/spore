<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
    Setting, Connection, Aim, User, Tools, Promotion, VideoPause,
    ArrowDown, ArrowUp, RefreshLeft, Check,
} from '@element-plus/icons-vue'
import { api } from './api.js'
import SettingsDialog from './components/SettingsDialog.vue'
import McpDialog from './components/McpDialog.vue'
import SkillDialog from './components/SkillDialog.vue'
import AgentDialog from './components/AgentDialog.vue'
import ToolsDialog from './components/ToolsDialog.vue'

const messages = ref([
    { type: 'assistant', content: '你好！我是 Spore Agent，随时为你效劳。', time: now() },
])
const userInput = ref('')
const isSending = ref(false)
let abortController = null
const chatBox = ref(null)

// 控制面板
const panelExpanded = ref(false)
const latestReportState = ref(null) // preview | applied | failed

// 弹窗显示
const showSettings = ref(false)
const showMcp = ref(false)
const showSkill = ref(false)
const showAgent = ref(false)
const showTools = ref(false)
const showReportDialog = ref(false)
const currentReportContent = ref('')

function now() { return new Date().toLocaleTimeString() }
function scrollBottom() {
    nextTick(() => { if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight })
}

function addMsg(type, content) {
    messages.value.push({ type, content, time: now() })
    scrollBottom()
}

async function send() {
    if (isSending.value) {
        if (abortController) abortController.abort()
        return
    }
    const msg = userInput.value.trim()
    if (!msg) return
    addMsg('user', msg)
    userInput.value = ''
    isSending.value = true
    abortController = new AbortController()
    try {
        const d = await api.chat(msg, abortController.signal)
        if (d.success) addMsg('assistant', d.response)
        else addMsg('error', d.detail || '请求失败')
    } catch (e) {
        if (e.name === 'AbortError') addMsg('system', '已终止当前会话')
        else addMsg('error', '连接失败，请确保服务已启动')
    } finally {
        isSending.value = false
        abortController = null
    }
}

function togglePanel() {
    panelExpanded.value = !panelExpanded.value
}

async function loadLatestReportState() {
    try {
        const d = await api.evolveLatestReport()
        // 只有当有 preview 状态的报告时才解锁，其他情况都需要重新预览
        if (d.success && d.report && d.report.state === 'preview') {
            latestReportState.value = 'preview'
        } else {
            latestReportState.value = null // 需要重新预览
        }
    } catch {
        latestReportState.value = null
    }
}

async function showReport() {
    if (latestReportState.value !== 'preview') return
    try {
        const d = await api.evolveLatestReport()
        if (d.success && d.report) {
            currentReportContent.value = d.report.report_content || '(无内容)'
            showReportDialog.value = true
        }
    } catch { /* ignore */ }
}

async function doEvolve(apply) {
    ElMessage.info(apply ? '应用进化中...' : '进化预览中...')
    try {
        const d = await api.evolve(apply)
        if (d.success) {
            // 插入聊天记录
            addMsg('system', d.report || '(无提案)')

            // 更新最新报告状态
            latestReportState.value = d.state

            if (apply) {
                if (d.state === 'applied') {
                    ElMessage.success('进化应用成功')
                } else {
                    ElMessage.error('进化应用失败，已自动回滚')
                }
            } else {
                ElMessage.success('进化预览完成')
            }
        } else ElMessage.error('操作失败')
    } catch (e) { ElMessage.error('请求失败: ' + e.message) }
}

async function loadHistory() {
    try {
        const d = await api.chatHistory()
        if (d.success && d.history.length > 0) {
            messages.value = []
            d.history.forEach(h => {
                if (h.msgType === 'system') {
                    messages.value.push({
                        type: 'system',
                        content: h.assistant,
                        time: new Date(h.time).toLocaleTimeString(),
                    })
                } else {
                    messages.value.push({
                        type: 'user',
                        content: h.user,
                        time: new Date(h.time).toLocaleTimeString(),
                    })
                    messages.value.push({
                        type: h.isError ? 'error' : 'assistant',
                        content: h.assistant,
                        time: new Date(h.time).toLocaleTimeString(),
                    })
                }
            })
            scrollBottom()
        }
    } catch { /* ignore */ }
}

onMounted(async () => {
    scrollBottom()
    await loadHistory()
    await loadLatestReportState()
})
</script>

<template>
    <div class="app-root">
        <header class="header glass">
            <h1><span>Spore</span> Agent</h1>
            <div class="header-actions">
                <el-button text circle :icon="Setting"    title="设置"        @click="showSettings = true" />
                <el-button text circle :icon="Connection" title="MCP 服务端"  @click="showMcp = true" />
                <el-button text circle :icon="Aim"        title="Skill 配置" @click="showSkill = true" />
                <el-button text circle :icon="User"       title="Agent 配置" @click="showAgent = true" />
                <el-button text circle :icon="Tools"      title="工具列表"   @click="showTools = true" />
                <span class="header-info"><span class="status-dot"></span>在线</span>
            </div>
        </header>

        <div class="control-toggle">
            <el-button class="glass" round size="small" @click="togglePanel">
                <el-icon><component :is="panelExpanded ? ArrowUp : ArrowDown" /></el-icon>
                &nbsp;控制面板
            </el-button>
        </div>

        <div class="control-panel glass" :class="{ expanded: panelExpanded }">
            <div class="control-inner">
                <div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;">
                    <el-button type="success" :icon="RefreshLeft" @click="doEvolve(false)">进化预览</el-button>
                    <el-button
                        type="info"
                        @click="showReport"
                        :disabled="latestReportState !== 'preview'"
                        title="查看预览报告"
                    >
                        查看报告
                    </el-button>
                    <el-button
                        type="primary"
                        :icon="Check"
                        @click="doEvolve(true)"
                        :disabled="latestReportState !== 'preview'"
                        :title="latestReportState === 'preview' ? '应用进化' : '请先执行进化预览'"
                    >
                        应用进化
                    </el-button>
                </div>
                <div v-if="latestReportState" style="text-align:center;margin-top:8px;font-size:12px;color:#636e72;">
                    <span v-if="latestReportState === 'preview'" style="color:#fdcb6e;">⚠ 有待应用的预览</span>
                    <span v-else-if="latestReportState === 'applied'" style="color:#00b894;">✓ 已应用</span>
                    <span v-else-if="latestReportState === 'failed'" style="color:#d63031;">✗ 已失败回滚</span>
                </div>
            </div>
        </div>

        <div class="chat-container" ref="chatBox">
            <div
                v-for="(m, i) in messages"
                :key="i"
                class="message"
                :class="m.type"
            >
                {{ m.content }}
                <span class="time">{{ m.time }}</span>
            </div>
            <div v-if="isSending" class="message assistant" style="opacity:0.7;">
                <el-icon class="is-loading"><Promotion /></el-icon>&nbsp;思考中...
            </div>
        </div>

        <div class="input-area">
            <div class="input-wrapper glass">
                <el-input
                    v-model="userInput"
                    placeholder="输入消息..."
                    @keydown.enter="!isSending && send()"
                    size="large"
                />
                <el-button
                    :type="isSending ? 'danger' : 'success'"
                    circle
                    size="large"
                    :icon="isSending ? VideoPause : Promotion"
                    @click="send"
                />
            </div>
        </div>

        <!-- 弹窗 -->
        <SettingsDialog v-model="showSettings" />
        <McpDialog      v-model="showMcp" />
        <SkillDialog    v-model="showSkill" />
        <AgentDialog    v-model="showAgent" />
        <ToolsDialog    v-model="showTools" />

        <!-- 进化报告弹窗 -->
        <el-dialog v-model="showReportDialog" title="进化报告" width="600px">
            <div style="white-space: pre-wrap; font-size: 13px; line-height: 1.6; max-height: 60vh; overflow-y: auto;" v-html="currentReportContent.replace(/\n/g, '<br>')"></div>
        </el-dialog>
    </div>
</template>