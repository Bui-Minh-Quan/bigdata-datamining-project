'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface ModelRankingProps {
  stocks: string[]
}

interface ModelData {
  id: string
  name: string
  symbol: string
  investment: number
  currentValue: number
  changePercent: number
}

export default function ModelRanking({ stocks }: ModelRankingProps) {
  const [models, setModels] = useState<ModelData[]>([])

  useEffect(() => {
    const initialModels = stocks.map((stock, index) => ({
      id: stock,
      name: `Model ${stock}`,
      symbol: stock,
      investment: 100000 + Math.random() * 900000,
      currentValue: 100000 + Math.random() * 900000,
      changePercent: (Math.random() - 0.5) * 10,
    }))
    setModels(initialModels.sort((a, b) => b.changePercent - a.changePercent))

    // Simulate real-time updates
    const interval = setInterval(() => {
      setModels((prev) =>
        prev
          .map((model) => ({
            ...model,
            currentValue: model.currentValue + (Math.random() - 0.5) * 5000,
            changePercent: model.changePercent + (Math.random() - 0.5) * 0.5,
          }))
          .sort((a, b) => b.changePercent - a.changePercent)
      )
    }, 3000)

    return () => clearInterval(interval)
  }, [stocks])

  return (
    <Card className="border-border/40 bg-card/50 backdrop-blur">
      <CardHeader>
        <CardTitle>Model Rankings</CardTitle>
        <CardDescription>Profit/Loss Status</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {models.map((model, index) => (
          <div
            key={model.id}
            className="group relative rounded-lg border border-border/20 bg-background/50 p-3 transition-all duration-300 hover:border-primary/50 hover:bg-background/80 hover:shadow-lg hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-2"
          >
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-purple-600 text-xs font-bold text-white">
                    {index + 1}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">{model.symbol}</p>
                    <p className="text-xs text-muted-foreground">{model.name}</p>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold">{model.currentValue.toLocaleString('vi-VN', { maximumFractionDigits: 0 })}đ</p>
                <div
                  className={`flex items-center justify-end gap-1 text-xs font-bold animate-pulse transition-all duration-500 ${
                    model.changePercent > 0 ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {model.changePercent > 0 ? (
                    <TrendingUp className="h-4 w-4" />
                  ) : (
                    <TrendingDown className="h-4 w-4" />
                  )}
                  {model.changePercent > 0 ? '+' : ''}
                  {model.changePercent.toFixed(2)}%
                </div>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
