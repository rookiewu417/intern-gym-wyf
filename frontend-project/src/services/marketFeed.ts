export interface SnapshotPayload {
  symbol: string
  snapshot: {
    symbol: string
    name: string
    price: number
    updatedAt: string
    tradeDate: string
  }
  minute_bars: Array<Record<string, unknown>>
  alerts: Array<Record<string, unknown>>
  broker_queue: {
    ask: Array<Record<string, unknown>>
    bid: Array<Record<string, unknown>>
  }
  freshness: Record<string, unknown>
}

interface ClientHandlers {
  onStatus?: (status: 'open' | 'closed' | 'error') => void
  onSnapshot?: (symbol: string, payload: SnapshotPayload) => void
  onDelta?: (symbol: string, payload: Record<string, unknown>) => void
}

export class MarketFeedClient {
  private ws: WebSocket | null = null
  private reconnectTimer: number | null = null

  constructor(
    private readonly url: string,
    private readonly handlers: ClientHandlers = {},
  ) {}

  connect() {
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => this.handlers.onStatus?.('open')
    this.ws.onerror = () => this.handlers.onStatus?.('error')
    this.ws.onclose = () => {
      this.handlers.onStatus?.('closed')
      this.reconnectTimer = window.setTimeout(() => this.connect(), 1000)
    }
    this.ws.onmessage = (event) => this.handleMessage(event.data)
  }

  close() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
    }
    this.ws?.close()
  }

  requestSnapshots(symbols: string[]) {
    this.sendCommand('snapshot_request', symbols)
  }

  setVisible(symbols: string[]) {
    this.sendCommand('visible_set', symbols)
  }

  private sendCommand(command: string, symbols: string[]) {
    const frame = {
      schema_version: 1,
      protocol: 'terminal-message-v3',
      command,
      request_id: `${command}-${Date.now()}`,
      symbols,
    }
    const send = () => this.ws?.send(JSON.stringify(frame))
    if (this.ws?.readyState === WebSocket.OPEN) {
      send()
    } else {
      window.setTimeout(send, 250)
    }
  }

  private handleMessage(raw: string) {
    const frame = JSON.parse(raw)
    if (frame.type === 'snapshot') {
      this.handlers.onSnapshot?.(frame.symbol, frame.payload)
    }
    if (frame.type === 'delta') {
      this.handlers.onDelta?.(frame.symbol, frame.payload)
    }
  }
}

