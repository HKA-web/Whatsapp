package wa

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/big"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"

	"microservice/whatsapp/whatsmeow/internal/config"
	localstore "microservice/whatsapp/whatsmeow/internal/store"
	"microservice/whatsapp/whatsmeow/internal/webhook"
)

const (
	StatusStarting   = "STARTING"
	StatusScanQRCode = "SCAN_QR_CODE"
	StatusWorking    = "WORKING"
	StatusFailed     = "FAILED"
	StatusStopped    = "STOPPED"
)

type Session struct {
	Name      string
	Status    string
	Client    *whatsmeow.Client
	QR        string
	LatestQR  string
	User      map[string]any
	UpdatedAt time.Time
	IsStopped bool
}

type Manager struct {
	cfg       *config.Config
	container *sqlstore.Container
	local     *localstore.LocalStore
	wh        *webhook.Client

	mu       sync.RWMutex
	sessions map[string]*Session

	locksMu  sync.Mutex
	jidLocks map[string]*sync.Mutex
}

func NewManager(cfg *config.Config, wh *webhook.Client) (*Manager, error) {
	dbLog := waLog.Stdout("WhatsmeowDB", "WARN", true)
	container, err := sqlstore.New(context.Background(), "postgres", cfg.PostgresDSN, dbLog)
	if err != nil {
		return nil, fmt.Errorf("gagal koneksi PostgreSQL sqlstore: %w", err)
	}

	m := &Manager{
		cfg:       cfg,
		container: container,
		local:     localstore.NewLocalStore(cfg.SessionsDir),
		wh:        wh,
		sessions:  make(map[string]*Session),
		jidLocks:  make(map[string]*sync.Mutex),
	}
	return m, nil
}

func (m *Manager) getJIDLock(jid string) *sync.Mutex {
	m.locksMu.Lock()
	defer m.locksMu.Unlock()
	lk, ok := m.jidLocks[jid]
	if !ok {
		lk = &sync.Mutex{}
		m.jidLocks[jid] = lk
	}
	return lk
}

func (m *Manager) InitFromDB() {
	devices, err := m.container.GetAllDevices(context.Background())
	if err != nil {
		log.Printf("[Auto-Start] Gagal membaca device dari PostgreSQL: %v", err)
		return
	}

	mappings := m.local.GetAllSessionMappings()
	jidToName := make(map[string]string)
	for name, jidStr := range mappings {
		jidToName[jidStr] = name
	}

	started := make(map[string]bool)
	for _, dev := range devices {
		if dev.ID == nil {
			continue
		}
		sessionName := jidToName[dev.ID.String()]
		if sessionName == "" {
			sessionName = dev.ID.User
		}
		if started[sessionName] {
			continue
		}
		started[sessionName] = true
		log.Printf("[Auto-Start] Memuat sesi tersimpan dari PostgreSQL: %s (%s)...", sessionName, dev.ID.String())
		if _, err := m.StartSession(sessionName); err != nil {
			log.Printf("[Auto-Start] Gagal memulai sesi %s: %v", sessionName, err)
		}
		time.Sleep(1 * time.Second)
	}
}

