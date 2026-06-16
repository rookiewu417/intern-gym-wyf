// UI broker-queue filter-tier selection (10/100/1000 档 toggle). NOT the per-row gear value.
export type Gear = 10 | 100 | 1000
export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

export interface BrokerCell {
  brokerCode: string
  displayName: string
  volume: number
}

export interface QueueLevel {
  id: string
  side: 'ask' | 'bid'
  position: number
  gear: number // raw position from server (gear === position; can be any int, e.g. 819)
  price: number
  volume: number
  brokerCount: number
  brokers: BrokerCell[]
}

export interface BrokerQueue {
  ask: QueueLevel[]
  bid: QueueLevel[]
  sourceDate?: string
  historical?: boolean
  fallback?: boolean
}

export interface MarketBar {
  timestamp: string
  price: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover: number
}

export interface TradeAlert {
  id: string
  timestamp: string
  tradeDate: string
  sourceDate: string
  historical?: boolean
  price: number
  volume: number
  turnover: number
  side: string
  thresholdVolume?: number
}

export interface SnapshotInner {
  symbol: string
  name: string
  currency?: string
  price: number
  open?: number
  high?: number
  low?: number
  volume?: number
  turnover?: number
  updatedAt: string
  tradeDate: string
}

export interface SnapshotPayload {
  symbol: string
  snapshot: SnapshotInner
  minute_bars: MarketBar[]
  alerts: TradeAlert[]
  broker_queue: BrokerQueue
  freshness: {
    runtime_state?: string
    effective_day?: string
    source_dates?: Record<string, string>
  }
}

export interface DeltaPayload {
  delta_type?: 'minute_bar' | 'trade_tick' | 'broker_queue'
  minute_bar?: MarketBar
  tick?: unknown
  alert?: TradeAlert | null
  broker_queue?: BrokerQueue
}

interface ClientHandlers {
  onStatus?: (status: WsStatus) => void
  onSnapshot?: (symbol: string, payload: SnapshotPayload, seq: number) => void
  onDelta?: (symbol: string, payload: DeltaPayload, seq: number) => void
}

export class MarketFeedClient {
  private ws: WebSocket | null = null
  private reconnectTimer: number | null = null
  private closedByClient = false
  private pendingCommands: string[] = []
  private trackedSymbols = new Set<string>()

  constructor(
    private readonly url: string,
    private readonly handlers: ClientHandlers = {},
  ) {}

  connect() {
    this.closedByClient = false
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return
    this.handlers.onStatus?.('connecting')
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.handlers.onStatus?.('open')
      this.flushPending()
      if (this.trackedSymbols.size) this.sendNow('snapshot_request', [...this.trackedSymbols])
    }
    this.ws.onerror = () => this.handlers.onStatus?.('error')
    this.ws.onclose = () => {
      this.handlers.onStatus?.('closed')
      if (!this.closedByClient) this.reconnectTimer = window.setTimeout(() => this.connect(), 1000)
    }
    this.ws.onmessage = (event) => this.handleMessage(event.data)
  }

  close() {
    this.closedByClient = true
    if (this.reconnectTimer !== null) { window.clearTimeout(this.reconnectTimer); this.reconnectTimer = null }
    this.ws?.close()
    this.ws = null
  }

  requestSnapshots(symbols: string[]) {
    symbols.forEach((s) => this.trackedSymbols.add(s))
    if (this.ws?.readyState === WebSocket.OPEN) this.sendNow('snapshot_request', symbols)
  }

  setVisible(symbols: string[]) {
    symbols.forEach((s) => this.trackedSymbols.add(s))
    this.sendCommand('visible_set', symbols)
  }

  private sendCommand(command: string, symbols: string[]) {
    const encoded = this.encode(command, symbols)
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(encoded)
    else { this.pendingCommands.push(encoded); this.connect() }
  }

  private sendNow(command: string, symbols: string[]) {
    this.ws?.send(this.encode(command, symbols))
  }

  private encode(command: string, symbols: string[]) {
    return JSON.stringify({
      schema_version: 1,
      protocol: 'terminal-message-v3',
      command,
      request_id: `${command}-${Date.now()}`,
      symbols,
    })
  }

  private flushPending() {
    if (this.ws?.readyState !== WebSocket.OPEN) return
    for (const command of this.pendingCommands.splice(0)) this.ws.send(command)
  }

  private handleMessage(raw: string) {
    const frame = JSON.parse(raw)
    const seq = Number(frame.seq || 0)
    if (frame.type === 'snapshot') this.handlers.onSnapshot?.(frame.symbol, frame.payload, seq)
    if (frame.type === 'delta') this.handlers.onDelta?.(frame.symbol, frame.payload, seq)
  }
}
