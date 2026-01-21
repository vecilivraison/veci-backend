import psycopg2

DATABASE_URL = "postgresql://manquant_db_vek4_user:w2t5Sq76xt2flP7VzsiFdAvErsfwJOVs@dpg-d5n24ocoud1c739nfhu0-a.frankfurt-postgres.render.com/manquant_db_vek4"

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("✅ Connexion réussie à PostgreSQL Render")
    conn.close()
except Exception as e:
    print("❌ Erreur de connexion :", e)
