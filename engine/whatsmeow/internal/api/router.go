package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow/types"

	"microservice/whatsapp/whatsmeow/internal/wa"
)

type Server struct {
	mgr *wa.Manager
}

func NewRouter(mgr *wa.Manager) http.Handler {
	s := &Server{mgr: mgr}
	mux := http.NewServeMux()

	mux.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/docs", http.StatusFound)
	})
	mux.HandleFunc("GET /openapi.json", s.handleOpenAPI)
	mux.HandleFunc("GET /docs", s.handleDocs)

	// 1. Session Management
	mux.HandleFunc("GET /api/sessions", s.getSessions)
	mux.HandleFunc("POST /api/sessions", s.startSession)
	mux.HandleFunc("POST /api/sessions/start", s.startSession)
	mux.HandleFunc("POST /api/sessions/stop", s.stopSession)
	mux.HandleFunc("POST /api/sessions/logout", s.logoutSession)
	mux.HandleFunc("GET /api/{session}/auth/qr", s.getQR)

	// 2. Chatting & Media
	mux.HandleFunc("POST /api/sendText", s.sendText)
	mux.HandleFunc("POST /api/sendImage", s.sendImage)
	mux.HandleFunc("POST /api/sendFile", s.sendFile)
	mux.HandleFunc("POST /api/downloadMedia", s.downloadMedia)
	mux.HandleFunc("POST /api/media/download", s.downloadMedia)

	// 3. Reply
	mux.HandleFunc("POST /api/reply", s.reply)
	mux.HandleFunc("POST /api/sendReply", s.reply)
	mux.HandleFunc("POST /api/message/reply", s.reply)
	mux.HandleFunc("POST /api/{session}/message/reply", s.reply)

	// 4. Presence & Seen
	mux.HandleFunc("POST /api/sendSeen", s.sendSeen)
	mux.HandleFunc("POST /api/startTyping", s.startTyping)
	mux.HandleFunc("POST /api/stopTyping", s.stopTyping)

	return corsMiddleware(mux)
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func readBodyAny(r *http.Request) (any, error) {
	b, err := io.ReadAll(io.LimitReader(r.Body, 100<<20))
	if err != nil {
		return nil, err
	}
	if len(strings.TrimSpace(string(b))) == 0 {
		return map[string]any{}, nil
	}
	var v any
	if err := json.Unmarshal(b, &v); err != nil {
		return nil, err
	}
	return v, nil
}

func strVal(m map[string]any, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k]; ok && v != nil {
			if s, ok := v.(string); ok && strings.TrimSpace(s) != "" {
				return strings.TrimSpace(s)
			}
		}
	}
	return ""
}

func boolVal(m map[string]any, keys ...string) bool {
	for _, k := range keys {
		if v, ok := m[k]; ok && v != nil {
			if b, ok := v.(bool); ok {
				return b
			}
		}
	}
	return false
}

func intVal(m map[string]any, keys ...string) int {
	for _, k := range keys {
		if v, ok := m[k]; ok && v != nil {
			switch n := v.(type) {
			case float64:
				return int(n)
			case int:
				return n
			}
		}
	}
	return 0
}

func (s *Server) handleOpenAPI(w http.ResponseWriter, r *http.Request) {
	candidates := []string{
		filepath.Join("..", "baileys", "openapi.json"),
		filepath.Join("whatsapp", "engine", "baileys", "openapi.json"),
	}
	for _, p := range candidates {
		if data, err := os.ReadFile(p); err == nil {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Cache-Control", "no-store")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(data)
			return
		}
	}
	writeJSON(w, http.StatusNotFound, map[string]any{"error": "openapi.json tidak ditemukan"})
}

func (s *Server) handleDocs(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(`<!DOCTYPE html>
<html>
<head>
  <title>Whatsmeow API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({ url: '/openapi.json', dom_id: '#swagger-ui' });
  </script>
</body>
</html>`))
}

