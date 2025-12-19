import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from docx import Document
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)  # Debug
if not DATABASE_URL:
    raise RuntimeError("❌ La variable d'environnement DATABASE_URL n'est pas définie.")

engine = create_engine(DATABASE_URL)

def generer_memo_mensuel(mois_selectionne, afficher=False):
    # Traduire mois
    mois_map = {"Janvier":"January","Février":"February","Mars":"March","Avril":"April",
                "Mai":"May","Juin":"June","Juillet":"July","Août":"August",
                "Septembre":"September","Octobre":"October","Novembre":"November","Décembre":"December"}
    nom_mois, annee = mois_selectionne.split()
    mois_en_anglais = f"{mois_map[nom_mois]} {annee}"
    mois_datetime = datetime.strptime(mois_en_anglais, "%B %Y")
    mois_debut = mois_datetime.replace(day=1)
    mois_fin = (mois_debut + pd.DateOffset(months=1)) - pd.DateOffset(days=1)

    # 📥 Requêtes Postgres
    df_liv = pd.read_sql("""
        SELECT id AS livraison_id, date, transporteur_id, site_id
        FROM livraison
        WHERE date BETWEEN %(d1)s AND %(d2)s
    """, engine, params={"d1": str(mois_debut.date()), "d2": str(mois_fin.date())})

    if df_liv.empty:
        return pd.DataFrame(), pd.DataFrame() if afficher else f"Aucune donnée disponible pour {mois_selectionne}"

    df_sites = pd.read_sql("SELECT id AS site_id, nom_site, numero_compte FROM sites", engine)
    df_liv = pd.merge(df_liv, df_sites, on="site_id", how="left")

    df_comp = pd.read_sql("""
        SELECT livraison_id, produit, volume_manquant, commentaire
        FROM compartiments
        WHERE commentaire = 'Remboursable'
    """, engine)

    df_prix = pd.read_sql("SELECT produit_id, prix, date_debut FROM prix_vente", engine)
    df_prix["date_debut"] = pd.to_datetime(df_prix["date_debut"])

    df_trans = pd.read_sql("SELECT id AS transporteur_id, nom FROM transporteurs", engine)

    # Fusion
    df = pd.merge(df_comp, df_liv, on="livraison_id")
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].between(mois_debut, mois_fin)]

    # Calcul montant
    def get_prix(produit_id, date_livraison):
        prix_liste = df_prix[(df_prix["produit_id"] == produit_id) & (df_prix["date_debut"] <= date_livraison)]
        if prix_liste.empty:
            return None
        return prix_liste.sort_values("date_debut", ascending=False).iloc[0]["prix"]

    df["montant"] = df.apply(lambda row: float(row["volume_manquant"]) * float(get_prix(row["produit"], row["date"]) or 0), axis=1)

    df_transpo = df.groupby("transporteur_id")["montant"].sum().reset_index()
    df_transpo = pd.merge(df_transpo, df_trans, on="transporteur_id")
    df_sites = df.groupby(["nom_site", "numero_compte"])["montant"].sum().reset_index()

    # 📄 Création du document Word (inchangé)
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    # ... reste du code identique pour générer le Word ...

    nom_fichier = f"manquants hors freinte RETAIL-B2B {mois_selectionne}.docx"
    doc.save(nom_fichier)

    return (df_transpo, df_sites) if afficher else nom_fichier
