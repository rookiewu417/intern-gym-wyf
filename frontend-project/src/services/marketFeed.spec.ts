import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MarketFeedClient } from './marketFeed'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor(public url: string) { MockWebSocket.instances.push(this) }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = 3; this.onclose?.() }
  open() { this.readyState = MockWebSocket.OPEN; this.onopen?.() }
}

describe('MarketFeedClient', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    ;(globalThis as any).WebSocket = MockWebSocket as any
  })
  afterEach(() => vi.useRealTimers())

  it('重连后自动重发 snapshot_request（tracked symbols）', () => {
    const client = new MarketFeedClient('ws://x', {})
    client.connect()
    client.requestSnapshots(['A'])               // CONNECTING：仅记录 tracked
    const ws1 = MockWebSocket.instances[0]
    ws1.open()
    expect(ws1.sent.filter(s => s.includes('snapshot_request')).length).toBe(1)
    ws1.close()                                   // 非主动关闭
    vi.advanceTimersByTime(1000)                  // 触发重连
    const ws2 = MockWebSocket.instances[1]
    ws2.open()
    expect(ws2.sent.filter(s => s.includes('snapshot_request')).length).toBe(1)
  })

  it('snapshot 帧把 frame.seq 透传给 onSnapshot', () => {
    const seqs: number[] = []
    const client = new MarketFeedClient('ws://x', { onSnapshot: (_sym, _p, seq) => seqs.push(seq) })
    client.connect()
    const ws = MockWebSocket.instances[0]
    ws.open()
    ws.onmessage?.({ data: JSON.stringify({ type: 'snapshot', symbol: 'A', seq: 7, payload: {} }) })
    expect(seqs).toEqual([7])
  })

  it('close() 后不再重连', () => {
    const client = new MarketFeedClient('ws://x', {})
    client.connect()
    MockWebSocket.instances[0].open()
    client.close()
    vi.advanceTimersByTime(2000)
    expect(MockWebSocket.instances.length).toBe(1) // 无新连接
  })

  it('delta 帧把 frame.seq 透传给 onDelta', () => {
    const seqs: number[] = []
    const client = new MarketFeedClient('ws://x', { onDelta: (_s, _p, seq) => seqs.push(seq) })
    client.connect()
    const ws = MockWebSocket.instances[0]
    ws.open()
    ws.onmessage?.({ data: JSON.stringify({ type: 'delta', symbol: 'A', seq: 9, payload: { delta_type: 'broker_queue' } }) })
    expect(seqs).toEqual([9])
  })

  it('setVisible 不会让 reconnect 为仅可见 symbol 重发 snapshot_request', () => {
    const client = new MarketFeedClient('ws://x', {})
    client.connect()
    const ws1 = MockWebSocket.instances[0]
    ws1.open()
    client.setVisible(['V']) // 仅声明可见
    ws1.close()
    vi.advanceTimersByTime(1000)
    const ws2 = MockWebSocket.instances[1]
    ws2.open()
    expect(ws2.sent.filter(s => s.includes('snapshot_request')).length).toBe(0)
  })
})
