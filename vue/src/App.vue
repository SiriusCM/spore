<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
    Setting, Connection, Aim, User, Document, Tools, Promotion, VideoPause,
    ArrowDown, ArrowUp, RefreshLeft, Check, Camera, Back,
} from '@element-plus/icons-vue'
import { api } from './api.js'
import SettingsDialog from './components/SettingsDialog.vue'
import McpDialog from './components/McpDialog.vue'
import SkillDialog from './components/SkillDialog.vue'
import AgentDialog from './components/AgentDialog.vue'
import PromptDialog from './components/PromptDialog.vue'
import ToolsDialog from './components/ToolsDialog.vue'

const messages = ref([
    { type: 'assistant', content: '你好！我是 Starfish Agent，随时为你效劳。', time: now() },
])
const userInput = ref('')
const isSending = ref(false)
let abortController = null
const chatBox = ref(null)

// 控制面板
const panelExpanded = ref(false)
const snapshots = ref([])
const selectedSnap = ref('')

// 弹窗显示
const showSettings = ref(false)
const showMcp = ref(false)
const showSkill = ref(false)
const showAgent = ref(false)
const showPrompt = ref(false)
const showTools = ref(false)

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
    if (panelExpanded.value) loadSnapshots()
}

async function loadSnapshots() {
    try {
        const d = await api.snapshots()
        snapshots.value = d.success ? d.snapshots : []
    } catch { snapshots.value = [] }
}

async function doEvolve(apply) {
    ElMessage.info(apply ? '执行进化中...' : '预览进化中...')
    try {
        const d = await api.evolve(apply)
        if (d.success) {
            ElMessage.success(apply ? '进化已执行' : '预览完成')
            addMsg('system', apply ? '进化执行完成' : '进化预览完成')
        } else ElMessage.error('操作失败')
    } catch (e) { ElMessage.error('请求失败: ' + e.message) }
}

async function takeSnapshot() {
    try {
        const d = await api.takeSnapshot()
        if (d.success) {
            ElMessage.success('快照已创建')
            addMsg('system', '快照: ' + d.snapshot)
            loadSnapshots()
        } else ElMessage.error('创建失败')
    } catch { ElMessage.error('请求失败') }
}

async function doRollback() {
    if (!selectedSnap.value) { ElMessage.warning('请先选择快照'); return }
    try {
        await ElMessageBox.confirm(`确定回滚到 ${selectedSnap.value}？`, '回滚确认', { type: 'warning' })
    } catch { return }
    try {
        const d = await api.rollback(selectedSnap.value)
        if (d.success) {
            ElMessage.success('回滚成功')
            addMsg('system', d.result)
            selectedSnap.value = ''
            loadSnapshots()
        } else ElMessage.error('回滚失败')
    } catch { ElMessage.error('请求失败') }
}

onMounted(scrollBottom)
</script>

<template>
    <div class="app-root">
        <header class="header glass">
            <h1><span>Starfish</span> Agent</h1>
            <div class="header-actions">
                <el-button text circle :icon="Setting"    title="设置"        @click="showSettings = true" />
                <el-button text circle :icon="Connection" title="MCP 服务端"  @click="showMcp = true" />
                <el-button text circle :icon="Aim"        title="Skill 配置" @click="showSkill = true" />
                <el-button text circle :icon="User"       title="Agent 配置" @click="showAgent = true" />
                <el-button text circle :icon="Document"   title="Prompt 常量" @click="showPrompt = true" />
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
                <div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-bottom:16px;">
                    <el-button type="success" :icon="RefreshLeft" @click="doEvolve(false)">预览</el-button>
                    <el-button type="primary" :icon="Check"       @click="doEvolve(true)">执行</el-button>
                    <el-button type="danger"  :icon="Camera"      @click="takeSnapshot">快照</el-button>
                    <el-button type="warning" :icon="Back"        @click="doRollback">回滚</el-button>
                </div>
                <div class="snapshot-section">
                    <div class="snapshot-label">选择快照后点击回滚</div>
                    <div class="snapshot-list">
                        <span v-if="!snapshots.length" style="color:#b2bec3">暂无快照</span>
                        <div
                            v-for="s in snapshots"
                            :key="s"
                            class="snapshot-item"
                            :class="{ selected: selectedSnap === s }"
                            @click="selectedSnap = s"
                        >{{ s }}</div>
                    </div>
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
        <PromptDialog   v-model="showPrompt" />
        <ToolsDialog    v-model="showTools" />
    </div>
</template>