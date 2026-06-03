<script setup>
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

const agents = ref([])
const showForm = ref(false)
const formMode = ref('add')   // add | edit
const form = ref(emptyForm())

function emptyForm() {
    return {
        id: '', name: '', description: '', domains: '["*"]',
        role: '智能助手', goal: '帮助用户完成任务。',
        backstory: '你是一个智能助手。', enabled: true,
    }
}

async function loadList() {
    const d = await api.agentList()
    agents.value = d.success ? d.agents : []
}

function addNew() {
    form.value = emptyForm()
    formMode.value = 'add'
    showForm.value = true
}

function edit(a) {
    form.value = {
        id: a.id || '', name: a.name || '',
        description: a.description || '',
        domains: JSON.stringify(a.domains || ['*']),
        role: a.role || '', goal: a.goal || '',
        backstory: a.backstory || '', enabled: !!a.enabled,
    }
    formMode.value = 'edit'
    showForm.value = true
}

async function save() {
    let domains
    try { domains = JSON.parse(form.value.domains || '["*"]') } catch { return ElMessage.error('domains 必须是合法 JSON 数组') }
    const f = form.value
    const body = {
        name: f.name.trim(),
        description: f.description.trim(),
        domains,
        role: f.role.trim(), goal: f.goal.trim(),
        backstory: f.backstory.trim(),
        enabled: f.enabled ? 1 : 0,
    }
    if (formMode.value === 'add') {
        if (!f.id.trim()) return ElMessage.error('id 不能为空')
        body.id = f.id.trim()
    }
    if (!body.name || !body.role || !body.goal || !body.backstory)
        return ElMessage.error('name/role/goal/backstory 都必填')

    const d = formMode.value === 'add' ? await api.agentAdd(body) : await api.agentUpdate(f.id, body)
    if (d.success) { ElMessage.success('已保存'); showForm.value = false; loadList() }
    else ElMessage.error(d.detail || '保存失败')
}

async function toggle(a) {
    const d = await api.agentToggle(a.id, !a.enabled)
    if (d.success) loadList()
    else ElMessage.error(d.detail || '失败')
}

async function remove(a) {
    try { await ElMessageBox.confirm(`确定删除 Agent ${a.id}？该 Agent 的专属规则也会一并清除。`, '删除确认', { type: 'warning' }) } catch { return }
    const d = await api.agentDelete(a.id)
    if (d.success) { ElMessage.success('已删除'); loadList() }
    else ElMessage.error(d.detail || '失败')
}

watch(() => props.modelValue, (v) => {
    if (v) { showForm.value = false; loadList() }
})
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="Agent 配置"
    >
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px;">
            <el-button type="primary" @click="addNew">+ 新增</el-button>
            <span class="tip-text">通用助手(general)不可删除或禁用</span>
        </div>

        <div style="border:1px solid #eee;border-radius:8px;padding:8px;max-height:300px;overflow:auto;">
            <span v-if="!agents.length" style="color:#888;">暂无 Agent</span>
            <div v-for="a in agents" :key="a.id" class="list-row">
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-bottom:4px;">
                    <span class="row-title">{{ a.name }}<span v-if="a.id === 'general'"> 🔒</span></span>
                    <span class="tip-text">[{{ a.id }}]</span>
                    <el-tag :type="a.enabled ? 'success' : 'info'" size="small">{{ a.enabled ? '启用' : '禁用' }}</el-tag>
                    <span class="tip-text">命中 {{ a.hit_count || 0 }}</span>
                </div>
                <div style="color:#666;font-size:13px;margin-bottom:2px;">{{ a.description || '' }}</div>
                <div class="row-meta">
                    domains: {{ JSON.stringify(a.domains || ['*']) }}
                    <span v-if="a.parent"> · parent: {{ a.parent }}</span>
                </div>
                <div class="row-actions">
                    <el-button v-if="a.id !== 'general'" size="small" @click="toggle(a)">{{ a.enabled ? '禁用' : '启用' }}</el-button>
                    <el-button size="small" @click="edit(a)">编辑</el-button>
                    <el-button v-if="a.id !== 'general'" size="small" type="danger" plain @click="remove(a)">删除</el-button>
                </div>
            </div>
        </div>

        <div v-if="showForm" style="margin-top:12px;border-top:1px solid #eee;padding-top:12px;">
            <el-form :model="form" label-position="top">
                <el-form-item label="ID（snake_case，新增后不可改）">
                    <el-input v-model="form.id" :disabled="formMode === 'edit'" placeholder="例如: programming" />
                </el-form-item>
                <el-form-item label="名称">
                    <el-input v-model="form.name" placeholder="例如: 编程助手" />
                </el-form-item>
                <el-form-item label="一句话描述">
                    <el-input v-model="form.description" placeholder="例如: 处理代码相关问题" />
                </el-form-item>
                <el-form-item label="负责领域（JSON 数组，* 表示兜底）">
                    <el-input v-model="form.domains" placeholder='["编程"] 或 ["*"]' />
                </el-form-item>
                <el-form-item label="Role">
                    <el-input v-model="form.role" placeholder="例如: 编程专家" />
                </el-form-item>
                <el-form-item label="Goal">
                    <el-input v-model="form.goal" type="textarea" :rows="2" placeholder="智能体目标" />
                </el-form-item>
                <el-form-item label="Backstory（描述其专业能力）">
                    <el-input v-model="form.backstory" type="textarea" :rows="4" placeholder="背景故事" />
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