func (s *Server) getSessions(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.mgr.ListSessions())
}

func (s *Server) startSession(w http.ResponseWriter, r *http.Request) {
	bodyAny, _ := readBodyAny(r)
	m, _ := bodyAny.(map[string]any)
	name := strVal(m, "name", "session")
	if name == "" {
		name = strings.TrimSpace(r.URL.Query().Get("name"))
	}
	if name == "" {
		name = strings.TrimSpace(r.URL.Query().Get("phone"))
	}
	if name == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'name' (nomor sesi) wajib diisi."})
		return
	}

	sess, err := s.mgr.StartSession(name)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": fmt.Sprintf("Gagal memulai sesi: %v", err)})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"name":    sess.Name,
		"status":  sess.Status,
		"engine":  "whatsmeow",
		"message": fmt.Sprintf("Inisialisasi sesi '%s' (whatsmeow) berhasil dimulai.", name),
	})
}

func (s *Server) stopSession(w http.ResponseWriter, r *http.Request) {
	bodyAny, _ := readBodyAny(r)
	m, _ := bodyAny.(map[string]any)
	name := strVal(m, "name", "session")
	if name == "" {
		name = strings.TrimSpace(r.URL.Query().Get("name"))
	}
	if name == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'name' wajib diisi."})
		return
	}
	ok, msg := s.mgr.StopSession(name)
	writeJSON(w, http.StatusOK, map[string]any{"success": ok, "message": msg})
}

func (s *Server) logoutSession(w http.ResponseWriter, r *http.Request) {
	bodyAny, _ := readBodyAny(r)
	m, _ := bodyAny.(map[string]any)
	name := strVal(m, "name", "session")
	if name == "" {
		name = strings.TrimSpace(r.URL.Query().Get("name"))
	}
	if name == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'name' wajib diisi."})
		return
	}
	ok, msg := s.mgr.LogoutSession(name)
	writeJSON(w, http.StatusOK, map[string]any{"success": ok, "message": msg})
}

func (s *Server) getQR(w http.ResponseWriter, r *http.Request) {
	sessionName := strings.TrimSpace(r.PathValue("session"))
	if sessionName == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Parameter sesi wajib diisi."})
		return
	}

	sess := s.mgr.GetSession(sessionName)
	if sess == nil || sess.Status == wa.StatusStopped {
		var err error
		sess, err = s.mgr.StartSession(sessionName)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
			return
		}
		for i := 0; i < 10 && sess.QR == "" && sess.LatestQR == "" && sess.Status != wa.StatusWorking; i++ {
			time.Sleep(500 * time.Millisecond)
		}
	}

	if sess.Status == wa.StatusWorking {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  sess.Status,
			"message": "Sesi sudah terhubung (tidak memerlukan scan QR).",
		})
		return
	}

	qrData := sess.QR
	if qrData == "" {
		qrData = sess.LatestQR
	}
	if qrData == "" {
		writeJSON(w, http.StatusAccepted, map[string]any{
			"status":  sess.Status,
			"message": "QR Code belum tersedia atau sedang dimuat, silakan muat ulang.",
		})
		return
	}

	if r.URL.Query().Get("format") == "json" {
		writeJSON(w, http.StatusOK, map[string]any{
			"status": sess.Status,
			"qr":     qrData,
		})
		return
	}

	png, err := qrcode.Encode(qrData, qrcode.Medium, 320)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(png)
}

