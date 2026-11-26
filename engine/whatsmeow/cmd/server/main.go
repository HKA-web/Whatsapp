package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"microservice/whatsapp/whatsmeow/internal/api"
	"microservice/whatsapp/whatsmeow/internal/config"
	"microservice/whatsapp/whatsmeow/internal/wa"
	"microservice/whatsapp/whatsmeow/internal/webhook"
)

func main() {
	cfg := config.Load()

	log.Printf("========================================")
	log.Printf("🚀 WhatsApp Machine (Engine: whatsmeow)")
	log.Printf("📡 Port       : %s", cfg.Port)
	log.Printf("🔗 Webhook    : %s", cfg.WebhookURL)
	log.Printf("🗄️  PostgreSQL : schema=public")
	log.Printf("========================================")

	wh := webhook.NewClient(cfg.WebhookURL)
	mgr, err := wa.NewManager(cfg, wh)
	if err != nil {
		log.Fatalf("❌ Gagal menginisialisasi whatsmeow manager: %v", err)
	}

	// Auto-start semua device yang sudah tersimpan di PostgreSQL
	go mgr.InitFromDB()

	router := api.NewRouter(mgr)
	addr := fmt.Sprintf("0.0.0.0:%s", cfg.Port)

	srv := &http.Server{
		Addr:    addr,
		Handler: router,
	}

	go func() {
		log.Printf("✅ Server whatsmeow berjalan di http://localhost:%s (Docs: http://localhost:%s/docs)", cfg.Port, cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("❌ Server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop
	log.Println("🛑 Menghentikan server whatsmeow...")
	_ = srv.Close()
}
