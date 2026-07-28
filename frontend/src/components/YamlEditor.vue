<script setup lang="ts">
/**
 * YamlEditor.vue — CodeMirror 6 YAML editor with dark theme.
 *
 * Emits 'update:modelValue' on every change so parent can v-model the YAML string.
 */
import { ref, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { EditorView, keymap, lineNumbers, highlightActiveLine } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { yaml as yamlLang } from '@codemirror/lang-yaml'
import { oneDark } from '@codemirror/theme-one-dark'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'

const props = defineProps<{
    modelValue: string
}>()

const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void
}>()

const editorHost = ref<HTMLDivElement | null>(null)
let editorView: EditorView | null = null
let syncingFromProp = false

function createEditor() {
    if (!editorHost.value) return

    const updateListener = EditorView.updateListener.of(update => {
        if (!update.docChanged || syncingFromProp) return
        const value = update.state.doc.toString()
        emit('update:modelValue', value)
    })

    const state = EditorState.create({
        doc: props.modelValue,
        extensions: [
            lineNumbers(),
            highlightActiveLine(),
            history(),
            yamlLang(),
            oneDark,
            keymap.of([...defaultKeymap, ...historyKeymap]),
            updateListener,
            EditorView.theme({
                '&': { height: '100%' },
                '.cm-scroller': { overflow: 'auto' },
                '.cm-content': { fontFamily: '"Cascadia Code", "Fira Code", monospace', fontSize: '13px' },
                '.cm-gutters': { backgroundColor: '#1a1f2e', borderRight: '1px solid #2d3748', color: '#556' },
            }),
        ],
    })

    editorView = new EditorView({
        state,
        parent: editorHost.value,
    })
}

// Sync prop → editor (external changes, e.g. loadFromApi)
watch(() => props.modelValue, (newVal) => {
    if (!editorView) return
    const current = editorView.state.doc.toString()
    if (current === newVal) return
    syncingFromProp = true
    editorView.dispatch({
        changes: { from: 0, to: editorView.state.doc.length, insert: newVal },
    })
    syncingFromProp = false
})

onMounted(() => {
    // Delay to ensure DOM is ready
    requestAnimationFrame(createEditor)
})

onBeforeUnmount(() => {
    editorView?.destroy()
    editorView = null
})
</script>

<template>
    <div ref="editorHost" class="editor-host"></div>
</template>

<style scoped>
.editor-host {
    flex: 1;
    overflow: hidden;
    border-radius: 0 0 var(--radius) var(--radius);
}

/* CodeMirror takes over the host, fill it */
.editor-host :deep(.cm-editor) {
    height: 100%;
}
</style>
