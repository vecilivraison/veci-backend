import pandas as pd
from sqlalchemy import create_engine, text
import psycopg2

# -----------------------------
# 1. Paramètres de connexion
# -----------------------------
DATABASE_URL = "postgresql://manquant_db_vek4_user:w2t5Sq76xt2flP7VzsiFdAvErsfwJOVs@dpg-d5n24ocoud1c739nfhu0-a.frankfurt-postgres.render.com/manquant_db_vek4"

# -----------------------------
# 2. Test de connexion
# -----------------------------
try:
    conn = psycopg2.connect(DATABASE_URL)
    print("✅ Connexion réussie à PostgreSQL Render")
    conn.close()
except Exception as e:
    print("❌ Erreur de connexion :", e)
    exit()

# -----------------------------
# 3. Charger le fichier Excel
# -----------------------------
excel_file = "Base de données livraison.xlsx"

# Feuilles simples
sheets = ["commerciaux", "transporteurs", "depots", "sites", "chauffeurs", "produits"]

dfs = {}
for sheet in sheets:
    try:
        df = pd.read_excel(excel_file, sheet_name=sheet)
        df.columns = df.columns.str.strip().str.lower()  # normaliser les noms
        print(f"📄 Colonnes dans {sheet} :", df.columns.tolist())
        dfs[sheet] = df.drop_duplicates()
    except Exception as e:
        print(f"⚠️ Impossible de lire la feuille {sheet} :", e)

# Feuille citernes (qui contient aussi les tracteurs)
try:
    df_citernes_full = pd.read_excel(excel_file, sheet_name="citernes")
    df_citernes_full.columns = df_citernes_full.columns.str.strip().str.lower()
    print("📄 Colonnes dans citernes :", df_citernes_full.columns.tolist())

    # Séparer tracteurs et citernes avec transporteur_id inclus
    df_tracteurs = df_citernes_full[["num_tracteur", "transporteur_id", "transporteur"]] \
        .dropna(subset=["num_tracteur"]) \
        .drop_duplicates()

    df_citernes = df_citernes_full[["num_citerne", "transporteur_id", "transporteur"]] \
        .dropna(subset=["num_citerne"]) \
        .drop_duplicates()
except Exception as e:
    print("⚠️ Impossible de lire la feuille citernes :", e)
    df_tracteurs, df_citernes = None, None

# -----------------------------
# 4. Diagnostic pour vérifier transporteur_id
# -----------------------------
def diagnostic(df, name):
    if df is None:
        print(f"⚠️ {name} est vide")
        return
    print(f"=== Diagnostic {name} ===")
    print(df.head())        # affiche les 5 premières lignes
    print(df.dtypes)        # affiche les types de colonnes
    print("=========================")

diagnostic(df_citernes, "citernes")
diagnostic(df_tracteurs, "tracteurs")

# -----------------------------
# 5. Insérer dans PostgreSQL avec ON CONFLICT DO UPDATE
# -----------------------------
engine = create_engine(DATABASE_URL)

def insert_with_update(df, table_name, unique_cols, update_cols):
    if df is None or df.empty:
        print(f"⚠️ Aucune donnée à insérer dans {table_name}")
        return
    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                cols = list(row.index)
                values = {col: row[col] for col in cols}
                col_names = ", ".join(cols)
                placeholders = ", ".join([f":{col}" for col in cols])
                conflict_cols = ", ".join(unique_cols)
                update_stmt = ", ".join([f"{col}=EXCLUDED.{col}" for col in update_cols])

                sql = text(f"""
                    INSERT INTO {table_name} ({col_names})
                    VALUES ({placeholders})
                    ON CONFLICT ({conflict_cols}) DO UPDATE
                    SET {update_stmt}
                """)
                print("SQL généré :", sql)
                print("Valeurs :", values)
                conn.execute(sql, values)
        print(f"✅ Données insérées/mises à jour dans {table_name}")
    except Exception as e:
        print(f"❌ Erreur lors de l'insertion dans {table_name} :", e)

# -----------------------------
# 6. Exécuter pour chaque table
# -----------------------------
insert_with_update(dfs.get("commerciaux"), "commerciaux", ["id"], ["nom"])
insert_with_update(dfs.get("transporteurs"), "transporteurs", ["id"], ["nom"])
insert_with_update(dfs.get("depots"), "depots", ["id"], ["nom"])
insert_with_update(dfs.get("sites"), "sites", ["id"], ["nom"])
insert_with_update(dfs.get("chauffeurs"), "chauffeurs", ["id"], ["nom"])
insert_with_update(dfs.get("produits"), "produits", ["id"], ["nom"])

# Tables citernes et tracteurs
insert_with_update(df_tracteurs, "tracteurs", ["num_tracteur"], ["transporteur_id", "transporteur"])
insert_with_update(df_citernes, "citernes", ["num_citerne"], ["transporteur_id", "transporteur"])