func (s *Server) sendText(w http.ResponseWriter, r *http.Request) {
	bodyAny, err := readBodyAny(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JSON tidak valid."})
		return
	}

	var items []map[string]any
	isArray := false
	switch v := bodyAny.(type) {
	case []any:
		isArray = true
		for _, el := range v {
			if m, ok := el.(map[string]any); ok {
				items = append(items, m)
			}
		}
	case map[string]any:
		items = []map[string]any{v}
	}

	if len(items) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Body request tidak boleh kosong."})
		return
	}

	var allResults []map[string]any
	for _, item := range items {
		reqSession := strVal(item, "session", "_botDevice", "name")
		sess := s.mgr.ResolveWorkingSession(reqSession)
		if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum siap atau belum terhubung.", reqSession)})
			return
		}

		chatID := strVal(item, "chatId", "jid", "phone", "to", "outbox_for", "recipient")
		text := strVal(item, "text", "message")
		if chatID == "" {
			writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'chatId' atau 'outbox_for' wajib diisi."})
			return
		}
		if text == "" {
			writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'text' atau 'message' wajib diisi."})
			return
		}

		replyTo := strVal(item, "reply_to", "messageId", "quotedMsg")
		simTyping := boolVal(item, "simulateTyping")
		typingDelay := intVal(item, "typingDelay")

		res, err := s.mgr.SendText(r.Context(), sess, chatID, text, replyTo, simTyping, typingDelay, false)
		if err != nil {
			allResults = append(allResults, map[string]any{"success": false, "to": chatID, "error": err.Error()})
		} else {
			allResults = append(allResults, res)
		}
	}

	if !isArray && len(allResults) == 1 {
		single := allResults[0]
		if ok, _ := single["success"].(bool); ok {
			writeJSON(w, http.StatusOK, single)
		} else {
			writeJSON(w, http.StatusInternalServerError, single)
		}
		return
	}

	anySuccess := false
	for _, res := range allResults {
		if ok, _ := res["success"].(bool); ok {
			anySuccess = true
			break
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": anySuccess,
		"total":   len(allResults),
		"results": allResults,
	})
}

