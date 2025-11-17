"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useKafkaStream } from "@/lib/hooks/useKafkaStream"

/**
 * Component demo để test Kafka streaming
 * 
 * Usage:
 * Import component này vào page để xem realtime data từ Kafka
 */
export function KafkaStreamDemo() {
  const { data, isConnected, error, reconnect, clearData, latestMessage } = useKafkaStream({
    wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/stock-news',
    autoReconnect: true,
    reconnectDelay: 3000,
    maxReconnectAttempts: 5
  })

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header với status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>📊 Stock News Live Stream</span>
            <div className="flex items-center gap-2">
              <Badge variant={isConnected ? "default" : "destructive"}>
                {isConnected ? "🟢 Connected" : "🔴 Disconnected"}
              </Badge>
              {error && (
                <Badge variant="destructive">Error: {error}</Badge>
              )}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold">{data.length}</div>
              <div className="text-sm text-muted-foreground">Total Messages</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">
                {latestMessage ? "✓" : "-"}
              </div>
              <div className="text-sm text-muted-foreground">Latest Message</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">
                {isConnected ? "Live" : "Offline"}
              </div>
              <div className="text-sm text-muted-foreground">Status</div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <Button onClick={reconnect} variant="outline" size="sm">
              🔄 Reconnect
            </Button>
            <Button onClick={clearData} variant="outline" size="sm">
              🗑️ Clear Data
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Latest Message */}
      {latestMessage && (
        <Card className="border-green-500 border-2">
          <CardHeader>
            <CardTitle className="text-lg">🆕 Latest Message</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-start justify-between">
                <h3 className="font-semibold text-lg">{latestMessage.title}</h3>
                <Badge>{latestMessage.stockCodes || "No Stock"}</Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                {latestMessage.description}
              </p>
              <div className="text-xs text-muted-foreground">
                📅 {new Date(latestMessage.date).toLocaleString('vi-VN')}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Message List */}
      <Card>
        <CardHeader>
          <CardTitle>📰 Recent Messages ({data.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 max-h-[600px] overflow-y-auto">
            {data.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                Waiting for messages...
              </div>
            ) : (
              data.slice().reverse().map((item, idx) => (
                <Card key={`${item.postID}-${idx}`} className="hover:bg-accent transition-colors">
                  <CardContent className="p-4">
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-medium">{item.title}</h4>
                        {item.stockCodes && (
                          <Badge variant="secondary" className="shrink-0">
                            {item.stockCodes}
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {item.description}
                      </p>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>ID: {item.postID}</span>
                        <span>{new Date(item.date).toLocaleString('vi-VN')}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
