'use client'

import React, { useState } from 'react'
import StockChart from '@/components/stock-chart'
import StockSelector from '@/components/stock-selector'
import ModelRanking from '@/components/model-ranking'
import ModelCharts from '@/components/model-charts'
import Portfolio from '@/components/portfolio'

export default function Page() {
  const [selectedStock, setSelectedStock] = useState('FPT')
  const [stocks] = useState(['FPT', 'SSI', 'VCB', 'VHM', 'HPG', 'GAS', 'MSN', 'MWG', 'GVR', 'VIC'])

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-background/95 text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
                <span className="text-lg font-bold text-white">📈</span>
              </div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
                Stock Terminal
              </h1>
            </div>
            <div className="text-sm text-muted-foreground">Real-time Kafka Feed</div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left Column - Chart & Portfolio */}
          <div className="lg:col-span-2 space-y-6">
            <StockSelector 
              stocks={stocks}
              selectedStock={selectedStock}
              onSelectStock={setSelectedStock}
            />
            <StockChart stock={selectedStock} />
            <Portfolio stocks={stocks} compact={true} />
          </div>

          {/* Right Column - Rankings & Charts */}
          <div className="space-y-6">
            <ModelRanking stocks={stocks} />
            <ModelCharts />
          </div>
        </div>
      </main>
    </div>
  )
}
