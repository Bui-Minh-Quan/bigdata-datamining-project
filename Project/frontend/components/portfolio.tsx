'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface TradeRecord {
  id: string
  symbol: string
  type: 'BUY' | 'SELL'
  quantity: number
  price: number
  timestamp: string
  pnl?: number
}

interface PortfolioProps {
  stocks: string[]
  compact?: boolean
}

export default function Portfolio({ stocks, compact = false }: PortfolioProps) {
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [currentPage, setCurrentPage] = useState(0)

  useEffect(() => {
    const initialTrades: TradeRecord[] = stocks.flatMap((stock) =>
      Array.from({ length: 3 }, (_, i) => ({
        id: `${stock}-${i}`,
        symbol: stock,
        type: (Math.random() > 0.5 ? 'BUY' : 'SELL') as 'BUY' | 'SELL',
        quantity: Math.floor(Math.random() * 1000) + 100,
        price: 50 + Math.random() * 100,
        timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
        pnl: Math.random() > 0.5 ? Math.random() * 50000 : -Math.random() * 50000,
      }))
    )
    setTrades(initialTrades.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()))

    // Simulate new trades
    const interval = setInterval(() => {
      const newTrade: TradeRecord = {
        id: Math.random().toString(),
        symbol: stocks[Math.floor(Math.random() * stocks.length)],
        type: (Math.random() > 0.5 ? 'BUY' : 'SELL') as 'BUY' | 'SELL',
        quantity: Math.floor(Math.random() * 1000) + 100,
        price: 50 + Math.random() * 100,
        timestamp: new Date().toISOString(),
        pnl: Math.random() > 0.5 ? Math.random() * 50000 : -Math.random() * 50000,
      }
      setTrades((prev) => [newTrade, ...prev])
    }, 10000)

    return () => clearInterval(interval)
  }, [stocks])

  const itemsPerPage = 5
  const totalPages = Math.ceil(trades.length / itemsPerPage)
  const paginatedTrades = trades.slice(
    currentPage * itemsPerPage,
    (currentPage + 1) * itemsPerPage
  )

  return (
    <Card className="border-border/40 bg-card/50 backdrop-blur">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Portfolio History</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 mb-3 max-h-screen overflow-y-auto">
          {paginatedTrades.map((trade) => (
            <div
              key={trade.id}
              className="group rounded-lg border border-border/20 bg-background/50 transition-all duration-300 hover:border-primary/50 hover:bg-background/80 animate-in fade-in slide-in-from-left-4 p-2"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1">
                    <div className="h-5 w-5 flex-shrink-0 rounded-lg bg-gradient-to-br from-primary to-purple-600 text-white font-bold text-xs flex items-center justify-center">
                      {trade.symbol[0]}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold truncate">
                        {trade.symbol}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(trade.timestamp).toLocaleDateString('vi-VN')}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <span
                    className={`inline-block rounded-full text-xs font-bold px-2 py-0.5 ${trade.type === 'BUY'
                      ? 'bg-green-500/20 text-green-600'
                      : 'bg-red-500/20 text-red-600'
                      }`}
                  >
                    {trade.type}
                  </span>
                  {trade.pnl && (
                    <p
                      className={`text-xs font-bold animate-pulse ${trade.pnl > 0 ? 'text-green-500' : 'text-red-500'
                        }`}
                    >
                      {trade.pnl > 0 ? '+' : ''}{(trade.pnl / 1000).toFixed(0)}K
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border/20 pt-2 gap-2">
            <span className="text-xs text-muted-foreground">
              {currentPage + 1}/{totalPages}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
                disabled={currentPage === 0}
                className="h-6 w-6 p-0"
              >
                <ChevronLeft className="h-3 w-3" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={currentPage === totalPages - 1}
                className="h-6 w-6 p-0"
              >
                <ChevronRight className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
