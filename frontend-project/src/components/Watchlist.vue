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
  if (q && !props.symbols.includes(q)) {
    emit('add', q)
    search.value = ''
  }
}
</script>

<template>
  <aside class="watchlist">
    <div class="search">
      <input v-model="search" type="search" placeholder="搜索 / 输入 symbol 回车" @keyup.enter="submit" />
    </div>
    <div class="items">
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
      <p v-if="!filtered.length" class="empty">无匹配</p>
    </div>
  </aside>
</template>

<style scoped>
.watchlist { border-right: 1px solid #d7dde5; background: #fff; padding: 12px; }
.search { margin-bottom: 12px; }
.search input { width: 100%; height: 36px; border: 1px solid #cfd7e2; border-radius: 6px; padding: 0 10px; font-size: 14px; }
.items { display: flex; flex-direction: column; gap: 8px; }
.item { display: block; width: 100%; padding: 9px; text-align: left; border: 1px solid #d7dde5; border-radius: 6px; background: #fff; cursor: pointer; }
.item.active { border-color: #0f62fe; box-shadow: inset 3px 0 0 #0f62fe; }
.item span, .item small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item span { font-weight: 600; }
.item small { color: #667085; }
.empty { color: #667085; font-size: 12px; margin: 0; }

@media (max-width: 900px) {
  /* 置顶：搜索独占一行，下面是可横滑的 symbol chip 条 */
  .watchlist { min-width: 0; position: sticky; top: 0; z-index: 5; padding: 10px 12px; border-right: 0; border-bottom: 1px solid #d7dde5; }
  .search { margin-bottom: 10px; }
  .items { flex-direction: row; overflow-x: auto; gap: 8px; padding-bottom: 2px; scrollbar-width: thin; -webkit-overflow-scrolling: touch; }
  .item { width: auto; flex: 0 0 auto; min-width: 104px; max-width: 150px; padding: 8px 12px; }
  .item.active { background: #eef4ff; }
  .item span { font-size: 14px; }
}
</style>
