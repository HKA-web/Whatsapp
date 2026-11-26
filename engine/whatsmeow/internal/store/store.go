package store

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.mau.fi/whatsmeow/proto/waE2E"
	"google.golang.org/protobuf/encoding/protojson"
)

type MessageKey struct {
	ID          string `json:"id"`
	RemoteJID   string `json:"remoteJid"`
	Participant string `json:"participant,omitempty"`
	FromMe      bool   `json:"fromMe"`
}

type StoredMessage struct {
	Key        MessageKey      `json:"key"`
	MessageRaw json.RawMessage `json:"message"`
	ProtoMsg   *waE2E.Message  `json:"-"`
}

type LocalStore struct {
	mu           sync.RWMutex
	dir          string
	messages     map[string]*StoredMessage
	order        []string
	maxSize      int
	lidMap       map[string]string
	sessionMap   map[string]string // sessionName -> deviceJID
}

func NewLocalStore(dir string) *LocalStore {
	_ = os.MkdirAll(dir, 0755)
	s := &LocalStore{
		dir:        dir,
		messages:   make(map[string]*StoredMessage),
		order:      make([]string, 0, 256),
		maxSize:    5000,
		lidMap:     make(map[string]string),
		sessionMap: make(map[string]string),
	}
	s.loadFiles()
	return s
}

func (s *LocalStore) loadFiles() {
	if data, err := os.ReadFile(filepath.Join(s.dir, "lid_map.json")); err == nil {
		_ = json.Unmarshal(data, &s.lidMap)
	}
	if data, err := os.ReadFile(filepath.Join(s.dir, "session_map.json")); err == nil {
		_ = json.Unmarshal(data, &s.sessionMap)
	}
	if data, err := os.ReadFile(filepath.Join(s.dir, "message_store.json")); err == nil {
		var disk map[string]*StoredMessage
		if err := json.Unmarshal(data, &disk); err == nil {
			for k, v := range disk {
				if v != nil && len(v.MessageRaw) > 0 {
					var pm waE2E.Message
					if err := protojson.Unmarshal(v.MessageRaw, &pm); err == nil {
						v.ProtoMsg = &pm
					}
					s.messages[k] = v
					s.order = append(s.order, k)
				}
			}
		}
	}
}

func (s *LocalStore) saveJSON(filename string, v any) {
	data, err := json.MarshalIndent(v, "", "  ")
	if err == nil {
		_ = os.WriteFile(filepath.Join(s.dir, filename), data, 0644)
	}
}

func (s *LocalStore) SaveSessionMapping(sessionName, deviceJID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sessionMap[sessionName] = deviceJID
	s.saveJSON("session_map.json", s.sessionMap)
}

func (s *LocalStore) DeleteSessionMapping(sessionName string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.sessionMap, sessionName)
	s.saveJSON("session_map.json", s.sessionMap)
}

func (s *LocalStore) GetSessionMapping(sessionName string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.sessionMap[sessionName]
}

func (s *LocalStore) GetAllSessionMappings() map[string]string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	cp := make(map[string]string, len(s.sessionMap))
	for k, v := range s.sessionMap {
		cp[k] = v
	}
	return cp
}

func (s *LocalStore) SaveLIDMapping(lid, pn string) {
	if lid == "" || pn == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lidMap[lid] = pn
	s.lidMap[pn] = lid
	s.saveJSON("lid_map.json", s.lidMap)
}

func (s *LocalStore) ResolveLID(jid string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if mapped, ok := s.lidMap[jid]; ok && mapped != "" {
		return mapped
	}
	return jid
}

func (s *LocalStore) SaveMessage(key MessageKey, msg *waE2E.Message) {
	if key.ID == "" || msg == nil {
		return
	}
	rawBytes, err := protojson.Marshal(msg)
	if err != nil {
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.messages[key.ID]; !exists {
		s.order = append(s.order, key.ID)
		if len(s.order) > s.maxSize {
			oldest := s.order[0]
			s.order = s.order[1:]
			delete(s.messages, oldest)
		}
	}
	s.messages[key.ID] = &StoredMessage{
		Key:        key,
		MessageRaw: json.RawMessage(rawBytes),
		ProtoMsg:   msg,
	}
	s.saveJSON("message_store.json", s.messages)
}

func (s *LocalStore) GetMessage(id string) *StoredMessage {
	if id == "" {
		return nil
	}
	s.mu.RLock()
	defer s.mu.RUnlock()

	if item, ok := s.messages[id]; ok {
		return item
	}
	base := strings.Split(id, "-")[0]
	for k, item := range s.messages {
		if k == id || strings.HasPrefix(k, id+"-") || (len(base) >= 8 && strings.HasPrefix(k, base)) {
			return item
		}
	}
	return nil
}

func (s *LocalStore) FindLatestMediaMessage(chatJID, participant string) *StoredMessage {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for i := len(s.order) - 1; i >= 0; i-- {
		id := s.order[i]
		item := s.messages[id]
		if item == nil || item.ProtoMsg == nil {
			continue
		}
		if !HasMediaKeys(item.ProtoMsg) {
			continue
		}
		if chatJID == "" || item.Key.RemoteJID == chatJID {
			if participant == "" || item.Key.Participant == "" || item.Key.Participant == participant {
				return item
			}
		}
	}
	return nil
}

func UnwrapMessage(msg *waE2E.Message) *waE2E.Message {
	if msg == nil {
		return nil
	}
	cur := msg
	for i := 0; i < 5; i++ {
		switch {
		case cur.GetViewOnceMessage().GetMessage() != nil:
			cur = cur.GetViewOnceMessage().GetMessage()
		case cur.GetViewOnceMessageV2().GetMessage() != nil:
			cur = cur.GetViewOnceMessageV2().GetMessage()
		case cur.GetViewOnceMessageV2Extension().GetMessage() != nil:
			cur = cur.GetViewOnceMessageV2Extension().GetMessage()
		case cur.GetEphemeralMessage().GetMessage() != nil:
			cur = cur.GetEphemeralMessage().GetMessage()
		case cur.GetDocumentWithCaptionMessage().GetMessage() != nil:
			cur = cur.GetDocumentWithCaptionMessage().GetMessage()
		case cur.GetEditedMessage().GetMessage() != nil:
			cur = cur.GetEditedMessage().GetMessage()
		default:
			return cur
		}
	}
	return cur
}

func HasMediaKeys(msg *waE2E.Message) bool {
	unwrapped := UnwrapMessage(msg)
	if unwrapped == nil {
		return false
	}
	if img := unwrapped.GetImageMessage(); img != nil {
		return len(img.GetMediaKey()) > 0 && (img.GetURL() != "" || img.GetDirectPath() != "")
	}
	if vid := unwrapped.GetVideoMessage(); vid != nil {
		return len(vid.GetMediaKey()) > 0 && (vid.GetURL() != "" || vid.GetDirectPath() != "")
	}
	if aud := unwrapped.GetAudioMessage(); aud != nil {
		return len(aud.GetMediaKey()) > 0 && (aud.GetURL() != "" || aud.GetDirectPath() != "")
	}
	if doc := unwrapped.GetDocumentMessage(); doc != nil {
		return len(doc.GetMediaKey()) > 0 && (doc.GetURL() != "" || doc.GetDirectPath() != "")
	}
	if stk := unwrapped.GetStickerMessage(); stk != nil {
		return len(stk.GetMediaKey()) > 0 && (stk.GetURL() != "" || stk.GetDirectPath() != "")
	}
	return false
}
