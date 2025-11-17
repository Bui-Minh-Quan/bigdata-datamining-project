"use client"

import { useEffect, useState, useCallback, useRef } from 'react'

interface StockNews {
    postID: string
    stockCodes: string
    title: string
    description: string
    date: string
}

interface UseKafkaStreamOptions {
    wsUrl?: string
    autoReconnect?: boolean
    reconnectDelay?: number
    maxReconnectAttempts?: number
}

interface UseKafkaStreamReturn {
    data: StockNews[]
    isConnected: boolean
    error: string | null
    reconnect: () => void
    clearData: () => void
    latestMessage: StockNews | null
}

/**
 * Custom hook để kết nối WebSocket và nhận data từ Kafka
 * 
 * @example
 * ```tsx
 * function Dashboard() {
 *   const { data, isConnected, latestMessage } = useKafkaStream({
 *     wsUrl: 'ws://localhost:8000/ws/stock-news',
 *     autoReconnect: true
 *   })
 * 
 *   return (
 *     <div>
 *       <div>Status: {isConnected ? '🟢 Live' : '🔴 Disconnected'}</div>
 *       {data.map((item, idx) => (
 *         <div key={idx}>{item.title}</div>
 *       ))}
 *     </div>
 *   )
 * }
 * ```
 */
export function useKafkaStream(options: UseKafkaStreamOptions = {}): UseKafkaStreamReturn {
    const {
        wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/stock-news',
        autoReconnect = true,
        reconnectDelay = 3000,
        maxReconnectAttempts = 5
    } = options

    const [data, setData] = useState<StockNews[]>([])
    const [latestMessage, setLatestMessage] = useState<StockNews | null>(null)
    const [isConnected, setIsConnected] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const wsRef = useRef<WebSocket | null>(null)
    const reconnectAttemptsRef = useRef(0)
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined)

    const connect = useCallback(() => {
        try {
            console.log('🔄 Connecting to WebSocket:', wsUrl)

            const ws = new WebSocket(wsUrl)
            wsRef.current = ws

            ws.onopen = () => {
                console.log('✅ WebSocket connected')
                setIsConnected(true)
                setError(null)
                reconnectAttemptsRef.current = 0

                // Send ping every 20s to keep connection alive
                const pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping')
                    } else {
                        clearInterval(pingInterval)
                    }
                }, 20000)
            }

            ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data)

                    // Handle heartbeat/pong messages
                    if (message.type === 'heartbeat' || message.type === 'pong') {
                        return
                    }

                    // Update latest message
                    setLatestMessage(message)

                    // Add to data array (keep last 100 items)
                    setData(prev => {
                        const newData = [...prev, message]
                        return newData.slice(-100)
                    })

                    console.log('📰 Received:', message.title?.substring(0, 50) + '...')
                } catch (err) {
                    console.error('❌ Error parsing message:', err)
                }
            }

            ws.onerror = (event) => {
                console.error('❌ WebSocket error:', event)
                setError('WebSocket connection error')
            }

            ws.onclose = (event) => {
                console.log('👋 WebSocket closed:', event.code, event.reason)
                setIsConnected(false)
                wsRef.current = null

                // Auto reconnect
                if (autoReconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
                    reconnectAttemptsRef.current++
                    console.log(`🔄 Reconnecting... (${reconnectAttemptsRef.current}/${maxReconnectAttempts})`)

                    reconnectTimeoutRef.current = setTimeout(() => {
                        connect()
                    }, reconnectDelay)
                } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
                    setError('Max reconnection attempts reached')
                }
            }
        } catch (err) {
            console.error('❌ Error creating WebSocket:', err)
            setError('Failed to create WebSocket connection')
        }
    }, [wsUrl, autoReconnect, reconnectDelay, maxReconnectAttempts])

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current)
        }

        if (wsRef.current) {
            wsRef.current.close()
            wsRef.current = null
        }

        setIsConnected(false)
    }, [])

    const reconnect = useCallback(() => {
        disconnect()
        reconnectAttemptsRef.current = 0
        connect()
    }, [connect, disconnect])

    const clearData = useCallback(() => {
        setData([])
        setLatestMessage(null)
    }, [])

    // Connect on mount
    useEffect(() => {
        connect()

        return () => {
            disconnect()
        }
    }, [connect, disconnect])

    return {
        data,
        isConnected,
        error,
        reconnect,
        clearData,
        latestMessage
    }
}