func (m *Manager) StartSession(sessionName string) (*Session, error) {
	sessionName = strings.TrimSpace(sessionName)
	if sessionName == "" {
		return nil, fmt.Errorf("nama sesi wajib diisi")
	}

	m.mu.Lock()
	if existing, ok := m.sessions[sessionName]; ok {
		if existing.Status == StatusWorking || existing.Status == StatusScanQRCode || existing.Status == StatusStarting {
			m.mu.Unlock()
			return existing, nil
		}
		if existing.Client != nil {
			existing.Client.Disconnect()
		}
	}

	sess := &Session{
		Name:      sessionName,
		Status:    StatusStarting,
		UpdatedAt: time.Now(),
	}
	m.sessions[sessionName] = sess
	m.mu.Unlock()

	// Cari device di PostgreSQL berdasarkan session_map atau user ID
	devices, err := m.container.GetAllDevices(context.Background())
	if err != nil {
		return nil, err
	}

	var targetDev = m.container.NewDevice()
	mappedJID := m.local.GetSessionMapping(sessionName)
	for _, dev := range devices {
		if dev.ID == nil {
			continue
		}
		if (mappedJID != "" && dev.ID.String() == mappedJID) || dev.ID.User == sessionName {
			targetDev = dev
			break
		}
	}

	clientLog := waLog.Stdout("Whatsmeow", "WARN", true)
	client := whatsmeow.NewClient(targetDev, clientLog)
	sess.Client = client

	client.AddEventHandler(func(evt any) {
		m.handleEvent(sess, evt)
	})

	if client.Store.ID == nil {
		qrChan, err := client.GetQRChannel(context.Background())
		if err != nil {
			sess.Status = StatusFailed
			return nil, fmt.Errorf("gagal inisialisasi QR channel: %w", err)
		}
		if err := client.Connect(); err != nil {
			sess.Status = StatusFailed
			return nil, fmt.Errorf("gagal connect WhatsApp: %w", err)
		}
		go func() {
			for evt := range qrChan {
				if evt.Event == "code" {
					m.mu.Lock()
					sess.Status = StatusScanQRCode
					sess.QR = evt.Code
					sess.LatestQR = evt.Code
					sess.UpdatedAt = time.Now()
					m.mu.Unlock()
					log.Printf("[%s] QR Code siap di-scan.", sessionName)
					m.wh.Send(map[string]any{
						"event":   "session.status",
						"session": sessionName,
						"status":  StatusScanQRCode,
						"data":    map[string]any{"qr": evt.Code},
					})
					m.wh.Send(map[string]any{
						"event":   "connection.qrcode",
						"session": sessionName,
						"data":    map[string]any{"qr": evt.Code},
					})
				} else if evt.Event == "timeout" {
					log.Printf("[%s] QR Code timeout.", sessionName)
				}
			}
		}()
	} else {
		if err := client.Connect(); err != nil {
			sess.Status = StatusFailed
			return nil, fmt.Errorf("gagal reconnect WhatsApp: %w", err)
		}
	}

	return sess, nil
}

func (m *Manager) handleEvent(sess *Session, evt any) {
	switch v := evt.(type) {
	case *events.PairSuccess:
		if v.ID.User != "" {
			m.local.SaveSessionMapping(sess.Name, v.ID.String())
		}
	case *events.Connected:
		m.mu.Lock()
		sess.Status = StatusWorking
		sess.QR = ""
		sess.LatestQR = ""
		sess.UpdatedAt = time.Now()
		if sess.Client.Store.ID != nil {
			m.local.SaveSessionMapping(sess.Name, sess.Client.Store.ID.String())
			sess.User = map[string]any{
				"id":   sess.Client.Store.ID.String(),
				"name": sess.Client.Store.PushName,
			}
		}
		userCopy := sess.User
		m.mu.Unlock()

		log.Printf("[%s] WhatsApp (whatsmeow) terhubung!", sess.Name)
		m.wh.Send(map[string]any{
			"event":   "session.status",
			"session": sess.Name,
			"status":  StatusWorking,
			"data":    map[string]any{"user": userCopy},
		})
		m.wh.Send(map[string]any{
			"event":   "connection.open",
			"session": sess.Name,
			"data":    map[string]any{"user": userCopy},
		})
	case *events.Disconnected:
		m.mu.Lock()
		if !sess.IsStopped {
			sess.Status = StatusFailed
		}
		sess.UpdatedAt = time.Now()
		m.mu.Unlock()
		m.wh.Send(map[string]any{
			"event":   "session.status",
			"session": sess.Name,
			"status":  sess.Status,
		})
		m.wh.Send(map[string]any{
			"event":   "connection.close",
			"session": sess.Name,
			"data":    map[string]any{"reason": "disconnected"},
		})
	case *events.LoggedOut:
		m.mu.Lock()
		sess.Status = StatusStopped
		sess.IsStopped = true
		sess.UpdatedAt = time.Now()
		m.mu.Unlock()
		m.local.DeleteSessionMapping(sess.Name)
		m.wh.Send(map[string]any{
			"event":   "session.status",
			"session": sess.Name,
			"status":  StatusStopped,
		})
		m.wh.Send(map[string]any{
			"event":   "connection.close",
			"session": sess.Name,
			"data":    map[string]any{"reason": "logged_out"},
		})
	case *events.Message:
		m.handleIncomingMessage(sess, v)
	}
}

