# UI Gap Fix Plan: hw2c-web 前端交互能力补全

> 状态：规划中 | 仓库：hw2c-web | 依赖：hw2c parser/generator 已就绪

## 背景

后端能力（ConstraintEngine、BehaviorModel、SleepModel、AF_TABLE）已完整实现，但前端 5 项核心交互缺失，导致用户只能"查看"解析结果，无法进行交互式配置。

## 问题矩阵

| # | 问题 | 严重度 | 根因 |
|---|------|:--:|------|
| G1 | 无状态机可视化编辑器 | 🔴 核心 | BehaviorModel 有数据无 UI |
| G2 | 无引脚拖拽/选择分配 | 🔴 核心 | PinChip click 处理器为空，PinTable 未集成 |
| G3 | 任务编排参数不足 | 🟡 增强 | 缺少 entry/period/type 字段 |
| G4 | 无低功耗策略面板 | 🟡 增强 | SleepModel 仅 mode:string，无 UI |
| G5 | 无实时校验反馈 | 🔴 核心 | ConstraintEngine 未接入 PinChip |

## 总体方案

```
                    ┌──────────────────────────────────────┐
                    │          App.vue (4 Tabs)             │
                    │                                      │
   Hardware Tab ────┤  PinChip.vue  ← ConstraintEngine     │
                    │    ├─ 点击引脚 → 弹出 AF 选择菜单      │
                    │    ├─ 冲突引脚 → 红色闪烁边框          │
                    │    └─ 外设配置面板含引脚选择器         │
                    │                                      │
   Tasks Tab ───────┤  TaskAllocator.vue (扩展字段)         │
                    │  TaskGraph.vue (增加编辑能力)          │
                    │  StateMachineEditor.vue (NEW)         │
                    │                                      │
   Sleep Panel ─────┤  SleepConfig.vue (NEW)               │
   (侧栏 / 弹窗)    │    ├─ STOP0/1/2 选择                 │
                    │    ├─ 调压器等级                       │
                    │    └─ 唤醒源 GPIO/RTC/LPUART          │
                    │                                      │
   Bind Tab ────────┤  BindGraph.vue (已有, 不变)           │
   YAML Tab ────────┤  YamlEditor.vue (已有, 不变)          │
                    └──────────────────────────────────────┘
```

---

## Phase 1: G5 — 实时校验反馈

**优先级最高**：不依赖新组件，接入已有能力即可生效。

### 1.1 ConstraintEngine 接入 PinChip

