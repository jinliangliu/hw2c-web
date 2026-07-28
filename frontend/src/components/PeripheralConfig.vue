<script setup lang="ts">
/**
 * PeripheralConfig.vue — Orchestrator: selects the right config panel by peripheral type.
 *
 * When a peripheral is clicked in PeripheralList, this panel renders the matching
 * configuration form (I2C/SPI/UART/GPIO). All mutations flow through
 * writePeripheral / writePin → auto-update YAML.
 */
import type { PeripheralModel, PinModel } from '../../composables/useHardwareModel'
import I2CConfig from './configs/I2CConfig.vue'
import SPIConfig from './configs/SPIConfig.vue'
import UARTConfig from './configs/UARTConfig.vue'
import GPIOConfig from './configs/GPIOConfig.vue'

const props = defineProps<{
    peripheral: PeripheralModel
    pins: PinModel[]
    index: number
}>()

const emit = defineEmits<{
    (e: 'update-peripheral', field: string, value: unknown): void
    (e: 'update-pin', pinIndex: number, field: string, value: unknown): void
}>()

function onPeripheralUpdate(field: string, value: unknown) {
    emit('update-peripheral', field, value)
}

function onPinUpdate(pinIndex: number, field: string, value: unknown) {
    emit('update-pin', pinIndex, field, value)
}

function configKey(t: string): string {
    const u = t.toUpperCase()
    if (u.includes('I2C') || u.includes('EEPROM')) return 'i2c'
    if (u.includes('SPI') || u.includes('FLASH') || u.includes('ETHERNET'))
        return 'spi'
    if (u.includes('UART') || u.includes('RS') || u.includes('CELLULAR') ||
        u.includes('WIFI') || u.includes('BT_') || u.includes('GNSS'))
        return 'uart'
    return 'gpio'
}
</script>

<template>
    <div class="panel config-panel" v-if="peripheral">
        <div class="panel-title">
            Configure: <strong>{{ peripheral.name }}</strong>
            <span class="type-tag tag" :class="{
                'tag-i2c': configKey(peripheral.type) === 'i2c',
                'tag-spi': configKey(peripheral.type) === 'spi',
                'tag-uart': configKey(peripheral.type) === 'uart',
                'tag-gpio': configKey(peripheral.type) === 'gpio',
            }">{{ peripheral.type }}</span>
        </div>

        <I2CConfig
            v-if="configKey(peripheral.type) === 'i2c'"
            :peripheral="peripheral"
            @update="onPeripheralUpdate"
        />
        <SPIConfig
            v-else-if="configKey(peripheral.type) === 'spi'"
            :peripheral="peripheral"
            @update="onPeripheralUpdate"
        />
        <UARTConfig
            v-else-if="configKey(peripheral.type) === 'uart'"
            :peripheral="peripheral"
            @update="onPeripheralUpdate"
        />
        <GPIOConfig
            v-else
            :peripheral="peripheral"
            :pins="pins"
            @update-peripheral="onPeripheralUpdate"
            @update-pin="onPinUpdate"
        />
    </div>
</template>

<style scoped>
.config-panel {
    background: var(--bg-card);
    border-left: 2px solid var(--accent);
}
.panel-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}
strong { font-weight: 600; color: var(--text); text-transform: none; letter-spacing: 0; }
.type-tag { font-size: 0.65rem; }
</style>