func (m *Manager) handleIncomingMessage(sess *Session, msg *events.Message) {
	if msg == nil || msg.Message == nil {
		return
	}

	remoteJID := msg.Info.Chat.ToNonAD().String()
	senderJID := msg.Info.Sender.ToNonAD().String()
	participant := ""
	if msg.Info.IsGroup {
		participant = senderJID
	}

	// Abaikan status@broadcast dan newsletter
	if msg.Info.Chat.Server == types.BroadcastServer || msg.Info.Chat.Server == types.NewsletterServer {
		return
	}

	// Simpan ke local store untuk .rvo dan reply quote
	m.local.SaveMessage(localstore.MessageKey{
		ID:          msg.Info.ID,
		RemoteJID:   remoteJID,
		Participant: participant,
		FromMe:      msg.Info.IsFromMe,
	}, msg.Message)

	// Mapping LID <-> PN jika tersedia
	if msg.Info.Sender.Server == types.HiddenUserServer && msg.Info.SenderAlt.User != "" {
		pnJID := msg.Info.SenderAlt.ToNonAD().String()
		m.local.SaveLIDMapping(senderJID, pnJID)
	}

	if msg.Info.IsFromMe {
		return
	}

	// Tentukan sender yang ramah untuk Django
	effectiveSender := remoteJID
	if !msg.Info.IsGroup {
		if msg.Info.SenderAlt.User != "" && msg.Info.SenderAlt.Server == types.DefaultUserServer {
			effectiveSender = msg.Info.SenderAlt.ToNonAD().String()
		} else {
			effectiveSender = m.local.ResolveLID(remoteJID)
		}
	}

	unwrapped := localstore.UnwrapMessage(msg.Message)
	text, msgType := extractTextAndType(unwrapped)

	// Konversi waE2E.Message menjadi map JSON agar kompatibel dengan parser Django (.rvo contextInfo, dll)
	var msgMap map[string]any
	if rawJSON, err := (protojson.MarshalOptions{UseProtoNames: false}).Marshal(msg.Message); err == nil {
		_ = json.Unmarshal(rawJSON, &msgMap)
	}

	rawKey := map[string]any{
		"id":        msg.Info.ID,
		"remoteJid": remoteJID,
		"fromMe":    msg.Info.IsFromMe,
	}
	if participant != "" {
		rawKey["participant"] = participant
	}
	if msg.Info.SenderAlt.User != "" && msg.Info.SenderAlt.Server == types.DefaultUserServer {
		rawKey["senderPn"] = msg.Info.SenderAlt.ToNonAD().String()
	}

	rawObj := map[string]any{
		"key":              rawKey,
		"message":          msgMap,
		"messageTimestamp": msg.Info.Timestamp.Unix(),
		"pushName":         msg.Info.PushName,
	}

	payload := map[string]any{
		"event":      "messages.upsert",
		"waha_event": "message",
		"session":    sess.Name,
		"payload": map[string]any{
			"id":        msg.Info.ID,
			"from":      effectiveSender,
			"pushName":  fallbackString(msg.Info.PushName, "Unknown"),
			"body":      text,
			"type":      msgType,
			"timestamp": msg.Info.Timestamp.Unix(),
			"raw":       rawObj,
		},
		"data": map[string]any{
			"messages": []any{rawObj},
		},
		"metadata": map[string]any{
			"phone":        sess.Name,
			"sender":       effectiveSender,
			"push_name":    msg.Info.PushName,
			"text":         text,
			"message_type": msgType,
		},
		"from_me":      false,
		"message_id":   msg.Info.ID,
		"sender":       effectiveSender,
		"push_name":    msg.Info.PushName,
		"timestamp":    msg.Info.Timestamp.Unix(),
		"message_type": msgType,
		"text":         text,
		"raw":          rawObj,
	}

	m.wh.Send(payload)
	msgAlias := make(map[string]any, len(payload))
	for k, val := range payload {
		msgAlias[k] = val
	}
	msgAlias["event"] = "message"
	m.wh.Send(msgAlias)
}

