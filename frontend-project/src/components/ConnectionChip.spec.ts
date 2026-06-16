import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConnectionChip from './ConnectionChip.vue'

describe('ConnectionChip', () => {
  it('渲染状态文案与对应 class', () => {
    const w = mount(ConnectionChip, { props: { status: 'Connecting' } })
    expect(w.text()).toContain('Connecting')
    expect(w.find('.chip').classes()).toContain('connecting')
  })
  it('Live 状态映射 live class', () => {
    const w = mount(ConnectionChip, { props: { status: 'Live' } })
    expect(w.find('.chip').classes()).toContain('live')
  })
})
