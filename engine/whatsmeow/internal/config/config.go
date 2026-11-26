package config

import (
	"flag"
	"os"
	"strings"
)

type Config struct {
	Port       string
	WebhookURL string
	PostgresDSN string
	SessionsDir string
}

func Load() *Config {
	port := flag.String("port", getEnv("WHATSAPP_PORT", "3002"), "HTTP server port")
	webhookURL := flag.String("webhook.url", getEnv("WHATSAPP_WEBHOOK_URL", "http://127.0.0.1:8008/whatsapp/webhook/"), "Django webhook URL")
	dsn := flag.String("dsn", getEnv("WHATSAPP_PG_DSN", ""), "PostgreSQL DSN for whatsmeow sqlstore (public schema)")
	_ = flag.String("catalogI18n", "", "Catalog i18n URL (optional compatibility flag)")
	_ = flag.String("config", "", "Config JSON path (optional compatibility flag)")
	flag.Parse()

	pgDSN := strings.TrimSpace(*dsn)
	if pgDSN == "" {
		pgDSN = "postgres://postgres:toor@127.0.0.1:5432/microservice?sslmode=disable&search_path=public"
	} else if !strings.Contains(pgDSN, "search_path=") {
		if strings.Contains(pgDSN, "?") {
			pgDSN += "&search_path=public"
		} else {
			pgDSN += "?search_path=public"
		}
	}

	return &Config{
		Port:        strings.TrimSpace(*port),
		WebhookURL:  strings.TrimSpace(*webhookURL),
		PostgresDSN: pgDSN,
		SessionsDir: "sessions",
	}
}

func getEnv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