func extractTextAndType(msg *waE2E.Message) (string, string) {
	if msg == nil {
		return "", "conversation"
	}
	switch {
	case msg.GetImageMessage() != nil:
		return msg.GetImageMessage().GetCaption(), "imageMessage"
	case msg.GetVideoMessage() != nil:
		return msg.GetVideoMessage().GetCaption(), "videoMessage"
	case msg.GetAudioMessage() != nil:
		return "", "audioMessage"
	case msg.GetDocumentMessage() != nil:
		return msg.GetDocumentMessage().GetCaption(), "documentMessage"
	case msg.GetStickerMessage() != nil:
		return "", "stickerMessage"
	case msg.GetExtendedTextMessage() != nil:
		return msg.GetExtendedTextMessage().GetText(), "extendedTextMessage"
	case msg.GetConversation() != "":
		return msg.GetConversation(), "conversation"
	default:
		return "", "conversation"
	}
}

func (m *Manager) StopSession(sessionName string) (bool, string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	sess, ok := m.sessions[strings.TrimSpace(sessionName)]
	if !ok {
		return false, "Sesi tidak ditemukan atau belum aktif."
	}
	sess.IsStopped = true
	sess.Status = StatusStopped
	sess.QR = ""
	sess.UpdatedAt = time.Now()
	if sess.Client != nil {
		sess.Client.Disconnect()
	}
	m.wh.Send(map[string]any{
		"event":   "session.status",
		"session": sess.Name,
		"status":  StatusStopped,
	})
	return true, fmt.Sprintf("Sesi %s berhasil dihentikan.", sess.Name)
}

func (m *Manager) LogoutSession(sessionName string) (bool, string) {
	m.mu.Lock()
	sess, ok := m.sessions[strings.TrimSpace(sessionName)]
	if ok {
		sess.IsStopped = true
		sess.Status = StatusStopped
		if sess.Client != nil {
			_ = sess.Client.Logout(context.Background())
			sess.Client.Disconnect()
		}
		delete(m.sessions, sess.Name)
	}
	m.mu.Unlock()
	m.local.DeleteSessionMapping(strings.TrimSpace(sessionName))
	m.wh.Send(map[string]any{
		"event":   "session.status",
		"session": strings.TrimSpace(sessionName),
		"status":  StatusStopped,
	})
	return true, fmt.Sprintf("Sesi %s berhasil logout dan dihapus.", sessionName)
}

func (m *Manager) ResolveWorkingSession(requested string) *Session {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if requested != "" {
		if s, ok := m.sessions[strings.TrimSpace(requested)]; ok && s.Status == StatusWorking && s.Client != nil {
			return s
		}
	}
	for _, s := range m.sessions {
		if s.Status == StatusWorking && s.Client != nil {
			return s
		}
	}
	for _, s := range m.sessions {
		return s
	}
	return nil
}

func (m *Manager) GetSession(name string) *Session {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.sessions[strings.TrimSpace(name)]
}

func (m *Manager) ListSessions() []map[string]any {
	m.mu.RLock()
	defer m.mu.RUnlock()
	list := make([]map[string]any, 0, len(m.sessions))
	for _, s := range m.sessions {
		list = append(list, map[string]any{
			"name":      s.Name,
			"status":    s.Status,
			"user":      s.User,
			"hasQr":     s.QR != "",
			"updatedAt": s.UpdatedAt.UTC().Format(time.RFC3339),
		})
	}
	return list
}

func ToJID(raw string) (types.JID, error) {
	s := strings.TrimSpace(raw)
	if s == "" {
		return types.EmptyJID, fmt.Errorf("JID kosong")
	}
	if strings.Contains(s, "@") {
		if strings.HasSuffix(s, "@c.us") {
			s = strings.TrimSuffix(s, "@c.us") + "@s.whatsapp.net"
		}
		return types.ParseJID(s)
	}
	digits := regexp.MustCompile(`\D`).ReplaceAllString(s, "")
	if strings.HasPrefix(digits, "0") {
		digits = "62" + digits[1:]
	}
	return types.NewJID(digits, types.DefaultUserServer), nil
}

var refPattern = regexp.MustCompile(`(^|\s)_+ref:[A-Za-z0-9]{4,8}_+`)