[PinChip.vue](file:///c:/Users/pc/Documents/hw2c-web/frontend/src/components/PinChip.vue) 当前不导入 ConstraintEngine。变更：

```typescript
// PinChip.vue — import constraint engine
import { validate, type PinAssignment } from '../composables/ConstraintEngine'

// New prop: validation result from parent
const props = defineProps<{
    // ...existing props...
    conflicts?: Set<string>    // pin IDs that have errors
    warnings?: Set<string>     // pin IDs that have warnings
}>()
```

**视觉反馈**（变更 PinChip 模板）：

| 状态 | 视觉 | CSS |
|------|------|-----|
| 正常 | 当前样式，不变 | — |
| 警告 | 引脚框黄色虚线闪烁 | `.pin-warning { border-color: #f59e0b; animation: pulse 1.5s infinite; }` |
| 冲突 | 引脚框红色实线 + 背景淡红 | `.pin-conflict { border-color: #ef4444; background: rgba(239,68,68,0.15); }` |

### 1.2 App.vue 接入校验

```typescript
// App.vue
import { validate, type PinAssignment } from './composables/ConstraintEngine'

const validationResult = computed(() => {
    const assignments: PinAssignment[] = hwModel.pins.map(p => ({
        pinId: p.id, function: p.function, af: p.af, label: p.label,
    }))
    return validate(assignments, hwModel.pins.map(p => p.id))
})

const conflictPins = computed(() =>
    new Set(validationResult.value.issues.filter(i => i.severity === 'error').map(i => i.pinId))
)
```

Template:

```html
<PinChip
    :conflicts="conflictPins"
    :warnings="warningPins"
    @select-pin="handlePinSelect"
/>
```

### 1.3 错误汇总角标

PinChip 上方增加徽章：

```html
<div v-if="conflictPins.size" class="validation-badge error">
    {{ conflictPins.size }} pin conflict(s)
</div>
```

**验收**：
- AF 冲突引脚 → PinChip 上红色边框
- 保留引脚被占用 → PinChip 上红色边框
- 无冲突时无任何变化，不破坏现有外观

---

## Phase 2: G2 — 引脚交互式分配

### 2.1 PinChip 引脚点击弹出 AF 选择器

变更 `App.vue` 中的 `handlePinSelect`（当前为空函数）：

```typescript
const selectedPin = ref<string | null>(null)

function handlePinSelect(pinId: string) {
    selectedPin.value = pinId
    // 打开 AF 选择弹窗 / 侧面板
}
```

新增 `PinAfSelector.vue` 组件：

```
┌─────────────────────────────────┐
│  Pin PA2                    [X] │
├─────────────────────────────────┤
│  Current: GPIO_Input (AF 0)     │
│                                 │
│  Available Functions:           │
│  ┌───────────────────────────┐  │
│  │ ○ USART2_TX      AF 1    │  │
│  │ ○ TIM2_CH3       AF 2    │  │
│  │ ● GPIO_Output    AF 0    │  │  ← 当前已选
│  │ ○ SPI1_MISO      AF 0    │  │
│  │ ○ I2C2_SDA       AF 1    │  │
│  └───────────────────────────┘  │
│                                 │
│  GPIO Config:                   │
│  ├─ Direction: [Output ▼]      │
│  ├─ Pull:      [Pull-up ▼]     │
│  └─ Speed:     [Low ▼]         │
│                                 │
│  [Apply]  [Cancel]              │
└─────────────────────────────────┘
```

数据源：`Lqfp64Pinout.ts` 中的 `AF_TABLE`。

### 2.2 外设配置面板增加引脚选择器

以 `UARTConfig.vue` 为例：

```html
<label>TX Pin</label>
<select v-model="uart.txPin"
        :class="{ 'pin-conflict': isPinConflict(uart.txPin) }">
    <option v-for="pin in availableTxPins" :key="pin.id" :value="pin.id">
        {{ pin.id }} (AF{{ pin.af }})
    </option>
</select>

<label>RX Pin</label>
<select v-model="uart.rxPin">
    <option v-for="pin in availableRxPins" :key="pin.id" :value="pin.id">
        {{ pin.id }} (AF{{ pin.af }})
    </option>
</select>
```

数据源：`ConstraintEngine.findFunctionsForPin()` + `AF_TABLE`。

### 2.3 拖拽引脚到外设（可选增强）

作为 Phase 2 的高级交互模式，允许从 PinChip 拖拽引脚到 PeripheralList：

```typescript
// PinChip.vue — 增加 draggable
@dragstart="onDragStart(pad.pp.id)"

// PeripheralList.vue — 增加 drop zone
@dragover.prevent
@drop="onDropPin($event, peripheral.name)"
```

此为可选项，不阻塞 Phase 2 交付。

**验收**：
- 点击 PinChip 引脚 → 弹出 AF 选择菜单
- 选择新功能 → 实时更新引脚颜色和标签
- UART/SPI/I2C Config 面板有引脚下拉选择器
- 选择已被占用的引脚 → 下拉选项中高亮冲突

---

## Phase 3: G3 — 任务编排参数扩展

### 3.1 AppTaskModel 扩展

[useTaskModel.ts](file:///c:/Users/pc/Documents/hw2c-web/frontend/src/composables/useTaskModel.ts) — 扩展接口：

```typescript
export interface AppTaskModel {
    name: string
    priority: number           // 1-5
    stack_size: number         // bytes
    entry: string              // NEW: entry function name (e.g. "vSensorTask")
    type: TaskType             // NEW: 'periodic' | 'continuous' | 'event_driven' | 'one_shot'
    auto_start: boolean        // NEW: auto-create on boot
    period_ms?: number         // NEW: period in ms (periodic only)
    queue_size?: number        // NEW: task notification queue depth
}
```

### 3.2 TaskAllocator 表单扩展

新增字段：

```html
<!-- Entry Function -->
<input v-model="newEntry" placeholder="vTaskName" />

<!-- Task Type -->
<select v-model="newType">
    <option value="periodic">Periodic</option>
    <option value="continuous">Continuous</option>
    <option value="event_driven">Event-Driven</option>
    <option value="one_shot">One-Shot</option>
</select>

<!-- Period (if periodic) -->
<input v-if="newType === 'periodic'" v-model.number="newPeriod" type="number" />

<!-- Auto Start -->
<label>
    <input type="checkbox" v-model="newAutoStart" /> Auto-start on boot
</label>
```

### 3.3 TaskGraph 增加编辑能力

- 点击节点 → 侧面板显示参数编辑器
- 节点右键菜单 → Edit / Delete
- 支持拖拽排序（Y 轴位置反映执行顺序）

**验收**：
- 新建任务时有完整参数表单
- TaskGraph 节点点击可编辑参数
- YAML 输出包含新增字段

---

## Phase 4: G1 — 状态机可视化编辑器

### 4.1 新增 Behavior Tab / Panel

在 App.vue 中新增第 5 个 Tab（或作为 Tasks 的子面板）：

```typescript
const activeTab = ref<'chip' | 'tasks' | 'behavior' | 'bind' | 'yaml'>('chip')
```

### 4.2 StateMachineEditor.vue

基于 Vue Flow 实现，技术栈与 BindGraph 一致（可复用 Handle、节点样式）：

```
┌──────────────────────────────────────────────────────┐
│  State Machine Editor                   [Add State]  │
│                                                      │
│    ┌──────────┐     BUTTON_PRESS     ┌──────────┐   │
│    │   IDLE   │─────────────────────>│  ACTIVE  │   │
│    │          │                      │          │   │
│    │ entry/   │     TIMEOUT_5S       │ do/      │   │
│    │   led=0  │<─────────────────────│   led=1  │   │
│    └──────────┘                      └──────────┘   │
│         │                                  │         │
│         │ RTC_TICK (every 1s)              │         │
│         ▼                                  ▼         │
│    ┌──────────┐                      ┌──────────┐   │
│    │  SLEEP   │                      │  ERROR   │   │
│    └──────────┘                      └──────────┘   │
│                                                      │
├──────────────────────────────────────────────────────┤
│  State: [IDLE ▼]                                     │
│  ├─ On Entry: set_led(0); counter=0                  │
│  ├─ On Exit:  log_state_change("IDLE")               │
│  └─ Events:                                          │
│      ├─ BUTTON_PRESS → ACTIVE                        │
│      └─ RTC_TICK → SLEEP                             │
└──────────────────────────────────────────────────────┘
```

**节点类型**：

| 节点类型 | 形状 | 内容 |
|---------|------|------|
| State | 圆角矩形 | 名称 + entry/do/exit 摘要 |
| Choice | 菱形 | 条件分支配额 |
| Fork/Join | 粗横线 | 并行分支 |

**连线类型**：

| 类型 | 线条 | 标签 |
|------|------|------|
| Transition | 实线箭头 | event_name [guard] / action |

**拖拽交互**：
- 左侧面板拖入 State 节点创建
- State → State 拖拽连线创建 Transition
- 双击连线 → 编辑 event / guard / action
- 点击节点 → 底部属性面板编辑 entry/do/exit

### 4.3 变量与类型面板

侧边栏：自定义类型(`types`) 和共享变量(`variables`) 编辑器。

```html
<!-- Variables Panel -->
<div class="var-list">
    <div v-for="v in behavior.variables" class="var-item">
        <input v-model="v.name" placeholder="var_name" />
        <select v-model="v.type">
            <option>uint8_t</option>
            <option>uint16_t</option>
            <option>uint32_t</option>
            <option>int32_t</option>
            <option>float</option>
            <option>bool</option>
        </select>
        <input v-model="v.default" placeholder="init value" />
    </div>
</div>

<!-- Types Panel -->
<div class="type-list">
    <div v-for="t in behavior.types" class="type-item">
        <select v-model="t.kind">
            <option>struct</option>
            <option>enum</option>
            <option>union</option>
        </select>
        <input v-model="t.name" placeholder="type_name" />
    </div>
</div>
```

**验收**：
- 拖入 State 节点创建新状态
- State → State 连线创建 transition
- 双击连线编辑 event/guard/action
- 底部面板编辑 entry/do/exit
- 变量和自定义类型的增删改
- YAML 输出实时同步

---

## Phase 5: G4 — 低功耗策略配置

### 5.1 SleepModel 扩展

```typescript
// useHardwareModel.ts
export interface SleepModel {
    enabled: boolean
    mode: 'SLEEP' | 'STOP0' | 'STOP1' | 'STANDBY' | 'SHUTDOWN'
    enter_on_exit: boolean           // return to sleep after ISR
    regulator_voltage_scale: 1 | 2 | 3   // VOS
    flash_power_down: boolean
    wakeup_sources: WakeupSource[]
}

export interface WakeupSource {
    type: 'gpio' | 'rtc_alarm' | 'rtc_wakeup' | 'lpuart' | 'iwdg'
    pin?: string          // for gpio: PA0 (WKUP1), PC13 (WKUP2), etc.
    edge?: 'rising' | 'falling' | 'both'
    period_s?: number     // for rtc_wakeup
}
```

### 5.2 SleepConfig.vue

作为 Hardware Tab 的子面板或独立弹窗：

```
┌─────────────────────────────────────────────┐
│  Low-Power Configuration                    │
├─────────────────────────────────────────────┤
│  Enable Sleep:         [✓]                  │
│  Sleep Mode:           [STOP1 ▼]           │
│  Enter on Exit (WFI):  [✓]                 │
│  Regulator VOS:        [Scale 2 ▼]          │
│  Flash Power Down:     [ ]                  │
├─────────────────────────────────────────────┤
│  Wakeup Sources:              [+ Add]       │
│  ┌───────────────────────────────────────┐  │
│  │ @ GPIO   PA0 (WKUP1)  rising [DEL]  │  │
│  │ @ RTC    Alarm A       —       [DEL] │  │
│  │ @ LPUART LPUART1       RXNE   [DEL] │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│  [Apply]  [Cancel]                         │
└─────────────────────────────────────────────┘
```

**验收**：
- 选择 SLEEP / STOP0 / STOP1 / STANDBY / SHUTDOWN
- 可添加/删除多个唤醒源
- GPIO 唤醒可选择引脚和边沿
- RTC 唤醒可设置周期
- YAML 输出实时同步

---

## 实施顺序

```
Phase 1 (G5) ──→ Phase 2 (G2) ──→ Phase 3 (G3) ──→ Phase 4 (G1) ──→ Phase 5 (G4)
  2 天            3 天             1.5 天           3 天             1 天

  G5 先做：     G2 紧随：        G3 快速：        G1 核心：         G4 收尾：
  改动最小      引脚选择器       3个字段扩展      状态机编辑器       低功耗面板
  接入已有能力  复用AF_TABLE     表单+TaskGraph    Vue Flow 复用     SleepConfig
```

| Phase | 新增组件 | 修改组件 |
|-------|---------|---------|
| G5 | — | PinChip.vue, App.vue |
| G2 | PinAfSelector.vue | PinChip.vue, UARTConfig.vue, SPIConfig.vue, I2CConfig.vue, GPIOConfig.vue, App.vue |
| G3 | — | TaskAllocator.vue, TaskGraph.vue, useTaskModel.ts |
| G1 | StateMachineEditor.vue | App.vue, useTaskModel.ts |
| G4 | SleepConfig.vue | App.vue, useHardwareModel.ts |

## 不做的事情

| 不做的 | 原因 |
|--------|------|
| PinChip 拖拽到外设 | 可选增强，点击 + 下拉已满足需求 |
| TaskGraph 时间线视图 | 独立需求，Phase 6 单独评估 |
| 代码生成预览（C代码） | 属于 YAML Tab 的 CodeMirror 区域，功能已覆盖 |
| 多 MCU 封装支持 | 当前仅 LQFP64，扩展需单独设计 |
