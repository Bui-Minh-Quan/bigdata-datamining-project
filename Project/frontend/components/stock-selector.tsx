'use client'

import React from 'react'
import { Button } from '@/components/ui/button'

interface StockSelectorProps {
  stocks: string[]
  selectedStock: string
  onSelectStock: (stock: string) => void
}

export default function StockSelector({
  stocks,
  selectedStock,
  onSelectStock,
}: StockSelectorProps) {
  return (
    <div className="rounded-xl border border-border/40 bg-card/50 backdrop-blur p-4">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Select Stock
        </h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {stocks.map((stock) => (
          <Button
            key={stock}
            onClick={() => onSelectStock(stock)}
            variant={selectedStock === stock ? 'default' : 'outline'}
            className={`font-semibold transition-all duration-200 ${
              selectedStock === stock
                ? 'bg-gradient-to-r from-primary to-purple-600 hover:from-primary/90 hover:to-purple-600/90'
                : 'hover:border-primary/50'
            }`}
          >
            {stock}
          </Button>
        ))}
      </div>
    </div>
  )
}
