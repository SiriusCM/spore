<script setup>
// 统一封装的 dialog：自适应窗口大小，不会超出主窗口
import { computed } from 'vue'

const props = defineProps({
    modelValue: Boolean,
    title: String,
    width: { type: String, default: '92vw' },   // 永远不超出主窗
    maxWidth: { type: String, default: '760px' },
})
const emit = defineEmits(['update:modelValue'])
const visible = computed({
    get: () => props.modelValue,
    set: (v) => emit('update:modelValue', v),
})
</script>

<template>
    <el-dialog
        v-model="visible"
        :title="title"
        :width="width"
        :style="{ maxWidth }"
        :close-on-click-modal="true"
        align-center
        destroy-on-close
        class="app-dialog"
    >
        <div class="app-dialog-body">
            <slot />
        </div>
        <template v-if="$slots.footer" #footer>
            <slot name="footer" />
        </template>
    </el-dialog>
</template>

<style>
.app-dialog .el-dialog__body { padding-top: 8px; padding-bottom: 8px; }
.app-dialog .app-dialog-body { max-height: 70vh; overflow-y: auto; padding-right: 4px; }
</style>