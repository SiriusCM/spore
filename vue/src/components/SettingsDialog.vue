<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const form = ref({ model: '', base_url: '', api_key: '' })

async function load() {
    try {
        const d = await api.getSettings()
        if (d.success) form.value = { ...form.value, ...d.settings }
    } catch {}
}

async function save() {
    try {
        const d = await api.saveSettings(form.value)
        if (d.success) {
            ElMessage.success('设置已保存')
            emit('update:modelValue', false)
        } else ElMessage.error(d.detail || '保存失败')
    } catch (e) { ElMessage.error('保存失败: ' + e.message) }
}

watch(() => props.modelValue, (v) => { if (v) load() })
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="LLM 设置"
        max-width="480px"
    >
        <el-form :model="form" label-position="top">
            <el-form-item label="模型名称 (LLM_MODEL)">
                <el-input v-model="form.model" placeholder="例如: gpt-4" />
            </el-form-item>
            <el-form-item label="API 地址 (LLM_BASE_URL)">
                <el-input v-model="form.base_url" placeholder="例如: https://api.openai.com/v1" />
            </el-form-item>
            <el-form-item label="API 密钥 (LLM_API_KEY)">
                <el-input v-model="form.api_key" type="password" show-password placeholder="your-api-key" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="$emit('update:modelValue', false)">取消</el-button>
            <el-button type="primary" @click="save">保存</el-button>
        </template>
    </AppDialog>
</template>