func (s *Server) reply(w http.ResponseWriter, r *http.Request) {
	bodyAny, err := readBodyAny(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JSON tidak valid."})
		return
	}
	m, ok := bodyAny.(map[string]any)
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Body harus berupa JSON object."})
		return
	}
	if sessParam := strings.TrimSpace(r.PathValue("session")); sessParam != "" {
		m["session"] = sessParam
	}

	msgID := strVal(m, "messageId", "reply_to", "replyTo", "quotedMessageId", "quotedMsg")
	if msgID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'messageId' atau 'reply_to' wajib diisi untuk melakukan reply."})
		return
	}
	m["reply_to"] = msgID

	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}
	chatID := strVal(m, "chatId", "jid", "phone", "to", "outbox_for", "recipient")
	text := strVal(m, "text", "message")
	res, err := s.mgr.SendText(r.Context(), sess, chatID, text, msgID, boolVal(m, "simulateTyping"), intVal(m, "typingDelay"), false)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"success": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (s *Server) sendImage(w http.ResponseWriter, r *http.Request) {
	bodyAny, err := readBodyAny(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JSON tidak valid."})
		return
	}
	m, _ := bodyAny.(map[string]any)
	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}

	chatID := strVal(m, "chatId", "jid", "phone", "to", "outbox_for")
	if chatID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'chatId' wajib diisi."})
		return
	}

	fileURL := strVal(m, "url", "image")
	if fileMap, ok := m["file"].(map[string]any); ok {
		if u := strVal(fileMap, "url"); u != "" {
			fileURL = u
		}
	}
	if fileURL == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'file.url' atau 'url' wajib diisi."})
		return
	}

	res, err := s.mgr.SendImage(
		r.Context(),
		sess,
		chatID,
		fileURL,
		strVal(m, "caption"),
		strVal(m, "reply_to", "messageId", "quotedMsg"),
		boolVal(m, "simulateTyping"),
		intVal(m, "typingDelay"),
	)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": fmt.Sprintf("Gagal mengirim gambar: %v", err)})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (s *Server) sendFile(w http.ResponseWriter, r *http.Request) {
	bodyAny, err := readBodyAny(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JSON tidak valid."})
		return
	}
	m, _ := bodyAny.(map[string]any)
	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}

	chatID := strVal(m, "chatId", "jid", "phone", "to", "outbox_for")
	if chatID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'chatId' wajib diisi."})
		return
	}

	fileURL := strVal(m, "url", "document")
	filename := strVal(m, "filename")
	mimetype := strVal(m, "mimetype")
	if fileMap, ok := m["file"].(map[string]any); ok {
		if u := strVal(fileMap, "url"); u != "" {
			fileURL = u
		}
		if fn := strVal(fileMap, "filename"); fn != "" {
			filename = fn
		}
		if mt := strVal(fileMap, "mimetype"); mt != "" {
			mimetype = mt
		}
	}
	if fileURL == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'file.url' atau 'url' wajib diisi."})
		return
	}

	res, err := s.mgr.SendFile(
		r.Context(),
		sess,
		chatID,
		fileURL,
		filename,
		mimetype,
		strVal(m, "caption"),
		strVal(m, "reply_to", "messageId", "quotedMsg"),
	)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": fmt.Sprintf("Gagal mengirim dokumen: %v", err)})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (s *Server) downloadMedia(w http.ResponseWriter, r *http.Request) {
	bodyAny, err := readBodyAny(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JSON tidak valid."})
		return
	}
	m, _ := bodyAny.(map[string]any)
	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}

	messageID := strVal(m, "messageId", "id")
	chatID := strVal(m, "chatId")
	participant := strVal(m, "participant")
	rawMsg, _ := m["message"].(map[string]any)
	if rawMsg != nil && messageID == "" {
		if keyMap, ok := rawMsg["key"].(map[string]any); ok {
			messageID = strVal(keyMap, "id")
			if chatID == "" {
				chatID = strVal(keyMap, "remoteJid")
			}
			if participant == "" {
				participant = strVal(keyMap, "participant")
			}
		}
	}

	res, err := s.mgr.DownloadMedia(r.Context(), sess, messageID, chatID, participant, rawMsg)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (s *Server) sendSeen(w http.ResponseWriter, r *http.Request) {
	bodyAny, _ := readBodyAny(r)
	m, _ := bodyAny.(map[string]any)
	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}
	chatID := strVal(m, "chatId", "jid", "phone", "to")
	jid, err := wa.ToJID(chatID)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'chatId' wajib diisi."})
		return
	}
	msgID := strVal(m, "messageId", "id")
	if msgID != "" {
		var partJID types.JID
		if p := strVal(m, "participant"); p != "" {
			partJID, _ = wa.ToJID(p)
		}
		_ = sess.Client.MarkRead(r.Context(), []types.MessageID{msgID}, time.Now(), jid, partJID)
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": fmt.Sprintf("Chat %s ditandai seen.", jid.String())})
}

func (s *Server) startTyping(w http.ResponseWriter, r *http.Request) {
	s.handleTyping(w, r, types.ChatPresenceComposing)
}

func (s *Server) stopTyping(w http.ResponseWriter, r *http.Request) {
	s.handleTyping(w, r, types.ChatPresencePaused)
}

func (s *Server) handleTyping(w http.ResponseWriter, r *http.Request, state types.ChatPresence) {
	bodyAny, _ := readBodyAny(r)
	m, _ := bodyAny.(map[string]any)
	reqSession := strVal(m, "session", "_botDevice", "name")
	sess := s.mgr.ResolveWorkingSession(reqSession)
	if sess == nil || sess.Status != wa.StatusWorking || sess.Client == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": fmt.Sprintf("Sesi '%s' belum terhubung.", reqSession)})
		return
	}
	chatID := strVal(m, "chatId", "jid", "phone", "to")
	jid, err := wa.ToJID(chatID)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "Field 'chatId' wajib diisi."})
		return
	}
	_ = sess.Client.SendChatPresence(r.Context(), jid, state, types.ChatPresenceMediaText)
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": fmt.Sprintf("Presence %s dikirim ke %s.", state, jid.String())})
}
