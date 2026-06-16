<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ symbols: string[]; activeSymbol: string; names: Record<string, string> }>()
const emit = defineEmits<{ (e: 'select', s: string): void; (e: 'add', s: string): void }>()

const search = ref('')
const filtered = computed(() => {
  const q = search.value.trim().toUpperCase()
  if (!q) return props.symbols
  return props.symbols.filter((s) => s.includes(q) || (props.names[s] || '').toUpperCase().includes(q))
})

function submit() {
  const q = search.value.trim().toUpperCase()
  if (q && !props.symbols.includes(q)) emit('add', q)
}
</script>

<template>
  <aside class="watchlist">
    <div class="search">
      <input v-model="search" type="search" placeholder="搜索 / 输入 symbol 回车" @keyup.enter="submit" />
    </div>
    <button
      v-for="symbol in filtered"
      :key="symbol"
      class="item"
      :class="{ active: symbol === activeSymbol }"
      @click="emit('select', symbol)"
    >
      <span>{{ names[symbol] || symbol }}</span>
      <small>{{ symbol }}</small>
    </button>
  </aside>
</template>

<style scoped>
.watchlist { border-right: 1px solid #d7dde5; background: #fff; padding: 12px; }
.search { margin-bottom: 12px; }
.search input { width: 100%; height: 36px; border: 1px solid #cfd7e2; border-radius: 6px; padding: 0 10px; }
.item { display: block; width: 100%; margin-bottom: 8px; padding: 9px; text-align: left; border: 1px solid #d7dde5; border-radius: 6px; background: #fff; }
.item.active { border-color: #0f62fe; box-shadow: inset 3px 0 0 #0f62fe; }
.item span, .item small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item small { color: #667085; }
@media (max-width: 900px) {
  .watchlist { display: flex; gap: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid #d7dde5; }
  .search { flex: 0 0 100%; }
  .item { flex: 0 0 132px; }
}
</style>
