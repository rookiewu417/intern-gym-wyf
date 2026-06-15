<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { MarketFeedClient, type SnapshotPayload } from './services/marketFeed'

const symbols = ['02723.HK', '02675.HK', '00100.HK', '02513.HK', '06082.HK']
const activeSymbol = ref(symbols[0])
const connected = ref(false)
const snapshots = ref<Record<string, SnapshotPayload>>({})

let client: MarketFeedClient | null = null

const activeSnapshot = computed(() => snapshots.value[activeSymbol.value])

onMounted(() => {
  client = new MarketFeedClient('ws://127.0.0.1:9021/ws', {
    onStatus: (value) => {
      connected.value = value === 'open'
    },
    onSnapshot: (symbol, payload) => {
      snapshots.value = { ...snapshots.value, [symbol]: payload }
    },
    onDelta: () => {
      // TODO: apply deltas incrementally instead of relying only on snapshots.
    },
  })
  client.connect()
  client.requestSnapshots(symbols)
})

onBeforeUnmount(() => {
  client?.close()
})
</script>

<template>
  <main class="terminal">
    <aside class="watchlist">
      <button
        v-for="symbol in symbols"
        :key="symbol"
        :class="{ active: symbol === activeSymbol }"
        @click="activeSymbol = symbol"
      >
        {{ snapshots[symbol]?.snapshot.name || symbol }}
        <small>{{ symbol }}</small>
      </button>
    </aside>

    <section class="workspace">
      <header>
        <div>
          <h1>{{ activeSnapshot?.snapshot.name || activeSymbol }}</h1>
          <span>{{ activeSymbol }}</span>
        </div>
        <strong>{{ connected ? 'Live' : 'Connecting' }}</strong>
      </header>

      <pre>{{ activeSnapshot }}</pre>
    </section>
  </main>
</template>

<style scoped>
.terminal {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
  font-family: Inter, system-ui, sans-serif;
  color: #17202a;
}

.watchlist {
  border-right: 1px solid #d7dde5;
  padding: 12px;
}

.watchlist button {
  display: block;
  width: 100%;
  margin-bottom: 8px;
  padding: 8px;
  text-align: left;
  border: 1px solid #d7dde5;
  background: white;
}

.watchlist button.active {
  border-color: #1463ff;
}

.watchlist small {
  display: block;
  color: #667085;
}

.workspace {
  padding: 16px;
  overflow: auto;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #d7dde5;
  margin-bottom: 16px;
}

h1 {
  margin: 0;
  font-size: 20px;
}

pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f6f8fb;
  padding: 12px;
}

@media (max-width: 760px) {
  .terminal {
    grid-template-columns: 1fr;
  }

  .watchlist {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid #d7dde5;
  }

  .watchlist button {
    min-width: 132px;
  }
}
</style>