func AttachRefID(text string, forceNew bool) string {
	if text == "" {
		return text
	}
	if !forceNew && refPattern.MatchString(text) {
		return text
	}
	clean := strings.TrimSpace(refPattern.ReplaceAllString(text, ""))
	return fmt.Sprintf("%s\n\n_ref:%s_", clean, randomRef(5))
}

func randomRef(n int) string {
	const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
	b := make([]byte, n)
	for i := range b {
		idx, _ := rand.Int(rand.Reader, big.NewInt(int64(len(chars))))
		b[i] = chars[idx.Int64()]
	}
	return string(b)
}

func (m *Manager) buildContextInfo(replyTo string, targetJID types.JID) *waE2E.ContextInfo {
	if replyTo == "" {
		return nil
	}
	stored := m.local.GetMessage(replyTo)
	if stored != nil {
		ci := &waE2E.ContextInfo{
			StanzaID:      proto.String(stored.Key.ID),
			QuotedMessage: stored.ProtoMsg,
		}
		if stored.Key.Participant != "" {
			ci.Participant = proto.String(stored.Key.Participant)
		} else if !stored.Key.FromMe {
			ci.Participant = proto.String(targetJID.String())
		}
		return ci
	}
	return &waE2E.ContextInfo{
		StanzaID:      proto.String(replyTo),
		Participant:   proto.String(targetJID.String()),
		QuotedMessage: &waE2E.Message{Conversation: proto.String("")},
	}
}

func (m *Manager) simulateTyping(ctx context.Context, client *whatsmeow.Client, jid types.JID, enabled bool, delayMs int) {
	if !enabled {
		return
	}
	if delayMs < 500 {
		delayMs = 1200
	} else if delayMs > 5000 {
		delayMs = 5000
	}
	_ = client.SendChatPresence(ctx, jid, types.ChatPresenceComposing, types.ChatPresenceMediaText)
	select {
	case <-time.After(time.Duration(delayMs) * time.Millisecond):
	case <-ctx.Done():
	}
	_ = client.SendChatPresence(ctx, jid, types.ChatPresencePaused, types.ChatPresenceMediaText)
}

func (m *Manager) SendText(ctx context.Context, sess *Session, rawChatID, text, replyTo string, simTyping bool, typingDelay int, forceRef bool) (map[string]any, error) {
	jid, err := ToJID(rawChatID)
	if err != nil {
		return nil, err
	}
	textToSend := AttachRefID(text, forceRef)

	lk := m.getJIDLock(jid.String())
	lk.Lock()
	defer lk.Unlock()

	m.simulateTyping(ctx, sess.Client, jid, simTyping, typingDelay)

	var msg *waE2E.Message
	if ci := m.buildContextInfo(replyTo, jid); ci != nil {
		msg = &waE2E.Message{
			ExtendedTextMessage: &waE2E.ExtendedTextMessage{
				Text:        proto.String(textToSend),
				ContextInfo: ci,
			},
		}
	} else {
		msg = &waE2E.Message{
			Conversation: proto.String(textToSend),
		}
	}

	resp, err := sess.Client.SendMessage(ctx, jid, msg)
	if err != nil {
		return nil, err
	}
	m.local.SaveMessage(localstore.MessageKey{
		ID:        resp.ID,
		RemoteJID: jid.String(),
		FromMe:    true,
	}, msg)

	return map[string]any{
		"success":   true,
		"id":        resp.ID,
		"to":        jid.String(),
		"timestamp": resp.Timestamp.Unix(),
	}, nil
}

func fetchMediaBytes(fileURL string) ([]byte, string, error) {
	if strings.HasPrefix(fileURL, "data:") {
		parts := strings.SplitN(fileURL, ",", 2)
		if len(parts) != 2 {
			return nil, "", fmt.Errorf("format data URI tidak valid")
		}
		meta := strings.TrimPrefix(parts[0], "data:")
		mime := strings.Split(meta, ";")[0]
		b, err := base64.StdEncoding.DecodeString(parts[1])
		return b, mime, err
	}
	if strings.HasPrefix(fileURL, "http://") || strings.HasPrefix(fileURL, "https://") {
		cli := &http.Client{Timeout: 30 * time.Second}
		resp, err := cli.Get(fileURL)
		if err != nil {
			return nil, "", err
		}
		defer resp.Body.Close()
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return nil, "", fmt.Errorf("Request failed with status code %d", resp.StatusCode)
		}
		b, err := io.ReadAll(resp.Body)
		return b, resp.Header.Get("Content-Type"), err
	}
	b, err := os.ReadFile(fileURL)
	return b, "", err
}

