<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import AppDialog from './AppDialog.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

const items = ref([])
const editValues = ref({})  // key -> 当前编辑文本

async function load() {
    const d = await api.promptList()
    if (d.success) {
        items.value = d.items
        editValues.value = Object.fromEntries(d.items.map(it => [it.key, it.value || '']))
    }
}

async function save(key) {
    const v = editValues.value[key]
    if (!v || !v.trim()) return reset(key)
    const d = await api.promptSet(key, v)
    if (d.success) { ElMessage.success('已保存'); load() }
    else ElMessage.error(d.detail || '保存失败')
}

async function reset(key) {
    const d = await api.promptReset(key)
    if (d.success) { ElMessage.success('已恢复默认'); load() }
    else ElMessage.error(d.detail || '失败')
}

watch(() => props.modelValue, (v) => { if (v) load() })
</script>

<template>
    <AppDialog
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        title="Prompt 常量覆盖"
    >
        <div class="tip-text" style="margin-bottom:12px;">
            这里只能覆盖 prompts.py 里的"纯文本常量"（如 PLANNER_GOAL / TOOL_CATALOG）。<br>
            带 <code>{xxx}</code> 占位符的模板由代码契约管理，不开放编辑。<br>
            清空保存即恢复默认值。
        </div>

        <div v-if="!items.length" class="tip-text">加载中...</div>
        <div
            v-for="it in items"
            :key="it.key"
            style="border:1px solid #eee;border-radius:8px;padding:10px;margin-bottom:10px;"
        >
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:6px;">
                <div>
                    <b>{{ it.key }}</b>
                    <el-tag
                        :type="it.overridden ? 'success' : 'info'"
                        size="small"
                        style="margin-left:6px;"
                    >{{ it.overridden ? `已覆盖 · ${it.updated_at}` : '使用默认' }}</el-tag>
                </div>
                <div style="display:flex;gap:6px;">
                    <el-button size="small" type="primary" @click="save(it.key)">保存</el-button>
                    <el-button v-if="it.overridden" size="small" @click="reset(it.key)">恢复默认</el-button>
                </div>
            </div>
            <el-input
                v-model="editValues[it.key]"
                type="textarea"
                :rows="4"
            />
            <details style="margin-top:6px;">
                <summary class="tip-text" style="cursor:pointer;">当前生效值（默认或覆盖后）</summary>
                <pre style="white-space:pre-wrap;background:#f7f7f7;border-radius:6px;padding:8px;font-size:12px;color:#333;margin-top:4px;">{{ it.effective }}</pre>
            </details>
        </div>
    </AppDialog>
</template>