<script setup lang="ts">
import { computed } from 'vue'
import { formatCompact, formatPrice } from '../utils/marketFormat'
import BrokerCell from './BrokerCell.vue'
import type { QueueLevel } from '../services/marketFeed'

const props = defineProps<{ level: QueueLevel; expanded: boolean }>()
const emit = defineEmits<{ (e: 'toggle'): void }>()
const VISIBLE = 3
const shown = computed(() => (props.expanded ? props.level.brokers : props.level.brokers.slice(0, VISIBLE)))
const overflow = computed(() => Math.max(0, props.level.brokers.length - VISIBLE))
</script>

<template>
  <li class="row">
    <div class="head">
      <span class="pos">{{ level.position }}档</span>
      <strong>{{ formatPrice(level.price) }}</strong>
      <em>{{ formatCompact(level.volume) }}</em>
      <small>{{ level.brokerCount }} 家</small>
    </div>
    <div class="cells">
      <BrokerCell v-for="(b, i) in shown" :key="i" :broker="b" />
      <button v-if="overflow" class="more" @click="emit('toggle')">{{ expanded ? '收起' : `+${overflow}` }}</button>
    </div>
  </li>
</template>

<style scoped>
.row { list-style: none; border-bottom: 1px solid #eef2f6; padding: 6px 0; }
/* 固定档头四列轨道宽度：展开/收起 cells 不改变列宽 */
.head { display: grid; grid-template-columns: 48px 1fr 72px 48px; gap: 8px; align-items: center; font-size: 13px; }
.head em { color: #344054; font-style: normal; text-align: right; }
.head small { color: #667085; text-align: right; }
.cells { margin-top: 4px; }
.more { padding: 2px 6px; margin: 2px; border: 1px solid #cfd7e2; border-radius: 4px; background: #f7f9fc; font-size: 12px; cursor: pointer; }
</style>
