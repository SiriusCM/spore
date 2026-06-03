<script setup>
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

const skills = ref([])
const showForm = ref(false)
const overwrite = ref(false)
const fileInput = ref(null)
const form = ref(emptyForm())

function emptyForm() {
    return {
        id: null, name: '', summary: '', triggers: '',
        domains: '["*"]', content: '', enabled: true,
    }
}

async function loadList() {
    const d = await api.skillList()
    skills.value = d.success ? d.skills : []
}

function addNew() {
    form.value = emptyForm()
    showForm.value = true
}

function edit(s) {
    form.value = {
        id: s.id, name: s.name || '',
        summary: s.summary || '', triggers: s.triggers || '',
        domains: JSON.stringify(s.domains || ['*']),
        content: s.content || '', enabled: !!s.enabled,
    }
    showForm.value = true
}

async function save() {
    let domains
    try { domains = JSON.parse(form.value.domains || '["*"]') } catch { return ElMessage.error('domains 必须是合法 JSON 数组') }
    const f = form.value
    const body = {
        name: f.name.trim(), summary: f.summary.trim(),
        triggers: f.triggers.trim(), content: f.content,
        domains, enabled: f.enabled ? 1 : 0,
    }
    if (!body.name) return ElMessage.error('name 不能为空')
    if (!body.summary) return ElMessage.error('summary 不能为空（planner 需要它判断）')
    if (!body.content.trim()) return ElMessage.error('content 不能为空')

    const d = f.id ? await api.skillUpdate(f.id, body) : await api.skillAdd(body)
    if (d.success) { ElMessage.success('已保存'); showForm.value = false; loadList() }
    else ElMessage.error(d.detail || '保存失败')
}

async function toggle(s) {
    const d = await api.skillToggle(s.id, !s.enabled)
    if (d.success) loadList()
    else ElMessage.error(d.detail || '失败')
}

async function remove(s) {
    try { await ElMessageBox.confirm('确定删除该 Skill？', '删除确认', { type: 'warning' }) } catch { return }
    const d = await api.skillDelete(s.id)
    if (d.success) { ElMessage.success('已删除'); loadList() }
    else ElMessage.error(d.detail || '失败')
}

function exportZip(s) {
    const a = document.createElement('a')
    a.href = api.skillExportUrl(s.id)
    a.style.display = 'none'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
}

async function onImport(e) {
    const file = e.target.files && e.target.files[0]
    if (!file) return
    try {
        const d = await api.skillImport(file, overwrite.value)
        if (d.success) {
            ElMessage.success(d.action === 'created' ? `已导入: ${d.name}` : `已覆盖: ${d.name}`)
            loadList()
        } else ElMessage.error(d.detail || '导入失败')
    } catch (e) { ElMessage.error('导入失败: ' + e.message) }
    finally { e.target.value = '' }
}

watch(() => props.modelValue, (v) => {
    if (v) { showForm.value = false; loadList() }
})
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="Skill 配置"
    >
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px;">
            <el-button type="primary" @click="addNew">+ 新增</el-button>
            <el-button @click="fileInput.click()">导入 ZIP</el-button>
            <el-checkbox v-model="overwrite">同名覆盖</el-checkbox>
            <input ref="fileInput" type="file" accept=".zip" style="display:none;" @change="onImport">
            <span class="tip-text">Skill 是按需激活的"任务剧本"，命中后会被注入到执行者的 prompt 中</span>
        </div>

        <div style="border:1px solid #eee;border-radius:8px;padding:8px;max-height:300px;overflow:auto;">
            <span v-if="!skills.length" style="color:#888;">暂无 Skill，点击 + 新增</span>
            <div v-for="s in skills" :key="s.id" class="list-row">
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-bottom:4px;">
                    <span class="row-title">{{ s.name }}</span>
                    <el-tag :type="s.enabled ? 'success' : 'info'" size="small">{{ s.enabled ? '启用' : '禁用' }}</el-tag>
                    <span class="tip-text">命中 {{ s.hit_count || 0 }}</span>
                </div>
                <div style="color:#666;font-size:13px;margin-bottom:2px;">{{ s.summary || '' }}</div>
                <div class="row-meta">
                    domains: {{ JSON.stringify(s.domains || ['*']) }}
                    <span v-if="s.triggers"> · triggers: {{ s.triggers }}</span>
                </div>
                <div class="row-actions">
                    <el-button size="small" @click="toggle(s)">{{ s.enabled ? '禁用' : '启用' }}</el-button>
                    <el-button size="small" @click="edit(s)">编辑</el-button>
                    <el-button size="small" @click="exportZip(s)">导出</el-button>
                    <el-button size="small" type="danger" plain @click="remove(s)">删除</el-button>
                </div>
            </div>
        </div>

        <div v-if="showForm" style="margin-top:12px;border-top:1px solid #eee;padding-top:12px;">
            <el-form :model="form" label-position="top">
                <el-form-item label="名称（唯一，英文/数字/下划线，AI 用它激活）">
                    <el-input v-model="form.name" placeholder="例如: weekly_report" />
                </el-form-item>
                <el-form-item label="简介（一句话，planner 用它判断是否激活）">
                    <el-input v-model="form.summary" placeholder="例如: 生成本周工作周报" />
                </el-form-item>
                <el-form-item label="触发关键词（可选，逗号分隔）">
                    <el-input v-model="form.triggers" placeholder="例如: 周报,周总结,本周" />
                </el-form-item>
                <el-form-item label="适用领域（JSON 数组，* 表示全部）">
                    <el-input v-model="form.domains" placeholder='["*"] 或 ["编程","写作"]' />
                </el-form-item>
                <el-form-item label="正文（激活时注入到执行者 prompt 的完整内容，支持 Markdown）">
                    <el-input v-model="form.content" type="textarea" :rows="8" />
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