func (m *Manager) SendImage(ctx context.Context, sess *Session, rawChatID, fileURL, caption, replyTo string, simTyping bool, typingDelay int) (map[string]any, error) {
	jid, err := ToJID(rawChatID)
	if err != nil {
		return nil, err
	}
	imgBytes, detectedMime, err := fetchMediaBytes(fileURL)
	if err != nil {
		return nil, err
	}
	if detectedMime == "" {
		detectedMime = http.DetectContentType(imgBytes)
	}

	uploaded, err := sess.Client.Upload(ctx, imgBytes, whatsmeow.MediaImage)
	if err != nil {
		return nil, fmt.Errorf("gagal upload gambar: %w", err)
	}

	finalCaption := ""
	if caption != "" {
		finalCaption = AttachRefID(caption, false)
	}

	lk := m.getJIDLock(jid.String())
	lk.Lock()
	defer lk.Unlock()

	m.simulateTyping(ctx, sess.Client, jid, simTyping, typingDelay)

	imgMsg := &waE2E.ImageMessage{
		Caption:       proto.String(finalCaption),
		Mimetype:      proto.String(detectedMime),
		URL:           proto.String(uploaded.URL),
		DirectPath:    proto.String(uploaded.DirectPath),
		MediaKey:      uploaded.MediaKey,
		FileEncSHA256: uploaded.FileEncSHA256,
		FileSHA256:    uploaded.FileSHA256,
		FileLength:    proto.Uint64(uint64(len(imgBytes))),
		ContextInfo:   m.buildContextInfo(replyTo, jid),
	}
	msg := &waE2E.Message{ImageMessage: imgMsg}

	resp, err := sess.Client.SendMessage(ctx, jid, msg)
	if err != nil {
		return nil, err
	}
	m.local.SaveMessage(localstore.MessageKey{
		ID:        resp.ID,
		RemoteJID: jid.String(),
		FromMe:    true,
	}, msg)

	return map[string]any{
		"success":   true,
		"id":        resp.ID,
		"to":        jid.String(),
		"timestamp": resp.Timestamp.Unix(),
	}, nil
}

func (m *Manager) SendFile(ctx context.Context, sess *Session, rawChatID, fileURL, filename, mimetype, caption, replyTo string) (map[string]any, error) {
	jid, err := ToJID(rawChatID)
	if err != nil {
		return nil, err
	}
	fileBytes, detectedMime, err := fetchMediaBytes(fileURL)
	if err != nil {
		return nil, err
	}
	if mimetype == "" {
		if detectedMime != "" {
			mimetype = detectedMime
		} else {
			mimetype = "application/octet-stream"
		}
	}
	if filename == "" {
		filename = "document"
	}

	uploaded, err := sess.Client.Upload(ctx, fileBytes, whatsmeow.MediaDocument)
	if err != nil {
		return nil, fmt.Errorf("gagal upload dokumen: %w", err)
	}

	finalCaption := ""
	if caption != "" {
		finalCaption = AttachRefID(caption, false)
	}

	lk := m.getJIDLock(jid.String())
	lk.Lock()
	defer lk.Unlock()

	docMsg := &waE2E.DocumentMessage{
		Caption:       proto.String(finalCaption),
		Mimetype:      proto.String(mimetype),
		FileName:      proto.String(filename),
		URL:           proto.String(uploaded.URL),
		DirectPath:    proto.String(uploaded.DirectPath),
		MediaKey:      uploaded.MediaKey,
		FileEncSHA256: uploaded.FileEncSHA256,
		FileSHA256:    uploaded.FileSHA256,
		FileLength:    proto.Uint64(uint64(len(fileBytes))),
		ContextInfo:   m.buildContextInfo(replyTo, jid),
	}
	msg := &waE2E.Message{DocumentMessage: docMsg}

	resp, err := sess.Client.SendMessage(ctx, jid, msg)
	if err != nil {
		return nil, err
	}
	m.local.SaveMessage(localstore.MessageKey{
		ID:        resp.ID,
		RemoteJID: jid.String(),
		FromMe:    true,
	}, msg)

	return map[string]any{
		"success":   true,
		"id":        resp.ID,
		"to":        jid.String(),
		"timestamp": resp.Timestamp.Unix(),
	}, nil
}

