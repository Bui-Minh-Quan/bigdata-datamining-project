'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { X } from 'lucide-react'

interface UserPost {
  id: string
  author: string
  avatar: string
  content: string
  timestamp: string
  isNew?: boolean
}

export default function ModelCharts() {
  const [posts, setPosts] = useState<UserPost[]>([
    {
      id: '1',
      author: 'Trader Alpha',
      avatar: '👨‍💼',
      content: 'FPT looking strong, breaking resistance at 78k',
      timestamp: '2 mins ago',
    },
    {
      id: '2',
      author: 'Market Observer',
      avatar: '📊',
      content: 'VCB consolidation phase, watch for volume spike',
      timestamp: '5 mins ago',
    },
  ])

  useEffect(() => {
    const interval = setInterval(() => {
      const newPost: UserPost = {
        id: Math.random().toString(),
        author: ['Trader Alpha', 'Market Observer', 'Tech Analyst'][Math.floor(Math.random() * 3)],
        avatar: ['👨‍💼', '📊', '🔍'][Math.floor(Math.random() * 3)],
        content: [
          'Strong momentum detected',
          'Volume increasing',
          'Support holding strong',
          'Breakout imminent',
        ][Math.floor(Math.random() * 4)],
        timestamp: 'now',
        isNew: true,
      }

      setPosts((prev) => [newPost, ...prev.slice(0, 4)])

      // Remove "new" flag after animation
      setTimeout(() => {
        setPosts((prev) =>
          prev.map((p) => (p.id === newPost.id ? { ...p, isNew: false } : p))
        )
      }, 1000)
    }, 8000)

    return () => clearInterval(interval)
  }, [])

  return (
    <Card className="border-border/40 bg-card/50 backdrop-blur max-h-100 overflow-hidden flex flex-col">
      <CardHeader>
        <CardTitle>Model Posts</CardTitle>
        <CardDescription>Real-time user updates</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 overflow-y-auto flex-1">
        {posts.map((post) => (
          <div
            key={post.id}
            className={`relative rounded-lg border border-border/20 bg-background/50 p-3 transition-all duration-500 ${post.isNew
              ? 'animate-in zoom-in-50 slide-in-from-top-4 shadow-lg ring-2 ring-primary/50'
              : 'animate-out'
              } group hover:border-primary/50 hover:bg-background/80`}
          >
            <div className="flex gap-2 pr-6">
              <span className="text-xl">{post.avatar}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-primary">{post.author}</p>
                <p className="text-xs text-muted-foreground break-words">{post.content}</p>
                <p className="text-xs text-muted-foreground mt-1">{post.timestamp}</p>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
