package webhook

import (
	"bytes"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Client struct {
	httpURL string
	wsURL   string
	mu      sync.Mutex
	conn    *websocket.Conn
	httpCli *http.Client
}

func NewClient(webhookRaw string) *Client {
	raw := strings.TrimSpace(webhookRaw)
	if raw == "" {
		raw = "http://127.0.0.1:8008/whatsapp/webhook/"
	}
	lower := strings.ToLower(raw)
	var wsURL, httpURL string
	if strings.HasPrefix(lower, "ws://") || strings.HasPrefix(lower, "wss://") {
		wsURL = raw
		httpURL = strings.Replace(raw, "wss://", "https://", 1)
		httpURL = strings.Replace(httpURL, "ws://", "http://", 1)
		httpURL = strings.TrimSuffix(httpURL, "/")
		httpURL = strings.TrimSuffix(httpURL, "/ws/whatsapp/webhook") + "/whatsapp/webhook/"
	} else {
		httpURL = raw
		wsURL = strings.Replace(raw, "https://", "wss://", 1)
		wsURL = strings.Replace(wsURL, "http://", "ws://", 1)
		wsURL = strings.TrimSuffix(wsURL, "/")
		wsURL = strings.TrimSuffix(wsURL, "/whatsapp/webhook") + "/ws/whatsapp/webhook/"
	}

	c := &Client{
		httpURL: httpURL,
		wsURL:   wsURL,
		httpCli: &http.Client{Timeout: 10 * time.Second},
	}
	go c.connectLoop()
	return c
}

func (c *Client) connectLoop() {
	for {
		c.mu.Lock()
		connected := c.conn != nil
		c.mu.Unlock()

		if !connected && strings.HasPrefix(c.wsURL, "ws") {
			conn, _, err := websocket.DefaultDialer.Dial(c.wsURL, nil)
			if err == nil {
				c.mu.Lock()
				c.conn = conn
				c.mu.Unlock()
				log.Printf("[Webhook] Connected to Django WebSocket at %s", c.wsURL)

				// Read loop to detect close
				for {
					if _, _, err := conn.ReadMessage(); err != nil {
						c.mu.Lock()
						if c.conn == conn {
							c.conn.Close()
							c.conn = nil
						}
						c.mu.Unlock()
						break
					}
				}
			}
		}
		time.Sleep(3 * time.Second)
	}
}

func (c *Client) Send(payload any) bool {
	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[Webhook] Marshal error: %v", err)
		return false
	}

	c.mu.Lock()
	conn := c.conn
	if conn != nil {
		err := conn.WriteMessage(websocket.TextMessage, data)
		if err == nil {
			c.mu.Unlock()
			return true
		}
		log.Printf("[Webhook] WS write error: %v", err)
		conn.Close()
		c.conn = nil
	}
	c.mu.Unlock()

	if c.httpURL != "" && strings.HasPrefix(c.httpURL, "http") {
		resp, err := c.httpCli.Post(c.httpURL, "application/json", bytes.NewReader(data))
		if err != nil {
			log.Printf("[Webhook] HTTP fallback error: %v", err)
			return false
		}
		resp.Body.Close()
		return resp.StatusCode >= 200 && resp.StatusCode < 300
	}
	return false
}
