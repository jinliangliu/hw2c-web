<script setup lang="ts">
/**
 * TopologyGraph.vue — renders MCU ↔ peripheral connection topology.
 *
 * Uses SVG to draw MCU (center) connected to peripherals (ring) via color-coded
 * bus lines. Pure Vue reactive render, no external library required.
 */
import { computed } from 'vue'
import type { ConnectionInfo, PeripheralInfo } from '../api'

const props = defineProps<{
    connections: ConnectionInfo[]
    peripherals: PeripheralInfo[]
}>()

const BUS_COLORS: Record<string, string> = {
    I2C:  '#3b82f6',
    SPI:  '#10b981',
    UART: '#f59e0b',
    USART: '#f59e0b',
    GPIO: '#8b5cf6',
}

interface Node {
    id: string
    label: string
    cx: number
    cy: number
    r: number
    color: string
    isMcu: boolean
}

function busType(peri: PeripheralInfo): string {
    if (peri.bus) return peri.bus.replace(/\d/g, '')
    if (peri.uart) return 'UART'
    return 'GPIO'
}

const nodes = computed<Node[]>(() => {
    const result: Node[] = []
    const mcu: Node = {
        id: 'MCU', label: 'MCU', cx: 400, cy: 250, r: 36, color: '#3b82f6', isMcu: true,
    }
    result.push(mcu)

    const n = props.peripherals.length
    const ringR = 160
    props.peripherals.forEach((peri, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        result.push({
            id: peri.name,
            label: peri.name.length > 12 ? peri.name.slice(0, 12) + '...' : peri.name,
            cx: 400 + ringR * Math.cos(angle),
            cy: 250 + ringR * Math.sin(angle),
            r: 28,
            color: BUS_COLORS[busType(peri)] ?? BUS_COLORS.GPIO,
            isMcu: false,
        })
    })
    return result
})

interface Link {
    fromNode: Node
    toNode: Node
    color: string
    label: string
}

const links = computed<Link[]>(() => {
    const nodeMap = new Map(nodes.value.map(n => [n.id, n]))
    const result: Link[] = []
    for (const conn of props.connections) {
        const from = nodeMap.get(conn.from_ref)
        const to = nodeMap.get(conn.to_ref)
        if (from && to) {
            const bus = conn.net.split('_')[0] ?? ''
            result.push({
                fromNode: from,
                toNode: to,
                color: BUS_COLORS[bus] ?? BUS_COLORS.GPIO,
                label: conn.net,
            })
        }
    }
    // Deduplicate by label
    const seen = new Set<string>()
    return result.filter(l => {
        const key = l.label
        if (seen.has(key)) return false
        seen.add(key)
        return true
    })
})
</script>

<template>
    <div class="panel topo">
        <div class="panel-title">Topology</div>
        <svg viewBox="0 0 800 500" v-if="nodes.length > 1">
            <!-- Links -->
            <g v-for="link in links" :key="link.label">
                <line
                    :x1="link.fromNode.cx" :y1="link.fromNode.cy"
                    :x2="link.toNode.cx" :y2="link.toNode.cy"
                    :stroke="link.color" stroke-width="2" opacity="0.6"
                />
                <text
                    :x="(link.fromNode.cx + link.toNode.cx) / 2"
                    :y="(link.fromNode.cy + link.toNode.cy) / 2 - 6"
                    text-anchor="middle" :fill="link.color" font-size="9"
                >{{ link.label }}</text>
            </g>

            <!-- Nodes -->
            <g v-for="node in nodes" :key="node.id">
                <circle
                    :cx="node.cx" :cy="node.cy" :r="node.r"
                    :fill="node.isMcu ? '#1e3a5f' : '#1a2a1a'"
                    :stroke="node.color" stroke-width="2"
                />
                <text
                    :x="node.cx" :y="node.cy + 4"
                    text-anchor="middle" fill="#e2e8f0" font-size="10" font-weight="600"
                >{{ node.label }}</text>
            </g>
        </svg>
        <p v-else class="empty">Parse a netlist to see the topology graph</p>
    </div>
</template>

<style scoped>
.topo svg {
    width: 100%;
    height: auto;
    max-height: 500px;
}
.empty { color: var(--text-dim); font-size: 0.8rem; text-align: center; padding: 1rem; }
</style>