func (m *Manager) DownloadMedia(ctx context.Context, sess *Session, messageID, chatID, participant string, rawMsg map[string]any) (map[string]any, error) {
	var targetProto *waE2E.Message

	if messageID != "" {
		if stored := m.local.GetMessage(messageID); stored != nil && stored.ProtoMsg != nil && localstore.HasMediaKeys(stored.ProtoMsg) {
			targetProto = stored.ProtoMsg
		}
	}

	if targetProto == nil && rawMsg != nil {
		if innerRaw, ok := rawMsg["message"]; ok {
			if b, err := json.Marshal(innerRaw); err == nil {
				var pm waE2E.Message
				if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal(b, &pm); err == nil && localstore.HasMediaKeys(&pm) {
					targetProto = &pm
				}
			}
		}
	}

	if targetProto == nil && chatID != "" {
		jid, err := ToJID(chatID)
		searchChat := chatID
		if err == nil {
			searchChat = jid.String()
		}
		if found := m.local.FindLatestMediaMessage(searchChat, participant); found != nil {
			targetProto = found.ProtoMsg
		}
	}

	if targetProto == nil || !localstore.HasMediaKeys(targetProto) {
		return nil, fmt.Errorf("Kunci enkripsi media tidak ditemukan (mediaKey / url kosong). Pastikan pesan sekali lihat dikirim ke bot / grup saat bot sedang aktif agar bot dapat mencatat kunci dekripsinya.")
	}

	unwrapped := localstore.UnwrapMessage(targetProto)
	var downloadable whatsmeow.DownloadableMessage
	var mimetype, mediaType, fileName string

	switch {
	case unwrapped.GetImageMessage() != nil:
		im := unwrapped.GetImageMessage()
		downloadable = im
		mimetype = fallbackString(im.GetMimetype(), "image/jpeg")
		mediaType = "image"
	case unwrapped.GetVideoMessage() != nil:
		vm := unwrapped.GetVideoMessage()
		downloadable = vm
		mimetype = fallbackString(vm.GetMimetype(), "video/mp4")
		mediaType = "video"
	case unwrapped.GetAudioMessage() != nil:
		am := unwrapped.GetAudioMessage()
		downloadable = am
		mimetype = fallbackString(am.GetMimetype(), "audio/ogg")
		mediaType = "audio"
	case unwrapped.GetDocumentMessage() != nil:
		dm := unwrapped.GetDocumentMessage()
		downloadable = dm
		mimetype = fallbackString(dm.GetMimetype(), "application/octet-stream")
		mediaType = "file"
		fileName = dm.GetFileName()
	case unwrapped.GetStickerMessage() != nil:
		sm := unwrapped.GetStickerMessage()
		downloadable = sm
		mimetype = fallbackString(sm.GetMimetype(), "image/webp")
		mediaType = "image"
	default:
		return nil, fmt.Errorf("pesan tidak mengandung media yang dapat diunduh")
	}

	data, err := sess.Client.Download(ctx, downloadable)
	if err != nil {
		return nil, fmt.Errorf("gagal mendekripsi media: %w", err)
	}

	ext := "bin"
	if parts := strings.Split(mimetype, "/"); len(parts) == 2 {
		ext = strings.Split(parts[1], ";")[0]
	}
	if fileName == "" {
		fileName = fmt.Sprintf("view_once_%d.%s", time.Now().UnixMilli(), ext)
	}

	return map[string]any{
		"success":  true,
		"type":     mediaType,
		"mimetype": mimetype,
		"filename": fileName,
		"data":     fmt.Sprintf("data:%s;base64,%s", mimetype, base64.StdEncoding.EncodeToString(data)),
		"size":     len(data),
	}, nil
}

func fallbackString(val, def string) string {
	if strings.TrimSpace(val) == "" {
		return def
	}
	return val
}
