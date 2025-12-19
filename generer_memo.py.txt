import sqlite3
import pandas as pd
from datetime import datetime
from docx import Document
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

def appliquer_style_entete(cell):
    # Centrer et mettre en gras
    paragraph = cell.paragraphs[0]
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.bold = True
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Fond gris via XML
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'D9D9D9')  # gris clair
    tcPr.append(shd)

# ✅ Traduction des mois français vers anglais
def traduire_mois_en_anglais(mois_francais):
    mois_map = {
        "Janvier": "January", "Février": "February", "Mars": "March", "Avril": "April",
        "Mai": "May", "Juin": "June", "Juillet": "July", "Août": "August",
        "Septembre": "September", "Octobre": "October", "Novembre": "November", "Décembre": "December"
    }
    parts = mois_francais.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Format invalide pour le mois sélectionné : {mois_francais}")
    nom_mois, annee = parts
    mois_anglais = mois_map.get(nom_mois)
    if not mois_anglais:
        raise ValueError(f"Mois non reconnu : {nom_mois}")
    return f"{mois_anglais} {annee}"

# ✅ Formatage des montants
def format_montant(valeur):
    return f"{round(valeur):,}".replace(",", " ")

# ✅ Chemins vers les bases
chemin_parametres = r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\parametres.db"
chemin_livraisons = r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\livraisons.db"

