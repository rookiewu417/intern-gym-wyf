<script setup lang="ts">
const props = defineProps<{ status: 'Live' | 'Warm' | 'Closed' | 'Connecting' | 'Error' }>()
const cls = () => props.status.toLowerCase()
</script>

<template>
  <strong class="chip" :class="cls()">{{ status }}</strong>
</template>

<style scoped>
.chip { border-radius: 999px; padding: 6px 10px; background: #f1f4f9; color: #344054; font-size: 13px; }
.chip.live { background: #e9f8ef; color: #137333; }
.chip.error, .chip.closed { background: #fdecec; color: #b42318; }
.chip.connecting, .chip.warm { background: #f1f4f9; color: #344054; }
</style>
