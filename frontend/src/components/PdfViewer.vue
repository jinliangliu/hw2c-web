<script setup lang="ts">
/**
 * PdfViewer.vue — Full-screen PDF viewer via <iframe>.
 *
 * Uses the browser's built-in PDF.js renderer (no bundling issues).
 * Remembers the last-viewed page per MCU + document type via localStorage
 * using the `#page=N` URL fragment supported by Chrome / Firefox / Edge.
 */
import { ref, computed, watch } from 'vue'

const props = defineProps<{
    part: string
    datasheetUrl: string | null
    referenceManualUrl: string | null
}>()

const emit = defineEmits<{
    (e: 'close'): void
}>()

/* ---- Active tab ---- */
const activeTab = ref<'datasheet' | 'refman'>('datasheet')

const currentUrl = computed(() =>
    activeTab.value === 'datasheet' ? props.datasheetUrl : props.referenceManualUrl
)

const currentTitle = computed(() =>
    activeTab.value === 'datasheet' ? 'Datasheet' : 'Reference Manual'
)

const hasDatasheet = computed(() => !!props.datasheetUrl)
const hasRefman = computed(() => !!props.referenceManualUrl)
const hasAny = computed(() => hasDatasheet.value || hasRefman.value)

if (!hasDatasheet.value && hasRefman.value) {
    activeTab.value = 'refman'
}

/* ---- localStorage ---- */
function storageKey(): string {
    return `pdfviewer:${props.part}:${activeTab.value}`
}
function loadLastPage(): number {
    try {
        const v = localStorage.getItem(storageKey())
        return v ? parseInt(v, 10) || 1 : 1
    } catch { return 1 }
}
function saveLastPage(page: number) {
    try { localStorage.setItem(storageKey(), String(page)) } catch { /* noop */ }
}

/* ---- Page tracking ---- */
const currentPage = ref(1)
const loading = ref(true)
const iframeSrc = ref('')
const iframeKey = ref(0)

/** Build iframe URL with restored #page=N fragment. */
function buildSrc(page: number): string {
    if (!currentUrl.value) return ''
    return `${currentUrl.value}#page=${page}`
}

/** Load the last-viewed page from localStorage and set iframe src. */
function restorePage() {
    const page = loadLastPage()
    currentPage.value = page
    iframeSrc.value = buildSrc(page)
    loading.value = true
    iframeKey.value++
}

/** Navigate to a page and persist to localStorage. */
function gotoPage(n: number) {
    if (n < 1) n = 1
    currentPage.value = n
    saveLastPage(n)
    iframeSrc.value = buildSrc(n)
    loading.value = true
    iframeKey.value++
}

/* ---- Init: load saved page on mount ---- */
restorePage()

function onIframeLoad() {
    loading.value = false
}

/* ---- Save on tab switch ---- */
watch(activeTab, () => {
    restorePage()
})

/* ---- Keyboard ---- */
function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
        emit('close')
    }
    if (e.key === 'PageDown') {
        e.preventDefault()
        gotoPage(currentPage.value + 1)
    }
    if (e.key === 'PageUp') {
        e.preventDefault()
        gotoPage(currentPage.value - 1)
    }
    if (e.key === 'Home') { e.preventDefault(); gotoPage(1) }
    if (e.key === 'End')  { e.preventDefault(); gotoPage(9999) }
}
</script>

<template>
    <div class="pdf-overlay" @click.self="emit('close')" @keydown="onKeydown" tabindex="0">
        <div class="pdf-modal">
            <!-- Header -->
            <div class="pdf-header">
                <div class="pdf-title">
                    <span class="pdf-chip">{{ part }}</span>
                    <span class="pdf-sep">—</span>
                    <span class="pdf-doc-type">{{ currentTitle }}</span>
                </div>
                <div class="pdf-tabs" v-if="hasDatasheet && hasRefman">
                    <button :class="['pdf-tab', { active: activeTab === 'datasheet' }]"
                        @click="activeTab = 'datasheet'">Datasheet</button>
                    <button :class="['pdf-tab', { active: activeTab === 'refman' }]"
                        @click="activeTab = 'refman'">RM</button>
                </div>

                <!-- Page nav -->
                <div class="pdf-pagenav">
                    <button @click="gotoPage(currentPage - 1)" title="Prev">&#8249;</button>
                    <input
                        type="number"
                        :value="currentPage"
                        @change="gotoPage(Number(($event.target as HTMLInputElement).value))"
                        min="1"
                        class="pdf-page-input"
                    />
                    <button @click="gotoPage(currentPage + 1)" title="Next">&#8250;</button>
                </div>

                <button class="pdf-close" @click="emit('close')" title="Close (Esc)">&times;</button>
            </div>

            <!-- Body -->
            <div class="pdf-body">
                <!-- Unavailable -->
                <div v-if="!hasAny" class="pdf-unavailable">
                    <p>No datasheet or reference manual available for {{ part }}.</p>
                </div>

                <template v-else>
                    <!-- Loading overlay -->
                    <div v-if="loading" class="pdf-loading">
                        <span class="pdf-spinner"></span>
                        Loading {{ currentTitle }}...
                    </div>

                    <!-- iframe -->
                    <iframe
                        :key="iframeKey"
                        :src="iframeSrc"
                        class="pdf-frame"
                        @load="onIframeLoad"
                        frameborder="0"
                    ></iframe>
                </template>
            </div>
        </div>
    </div>
</template>

<style scoped>
.pdf-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    outline: none;
}
.pdf-modal {
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: 8px;
    width: 92vw;
    height: 92vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 16px 48px rgba(0,0,0,0.4);
}

/* ---- Header ---- */
.pdf-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    flex-wrap: wrap;
}
.pdf-title {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.8rem;
}
.pdf-chip {
    font-weight: 700;
    color: var(--accent);
    font-family: monospace;
    font-size: 0.85rem;
}
.pdf-sep { color: var(--border); }
.pdf-doc-type {
    color: var(--text-dim);
    font-size: 0.7rem;
}

/* Tabs */
.pdf-tabs { display: flex; gap: 2px; margin-left: 0.5rem; }
.pdf-tab {
    padding: 3px 12px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: transparent;
    color: var(--text-dim);
    font-size: 0.65rem;
    font-weight: 600;
    cursor: pointer;
}
.pdf-tab.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
}
.pdf-tab:hover:not(.active) {
    background: var(--bg-input);
    color: var(--text);
}

/* Page nav */
.pdf-pagenav {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
    margin-right: 0.5rem;
}
.pdf-pagenav button {
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.7rem;
    padding: 2px 6px;
    border-radius: 3px;
    cursor: pointer;
    line-height: 1.2;
}
.pdf-pagenav button:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.pdf-page-input {
    width: 40px;
    text-align: center;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.7rem;
    padding: 2px 4px;
    font-family: monospace;
}

.pdf-close {
    border: none;
    background: none;
    color: var(--text-dim);
    font-size: 1.4rem;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
}
.pdf-close:hover { color: var(--text); }

/* ---- Body ---- */
.pdf-body {
    flex: 1;
    overflow: hidden;
    position: relative;
    background: #525659;
}
.pdf-loading {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--text-dim);
    font-size: 0.85rem;
}
.pdf-spinner {
    width: 18px; height: 18px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.pdf-unavailable {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-dim);
    font-size: 0.85rem;
}
.pdf-frame {
    width: 100%;
    height: 100%;
    border: none;
}
</style>