# ✅ Fonction principale
def generer_memo_mensuel(mois_selectionne, afficher=False):
    mois_en_anglais = traduire_mois_en_anglais(mois_selectionne)
    mois_datetime = datetime.strptime(mois_en_anglais, "%B %Y")
    mois_debut = mois_datetime.replace(day=1)
    mois_fin = mois_datetime.replace(day=28) + pd.DateOffset(days=4)
    mois_fin = mois_fin - pd.DateOffset(days=mois_fin.day)

    # 📦 Connexions aux deux bases
    conn_liv = sqlite3.connect(chemin_livraisons)
    conn_param = sqlite3.connect(chemin_parametres)

    # 📥 Requêtes
    df_liv = pd.read_sql_query("""
        SELECT id AS livraison_id, date, transporteur_id, site AS site_id
        FROM livraisons
        WHERE date BETWEEN ? AND ?
    """, conn_liv, params=(str(mois_debut.date()), str(mois_fin.date())))
    if df_liv.empty:
        print("📭 Aucune donnée disponible pour ce mois.")
        conn_liv.close()
        conn_param.close()
        if afficher:
            return pd.DataFrame(), pd.DataFrame()
        else:
            return f"Aucune donnée disponible pour {mois_selectionne}"


    df_sites = pd.read_sql_query("""
        SELECT id AS site_id, nom_site, numero_compte
        FROM sites
    """, conn_param)

    df_liv = pd.merge(df_liv, df_sites, on="site_id", how="left")
    print("🔍 Aperçu des livraisons après jointure avec sites :")
    print(df_liv[["livraison_id", "site_id", "nom_site", "numero_compte"]].drop_duplicates())

    df_comp = pd.read_sql_query("""
        SELECT livraison_id, produit, volume_manquant, commentaire
        FROM compartiments
        WHERE commentaire = 'Remboursable'
    """, conn_liv)

    df_prix = pd.read_sql_query("SELECT produit_id, prix, date_debut FROM prix_vente", conn_param)
    df_prix["date_debut"] = pd.to_datetime(df_prix["date_debut"])

    df_trans = pd.read_sql_query("""
        SELECT id AS transporteur_id, nom
        FROM transporteurs
    """, conn_param)

    conn_liv.close()
    conn_param.close()

    # 🧠 Fusion des données
    df = pd.merge(df_comp, df_liv, on="livraison_id")

    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].between(mois_debut, mois_fin)]
    if df.empty:
        print("📭 Aucune livraison remboursable trouvée pour ce mois.")
        if afficher:
            return pd.DataFrame(), pd.DataFrame()
        else:
            return f"Aucune livraison remboursable pour {mois_selectionne}"

    def get_prix(produit_id, date_livraison):
        prix_liste = df_prix[(df_prix["produit_id"] == produit_id) & (df_prix["date_debut"] <= date_livraison)]
        if prix_liste.empty:
            print(f"⚠️ Aucun prix trouvé pour {produit_id} à la date {date_livraison.date()}")
            return None
        return prix_liste.sort_values("date_debut", ascending=False).iloc[0]["prix"]
    
    def calculer_montant(row):
        try:
            prix = get_prix(row["produit"], row["date"])
            if prix is None:
                print(f"⚠️ Aucun prix pour produit {row['produit']} à la date {row['date']}")
                return 0
            return float(row["volume_manquant"]) * float(prix)
        except Exception as e:
            print(f"❌ Erreur dans calcul montant pour livraison {row['livraison_id']}: {e}")
            return 0

    df["montant"] = df.apply(
    lambda row: float(row["volume_manquant"]) * float(get_prix(row["produit"], row["date"])),
    axis=1
    )
    print("🔍 Aperçu des données fusionnées :")
    colonnes_cibles = ["livraison_id", "nom_site", "numero_compte", "montant"]
    colonnes_existantes = [col for col in colonnes_cibles if col in df.columns]

    if colonnes_existantes:
        print("🔍 Aperçu des données fusionnées :")
        print(df[colonnes_existantes].head())
    else:
        print("⚠️ Aucune des colonnes attendues n’est disponible :", colonnes_cibles)
        print("📋 Colonnes réellement disponibles :", df.columns.tolist())

    df_transpo = df.groupby("transporteur_id")["montant"].sum().reset_index()
    df_transpo = pd.merge(df_transpo, df_trans, on="transporteur_id")
    df_transpo["montant"] = df_transpo["montant"].apply(format_montant)
    print("🔍 Lignes valides pour le groupby par site :")
    print(df[df["nom_site"].notnull()][["nom_site", "numero_compte", "montant"]])

    df_sites = df.groupby(["nom_site", "numero_compte"])["montant"].sum().reset_index()
    df_sites["montant"] = df_sites["montant"].apply(format_montant)

    # 📄 Création du document Word
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    date_du_jour = datetime.today().strftime("%d-%m-%Y")
    doc.add_paragraph(f"Abidjan, le {date_du_jour}")
    doc.add_paragraph("De : Eustache YAVO")
    doc.add_paragraph("A : Stéphane KONAN")
    doc.add_paragraph("CC : Fatim KANATE, Brigitte ADON")
    doc.add_paragraph(f"Objet : refacturation des manquants sur livraison {mois_selectionne}")

    doc.add_paragraph(f"Merci d’établir une note de débit afin de facturer les transporteurs ci-dessous sur les manquants constatés lors des livraisons du mois de {mois_selectionne}, selon les montants définis :")

    table1 = doc.add_table(rows=1, cols=2)
    table1.style = "Table Grid"
    hdr_cells = table1.rows[0].cells
    hdr_cells[0].text = "Transporteur"
    hdr_cells[1].text = "Total montant"
    for cell in hdr_cells:
        appliquer_style_entete(cell)


    for _, row in df_transpo.iterrows():
        row_cells = table1.add_row().cells
        row_cells[0].text = row["nom"]
        row_cells[1].text = row["montant"]

    total1 = df_transpo["montant"].apply(lambda x: int(x.replace(" ", ""))).sum()
    row_cells = table1.add_row().cells
    row_cells[0].text = "Total général"
    row_cells[1].text = format_montant(total1)

    doc.add_paragraph(f"\nAussi, merci d’établir sur les comptes des sites suivants, une note de crédit comme mentionnée dans le tableau plus bas en vue de la régularisation de ces manquants sur leurs différents comptes :")

    table2 = doc.add_table(rows=1, cols=3)
    table2.style = "Table Grid"
    hdr_cells = table2.rows[0].cells
    hdr_cells[0].text = "Ship to Name"
    hdr_cells[1].text = "N° COMPTE"
    hdr_cells[2].text = "Total montant"
    for cell in hdr_cells:
        appliquer_style_entete(cell)

    for _, row in df_sites.iterrows():
        row_cells = table2.add_row().cells
        row_cells[0].text = row["nom_site"]
        row_cells[1].text = row["numero_compte"]
        row_cells[2].text = row["montant"]

    total2 = df_sites["montant"].apply(lambda x: int(x.replace(" ", ""))).sum()
    row_cells = table2.add_row().cells
    row_cells[0].text = "Total général"
    row_cells[1].text = ""
    row_cells[2].text = format_montant(total2)

    doc.add_paragraph(f"\nToutefois, je vous prie de noter que le reliquat de ce montant (RI – RM) sera provisionné sur le compte de VECI.")
    from docx.shared import Cm

    table3 = doc.add_table(rows=2, cols=6)
    table3.style = "Table Grid"

    # Remplir la première ligne
    headers = ["Dispatcher", "Logistics Manager", "R.T. Manager", "S&D Manager", "FCC", "FM"]
    for i, header in enumerate(headers):
        cell = table3.rows[0].cells[i]
        cell.text = header
        cell.width = Cm(2.95)
        cell.height = Cm(1.5)

    from docx.enum.table import WD_ROW_HEIGHT

    # Forcer la hauteur de la ligne 2 même si vide
    row2 = table3.rows[1]
    row2.height = Cm(2.95)
    row2.height_rule = WD_ROW_HEIGHT.EXACTLY

    for cell in row2.cells:
        if not cell.text.strip():
            cell.text = "\u00A0"  # espace insécable

    nom_fichier = f"manquants hors freinte RETAIL-B2B {mois_selectionne}.docx"
    doc.save(nom_fichier)

    if afficher:
        return df_transpo, df_sites
    else:
        return nom_fichier