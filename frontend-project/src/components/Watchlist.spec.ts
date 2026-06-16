import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Watchlist from './Watchlist.vue'

const symbols = ['02723.HK', '02675.HK']
const names: Record<string, string> = { '02723.HK': '深演智能' }

describe('Watchlist', () => {
  it('点击标的 emit select', async () => {
    const w = mount(Watchlist, { props: { symbols, activeSymbol: '02723.HK', names } })
    await w.findAll('button.item')[1].trigger('click')
    expect(w.emitted('select')?.[0]).toEqual(['02675.HK'])
  })

  it('搜索过滤；回车手输新 symbol emit add', async () => {
    const w = mount(Watchlist, { props: { symbols, activeSymbol: '02723.HK', names } })
    const input = w.find('input')
    await input.setValue('00100.hk')
    await input.trigger('keyup.enter')
    expect(w.emitted('add')?.[0]).toEqual(['00100.HK'])
  })
})
