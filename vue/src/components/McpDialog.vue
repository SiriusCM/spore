<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

const servers = ref([])
const tools = ref([])
const showForm = ref(false)
const form = ref(emptyForm())

function emptyForm() {
    return {
        id: null, name: '', transport: 'http',
        url: 'http://localhost:8801/mcp',
        command: '', args: '[]', env: '{}',
        description: '', enabled: true,
    }
}

async function loadList() {
    try {
        const d = await api.mcpList()
        servers.value = d.success ? d.servers : []
    } catch { servers.value = [] }
}

function addNew() {
    form.value = emptyForm()
    showForm.value = true
}

function edit(s) {
    form.value = {
        id: s.id, name: s.name || '',
        transport: s.transport || 'http',
        url: s.url || '', command: s.command || '',
        args: JSON.stringify(s.args || []),
        env: JSON.stringify(s.env || {}),
        description: s.description || '',
        enabled: !!s.enabled,
    }
    showForm.value = true
}

async function save() {
    let args, env
    try { args = JSON.parse(form.value.args || '[]') } catch { return ElMessage.error('args 必须是合法 JSON 数组') }
    try { env = JSON.parse(form.value.env || '{}') } catch { return ElMessage.error('env 必须是合法 JSON 对象') }
    const f = form.value
    const body = {
        name: f.name.trim(), transport: f.transport,
        url: f.url.trim(), command: f.command.trim(),
        args, env, description: f.description.trim(),
        enabled: f.enabled ? 1 : 0,
    }
    if (!body.name) return ElMessage.error('name 不能为空')
    if (f.transport === 'http' && !body.url) return ElMessage.error('http 协议必须填写 url')
    if (f.transport === 'stdio' && !body.command) return ElMessage.error('stdio 协议必须填写 command')

    try {
        const d = f.id ? await api.mcpUpdate(f.id, body) : await api.mcpAdd(body)
        if (d.success) {
            ElMessage.success('已保存')
            showForm.value = false
            loadList()
        } else ElMessage.error(d.detail || '保存失败')
    } catch (e) { ElMessage.error('保存失败: ' + e.message) }
}

async function toggle(s) {
    const d = await api.mcpToggle(s.id, !s.enabled)
    if (d.success) loadList()
    else ElMessage.error(d.detail || '失败')
}

async function remove(s) {
    try { await ElMessageBox.confirm('确定删除该 MCP 服务端配置？', '删除确认', { type: 'warning' }) } catch { return }
    const d = await api.mcpDelete(s.id)
    if (d.success) { ElMessage.success('已删除'); loadList() }
    else ElMessage.error(d.detail || '失败')
}

async function reload() {
    ElMessage.info('重新连接中...')
    const d = await api.mcpReload()
    if (d.success) ElMessage.success(`已重连，工具数: ${d.tools}`)
    else ElMessage.error(d.detail || '失败')
}

async function loadTools() {
    const d = await api.mcpTools()
    tools.value = d.success ? d.tools : []
}

watch(() => props.modelValue, (v) => {
    if (v) { showForm.value = false; tools.value = []; loadList() }
})
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="MCP 服务端"
    >
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;">
            <el-button type="primary" @click="addNew">+ 新增</el-button>
            <el-button @click="reload">重新连接</el-button>
            <el-button @click="loadTools">查看已加载工具</el-button>
        </div>

        <div style="border:1px solid #eee;border-radius:8px;padding:8px;max-height:300px;overflow:auto;">
            <span v-if="!servers.length" style="color:#888;">暂无配置，点击 + 新增</span>
            <div v-for="s in servers" :key="s.id" class="list-row">
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-bottom:4px;">
                    <span class="row-title">{{ s.name }}</span>
                    <el-tag :type="s.enabled ? 'success' : 'info'" size="small">{{ s.enabled ? '启用' : '禁用' }}</el-tag>
                    <el-tag size="small">{{ s.transport || 'stdio' }}</el-tag>
                </div>
                <div class="row-meta">
                    {{ s.transport === 'http' ? (s.url || '') : ((s.command || '') + ' ' + ((s.args || []).join(' '))) }}
                </div>
                <div v-if="s.description" class="row-meta" style="color:#aaa;">{{ s.description }}</div>
                <div class="row-actions">
                    <el-button size="small" @click="toggle(s)">{{ s.enabled ? '禁用' : '启用' }}</el-button>
                    <el-button size="small" @click="edit(s)">编辑</el-button>
                    <el-button size="small" type="danger" plain @click="remove(s)">删除</el-button>
                </div>
            </div>
        </div>

        <div v-if="tools.length" style="margin-top:12px;color:#555;font-size:13px;">
            <b>已加载工具：</b>
            <div v-for="t in tools" :key="t.name" style="margin:4px 0;">
                <code>{{ t.name }}</code> — <span style="color:#666;">{{ t.description || '' }}</span>
            </div>
        </div>

        <!-- 表单 -->
        <div v-if="showForm" style="margin-top:12px;border-top:1px solid #eee;padding-top:12px;">
            <el-form :model="form" label-position="top">
                <el-form-item label="名称（唯一）">
                    <el-input v-model="form.name" placeholder="例如: mysql-local" />
                </el-form-item>
                <el-form-item label="传输协议">
                    <el-select v-model="form.transport" style="width:100%;">
                        <el-option value="http" label="http (推荐)" />
                        <el-option value="stdio" label="stdio" />
                    </el-select>
                </el-form-item>
                <el-form-item v-if="form.transport === 'http'" label="服务地址（url）">
                    <el-input v-model="form.url" placeholder="例如: http://localhost:8801/mcp" />
                </el-form-item>
                <template v-if="form.transport === 'stdio'">
                    <el-form-item label="启动命令（command）">
                        <el-input v-model="form.command" placeholder="例如: python" />
                    </el-form-item>
                    <el-form-item label="启动参数（args，JSON 数组）">
                        <el-input v-model="form.args" placeholder='["/abs/path/mysql_server.py"]' />
                    </el-form-item>
                </template>
                <el-form-item label="环境变量（env，JSON 对象）">
                    <el-input v-model="form.env" placeholder='{"MYSQL_HOST":"127.0.0.1"}' />
                </el-form-item>
                <el-form-item label="描述">
                    <el-input v-model="form.description" placeholder="可选" />
                </el-form-item>
                <el-form-item>
                    <el-checkbox v-model="form.enabled">启用</el-checkbox>
                </el-form-item>
                <div style="display:flex;justify-content:flex-end;gap:8px;">
                    <el-button @click="showForm = false">取消</el-button>
                    <el-button type="primary" @click="save">保存</el-button>
                </div>
            </el-form>
        </div>
    </AppDialog>
</template>