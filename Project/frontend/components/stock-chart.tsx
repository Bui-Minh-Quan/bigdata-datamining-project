'use client'

import React, { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ComposedChart, Bar, ReferenceDot } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'

interface StockChartProps {
  stock: string
}

interface CandleData {
  time: string
  open: number
  high: number
  low: number
  close: number
  linePrice: number
  timestamp: number
  isActive: boolean
  isFuture?: boolean
}

// Candles close after 1 minute, x-axis extends to 3 hours + future area
export default function StockChart({ stock }: StockChartProps) {
  const [candleData, setCandleData] = useState<CandleData[]>([])
  const [highestPrice, setHighestPrice] = useState<number>(0)
  const [lowestPrice, setLowestPrice] = useState<number>(0)
  const [chartType, setChartType] = useState<'line' | 'candle'>('line')
  const [priceRange, setPriceRange] = useState<{ min: number; max: number }>({ min: 80, max: 130 })

  // Initialize candlestick data with 3 hours (36 candles of 5 minutes each) + 12 future slots
  useEffect(() => {
    const initialCandles: CandleData[] = []
    const now = Date.now()
    const basePrice = 100 + Math.random() * 50

    for (let i = 0; i < 36; i++) {
      const price = basePrice + Math.sin(i / 10) * 20 + (Math.random() - 0.5) * 5
      const minuteOffset = i * 5
      const timeString = new Date(now - (36 - i) * 5 * 60 * 1000).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })

      initialCandles.push({
        time: timeString,
        open: price + (Math.random() - 0.5) * 2,
        close: price + (Math.random() - 0.5) * 2,
        high: price + Math.abs(Math.random() * 3),
        low: price - Math.abs(Math.random() * 3),
        linePrice: price,
        timestamp: now - (36 - i) * 5 * 60 * 1000,
        isActive: false,
        isFuture: false,
      })
    }

    for (let i = 0; i < 12; i++) {
      const futureTime = new Date(now + (i + 1) * 5 * 60 * 1000).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
      initialCandles.push({
        time: futureTime,
        open: 0,
        close: 0,
        high: 0,
        low: 0,
        linePrice: 0,
        timestamp: now + (i + 1) * 5 * 60 * 1000,
        isActive: false,
        isFuture: true,
      })
    }

    setCandleData(initialCandles)
    const historicalCandles = initialCandles.slice(0, 36)
    const maxPrice = Math.max(...historicalCandles.map((c) => c.high))
    const minPrice = Math.min(...historicalCandles.map((c) => c.low))
    setPriceRange({ min: minPrice - 10, max: maxPrice + 10 })
    setHighestPrice(maxPrice)
    setLowestPrice(minPrice)
  }, [stock])

  useEffect(() => {
    const interval = setInterval(() => {
      setCandleData((prev) => {
        const updated = [...prev]
        const lastHistoricalCandle = updated.find((c) => !c.isFuture && updated.indexOf(c) === updated.findIndex((x) => !x.isFuture))

        let lastHistoricalIndex = -1
        for (let i = updated.length - 1; i >= 0; i--) {
          if (!updated[i].isFuture) {
            lastHistoricalIndex = i
            break
          }
        }

        if (lastHistoricalIndex < 0) return prev

        const lastCandle = updated[lastHistoricalIndex]
        const now = Date.now()
        const candleAge = now - lastCandle.timestamp

        if (candleAge > 60000) {
          const closedCandle = { ...lastCandle, isActive: false }
          updated[lastHistoricalIndex] = closedCandle

          const newPrice = lastCandle.close + (Math.random() - 0.5) * 3
          const newCandle: CandleData = {
            time: new Date().toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            }),
            open: newPrice,
            close: newPrice,
            high: newPrice,
            low: newPrice,
            linePrice: newPrice,
            timestamp: now,
            isActive: true,
            isFuture: false,
          }

          const futureCandles = updated.filter(c => c.isFuture)
          const historicalCandles = updated.filter(c => !c.isFuture).slice(-35)
          return [...historicalCandles, newCandle, ...futureCandles]
        } else {
          const newPrice = lastCandle.close + (Math.random() - 0.5) * 2
          updated[lastHistoricalIndex] = {
            ...lastCandle,
            close: newPrice,
            linePrice: newPrice,
            high: Math.max(lastCandle.high, newPrice),
            low: Math.min(lastCandle.low, newPrice),
            isActive: true,
          }
        }

        return updated
      })
    }, 5000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (candleData.length > 0) {
      const historicalCandles = candleData.filter(c => !c.isFuture)
      if (historicalCandles.length > 0) {
        const maxPrice = Math.max(...historicalCandles.map((c) => c.high))
        const minPrice = Math.min(...historicalCandles.map((c) => c.low))
        setHighestPrice(maxPrice)
        setLowestPrice(minPrice)
        setPriceRange({ min: minPrice - 10, max: maxPrice + 10 })
      }
    }
  }, [candleData])

  const currentPrice = candleData
    .filter(c => !c.isFuture)
    .slice(-1)[0]?.close || 0
  const previousPrice = candleData
    .filter(c => !c.isFuture)
    .slice(-2, -1)[0]?.close || currentPrice
  const priceChange = currentPrice - previousPrice
  const priceChangePercent = ((priceChange / previousPrice) * 100).toFixed(2)

  const CustomCandleStick = (props: any) => {
    const { x, y, width, height, payload } = props

    if (!payload || payload.isFuture) return null

    const open = payload.open
    const close = payload.close
    const high = payload.high
    const low = payload.low

    const yScale = height / (priceRange.max - priceRange.min)
    const xMid = x + width / 2

    const yOpen = y + height - (open - priceRange.min) * yScale
    const yClose = y + height - (close - priceRange.min) * yScale
    const yHigh = y + height - (high - priceRange.min) * yScale
    const yLow = y + height - (low - priceRange.min) * yScale

    const color = close >= open ? '#22c55e' : '#ef4444'
    const wickWidth = Math.max(1, width * 0.1)
    const bodyWidth = Math.max(width * 0.6, 4)

    return (
      <g>
        <line x1={xMid} y1={yHigh} x2={xMid} y2={yLow} stroke={color} strokeWidth={1} opacity={0.8} />
        <rect
          x={xMid - bodyWidth / 2}
          y={Math.min(yOpen, yClose)}
          width={bodyWidth}
          height={Math.abs(yClose - yOpen) || 2}
          fill={color}
          opacity={0.9}
          rx={1}
        />
      </g>
    )
  }

  const CandleTooltip = ({ active, payload }: any) => {
    if (active && payload && payload[0]) {
      const data = payload[0].payload
      if (data.isFuture) return null

      return (
        <div className="p-3 space-y-1 text-sm bg-card/90 border border-border rounded-lg backdrop-blur">
          <p className="text-muted-foreground text-xs font-medium">{data.time}</p>
          <p className="text-muted-foreground">O: {data.open.toFixed(2)}</p>
          <p className="text-green-500">H: {data.high.toFixed(2)}</p>
          <p className="text-red-500">L: {data.low.toFixed(2)}</p>
          <p className="font-semibold text-foreground">C: {data.close.toFixed(2)}</p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="space-y-4">
      <Card className="border-border/40 bg-card/50 backdrop-blur overflow-hidden">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-3xl font-bold">{stock}</CardTitle>
              <CardDescription>Real-time price feed with prediction area</CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-3xl font-bold">{currentPrice.toFixed(2)}đ</div>
                <div
                  className={`animate-pulse text-sm font-semibold transition-all duration-300 ${priceChange > 0 ? 'text-green-500' : 'text-red-500'
                    }`}
                >
                  {priceChange > 0 ? '+' : ''}{priceChangePercent}%
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setChartType('line')}
                  className={`px-3 py-1 rounded-md text-sm font-medium transition-all ${chartType === 'line'
                    ? 'bg-primary text-white'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                >
                  Line
                </button>
                <button
                  onClick={() => setChartType('candle')}
                  className={`px-3 py-1 rounded-md text-sm font-medium transition-all ${chartType === 'candle'
                    ? 'bg-primary text-white'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                >
                  Candle
                </button>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={400}>
            {chartType === 'line' ? (
              <LineChart data={candleData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="time" stroke="var(--color-muted-foreground)" tick={false} />
                <YAxis
                  stroke="var(--color-muted-foreground)"
                  domain={[priceRange.min, priceRange.max]}
                  tickCount={8}
                  width={60}
                  tickFormatter={(value) => `${value.toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--color-card)',
                    border: '1px solid var(--color-border)',
                    borderRadius: '8px',
                  }}
                  formatter={(value: any) => {
                    if (value === 0) return 'N/A'
                    return value.toFixed(2)
                  }}
                  labelFormatter={(label) => `Time: ${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="linePrice"
                  stroke="url(#gradient)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={true}
                  animationDuration={300}
                  connectNulls={true}
                  data={candleData.map(d => ({
                    ...d,
                    linePrice: d.linePrice === 0 ? null : d.linePrice
                  }))}
                />
                <defs>
                  <linearGradient id="gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-primary)" />
                    <stop offset="95%" stopColor="var(--color-primary)" opacity={0.1} />
                  </linearGradient>
                </defs>
              </LineChart>
            ) : (
              <ComposedChart data={candleData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="time" stroke="var(--color-muted-foreground)" tick={false} />
                <YAxis
                  stroke="var(--color-muted-foreground)"
                  domain={[priceRange.min, priceRange.max]}
                  tickCount={8}
                  width={60}
                  tickFormatter={(value) => `${(value + 25).toFixed(0)}`}
                />
                <Tooltip content={<CandleTooltip />} />
                <ReferenceDot x={36} r={0} stroke="var(--color-border)" strokeDasharray="5 5" />
                <Bar dataKey="open" shape={<CustomCandleStick />} />
              </ComposedChart>
            )}
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid grid-cols-4 gap-2 text-xs text-center">
        <div className="p-2 rounded-lg bg-muted/50 backdrop-blur">
          <p className="text-muted-foreground">Highest</p>
          <p className="font-semibold text-green-500">{highestPrice.toFixed(2)}đ</p>
        </div>
        <div className="p-2 rounded-lg bg-muted/50 backdrop-blur">
          <p className="text-muted-foreground">Lowest</p>
          <p className="font-semibold text-red-500">{lowestPrice.toFixed(2)}đ</p>
        </div>
        <div className="p-2 rounded-lg bg-muted/50 backdrop-blur">
          <p className="text-muted-foreground">Current</p>
          <p className="font-semibold">{currentPrice.toFixed(2)}đ</p>
        </div>
        <div className="p-2 rounded-lg bg-muted/50 backdrop-blur">
          <p className="text-muted-foreground">Candles</p>
          <p className="font-semibold">{candleData.filter(c => !c.isFuture).length}</p>
        </div>
      </div>
    </div>
  )
}
