# -------------------- CONFIGURATION GÉNÉRALE --------------------
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import hashlib
import sqlite3
import os
from generer_memo import generer_memo_mensuel
import generer_memo
print("📁 Fichier utilisé :", generer_memo.__file__)

st.set_page_config(page_title="🚛 Visualisation des livraisons", layout="wide")

chemin_parametres = r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\parametres.db"
chemin_db = r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\livraisons.db"

# -------------------- BLOC 1 — PAGE DE CONNEXION --------------------
if "utilisateur" not in st.session_state:
    st.title("🔐 Connexion requise")
    col1, col2 = st.columns(2)
    with col1:
        identifiant = st.text_input("👤 Nom d'utilisateur")
    with col2:
        mot_de_passe = st.text_input("🔐 Mot de passe", type="password")

    if st.button("✅ Se connecter"):
        conn = sqlite3.connect(chemin_parametres)
        cursor = conn.cursor()
        cursor.execute("SELECT nom_utilisateur, mot_de_passe_hash, role, transporteur_id FROM utilisateurs WHERE nom_utilisateur = ?", (identifiant,))
        result = cursor.fetchone()
        conn.close()

        if result:
            hash_mdp = hashlib.sha256(mot_de_passe.encode()).hexdigest()
            if hash_mdp == result[1]:
                st.session_state["utilisateur"] = {
                    "nom": result[0],
                    "role": result[2],
                    "transporteur_id": result[3]
                }
                st.success("✅ Connexion réussie")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
        else:
            st.error("❌ Utilisateur non trouvé")
    st.stop()

# -------------------- BLOC 2 — FONCTIONS UTILES --------------------
def get_prix_en_vigueur(produit_id, date_reference):
    conn = sqlite3.connect(chemin_parametres)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prix FROM prix_vente
        WHERE produit_id = ? AND date_debut <= ? AND date_fin >= ?
        ORDER BY date_debut DESC LIMIT 1
    """, (produit_id, date_reference, date_reference))
    result = cursor.fetchone()
    conn.close()
    return f"{result[0]:,.0f} XOF".replace(",", " ") if result else "❌ Non défini"

def get_prix_applicable(produit_id, date_livraison):
    conn = sqlite3.connect(chemin_parametres)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prix FROM prix_vente
        WHERE produit_id = ? AND date_debut <= ? AND date_fin >= ?
        ORDER BY date_debut DESC LIMIT 1
    """, (produit_id, date_livraison, date_livraison))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        raise ValueError(f"Aucun prix enregistré pour {produit_id} à la date {date_livraison}")

def calcul_volume(df, produit_id, prix):
    df_p = df[df["produit"] == produit_id]
    vol_livre = df_p["volume_livre"].sum()
    vol_manq = df_p[df_p["commentaire"] == "Remboursable"]["volume_manquant"].sum()
    val_manq = vol_manq * prix
    return vol_livre, vol_manq, val_manq

# -------------------- BLOC 3 — FONCTION : MENU LATÉRAL --------------------
def afficher_menu_principal():
    menus = {
        "🚛 Visualisation des livraisons": "livraisons",
        "💰 Gestion des prix": "prix",
        "📄 Mémo de régularisation": "memo",
        "👥 Gestion des comptes": "comptes"
    }

    admin_mode = (
        "utilisateur" in st.session_state
        and st.session_state["utilisateur"]["role"] == "admin"
    )

    if "menu_selectionne" not in st.session_state:
        st.session_state.menu_selectionne = list(menus.keys())[0]

    st.sidebar.markdown("<h3 style='margin-bottom: 20px;'>🧭 Menu principal</h3>", unsafe_allow_html=True)

    st.markdown("""
        <style>
        div[data-testid="stSidebar"] button {
            width: 100%;
            text-align: left;
            font-weight: bold;
            font-size: 16px;
            padding: 10px 16px;
            margin-bottom: 8px;
            border-radius: 6px;
        }
        div[data-testid="stSidebar"] button:hover {
            background-color: #e0e0e0;
        }
        div[data-testid="stSidebar"] button.menu-actif {
            background-color: #4F8BF9 !important;
            color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)

    for label, identifiant in menus.items():
        # Masquer "comptes" pour les non-admins
        if identifiant == "comptes" and not admin_mode:
            continue
        # Masquer "memo" pour les transporteurs
        if identifiant == "memo" and st.session_state["utilisateur"]["role"] == "transporteur":
            continue

        bouton = st.sidebar.button(label, key=f"menu_{identifiant}")
        if bouton:
            st.session_state.menu_selectionne = label
            st.rerun()

        if st.session_state.menu_selectionne == label:
            st.markdown(f"""
                <script>
                const btn = window.parent.document.querySelector('button[data-testid="menu_{identifiant}"]');
                if (btn) btn.classList.add("menu-actif");
                </script>
            """, unsafe_allow_html=True)

    if "utilisateur" in st.session_state:
        user = st.session_state["utilisateur"]
        st.sidebar.markdown(f"""
            <hr>
            <div style='font-size:14px; color:gray; margin-top:10px;'>
                Connecté en tant que <b>{user['nom']}</b><br>
                Rôle : <b>{user['role'].capitalize()}</b>
            </div>
        """, unsafe_allow_html=True)
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    if st.sidebar.button("🚪 Se déconnecter"):
        del st.session_state["utilisateur"]
        st.rerun()

    return st.session_state.menu_selectionne

# -------------------- Bloc 4 — FONCTIONS DE CONTENU PAR MENU --------------------
# -------------------- FONCTION : afficher_menu_livraisons --------------------
def afficher_menu_livraisons():
    st.title("🚛 VISUALISATION DES LIVRAISONS")

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        date_debut = st.date_input("📅 Date de début", value=datetime.today())
    with col2:
        date_fin = st.date_input("📅 Date de fin", value=datetime.today())
    with col3:
        afficher = st.button("🔍 Afficher")

    st.subheader("🧰 Filtres sur les livraisons")
    for key, default in {
        "filtre_id": "", "filtre_date_exacte": None, "filtre_commande": "", "filtre_bl": "",
        "filtre_depot": "", "filtre_transporteur": "", "filtre_tracteur": "",
        "filtre_citerne": "", "filtre_chauffeur": ""
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        st.session_state.filtre_id = st.text_input("🔎 Filtrer par ID", value=st.session_state.filtre_id)
        st.session_state.filtre_commande = st.text_input("🔎 Filtrer par Commande", value=st.session_state.filtre_commande)
        st.session_state.filtre_bl = st.text_input("🔎 Filtrer par BL", value=st.session_state.filtre_bl)
    with colf2:
        st.session_state.filtre_depot = st.text_input("🔎 Filtrer par Dépôt", value=st.session_state.filtre_depot)
        st.session_state.filtre_transporteur = st.text_input("🔎 Filtrer par Transporteur", value=st.session_state.filtre_transporteur)
        st.session_state.filtre_tracteur = st.text_input("🔎 Filtrer par Tracteur", value=st.session_state.filtre_tracteur)
    with colf3:
        st.session_state.filtre_citerne = st.text_input("🔎 Filtrer par Citerne", value=st.session_state.filtre_citerne)
        st.session_state.filtre_chauffeur = st.text_input("🔎 Filtrer par Chauffeur", value=st.session_state.filtre_chauffeur)
        st.session_state.filtre_date_exacte = st.date_input("📅 Filtrer par date exacte", value=st.session_state.filtre_date_exacte)

    if st.button("🔄 Réinitialiser les filtres"):
        for key in st.session_state:
            if key.startswith("filtre_"):
                st.session_state[key] = "" if isinstance(st.session_state[key], str) else None
        st.rerun()

    st.subheader("📊 RECAP MANQUANT SUR LIVRAISON")

    conn = sqlite3.connect(chemin_db)
    df_liv = pd.read_sql_query("SELECT * FROM livraisons", conn)
    df_liv.rename(columns={"id": "livraison_id"}, inplace=True)
    df_comp = pd.read_sql_query("SELECT * FROM compartiments", conn)
    conn.close()

    if st.session_state["utilisateur"]["role"] == "transporteur":
        df_liv = df_liv[df_liv["transporteur_id"] == st.session_state["utilisateur"]["transporteur_id"]]

    conn2 = sqlite3.connect(chemin_parametres)
    df_trans = pd.read_sql_query("SELECT id, nom FROM transporteurs", conn2)
    df_trans.rename(columns={"id": "transporteur_id", "nom": "nom_transporteur"}, inplace=True)
    df_liv = pd.merge(df_liv, df_trans, on="transporteur_id", how="left")
    conn2.close()

    if afficher:
        df_liv["date"] = pd.to_datetime(df_liv["date"]).dt.date
        df_liv = df_liv[(df_liv["date"] >= date_debut) & (df_liv["date"] <= date_fin)]

    trans_dict = dict(zip(df_trans["transporteur_id"], df_trans["nom_transporteur"]))
    nom_produits = {"PDT1": "Super", "PDT2": "Diesel", "PDT3": "Pétrole"}

    tableau = []
    for _, row in df_liv.iterrows():
        id_liv = row["livraison_id"]
        df_c = df_comp[df_comp["livraison_id"] == id_liv]

        try:
            prix_super = get_prix_applicable("PDT1", row["date"])
            prix_diesel = get_prix_applicable("PDT2", row["date"])
            prix_petrole = get_prix_applicable("PDT3", row["date"])
        except ValueError as e:
            st.warning(f"⚠️ Livraison ignorée : {e}")
            continue

        vol_super, manq_super, val_super = calcul_volume(df_c, "PDT1", prix_super)
        vol_diesel, manq_diesel, val_diesel = calcul_volume(df_c, "PDT2", prix_diesel)
        vol_petrole, manq_petrole, val_petrole = calcul_volume(df_c, "PDT3", prix_petrole)

        total_l = vol_super + vol_diesel + vol_petrole
        total_m = manq_super + manq_diesel + manq_petrole
        total_x = val_super + val_diesel + val_petrole

        pdf_path = os.path.join(os.path.expanduser("~"), "Documents", f"Résumé_livraison_{row['commande']}_{row['bl']}_{row['date']}.pdf").replace(" ", "_")
        bl_path = os.path.join(r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\docs", os.path.basename(row["photo_bl_path"]))
        ocst_path = os.path.join(r"C:\Users\Utilisateur\Bot_arbitrage\BOT_MULTI_EXCHANGE\Bot Manquant\docs", os.path.basename(row["photo_ocst_path"]))

        lien_pdf = f"file:///{pdf_path.replace(os.sep, '/')}" if os.path.exists(pdf_path) else "❌"
        lien_bl = f"file:///{bl_path.replace(os.sep, '/')}" if os.path.exists(bl_path) else "❌"
        lien_ocst = f"file:///{ocst_path.replace(os.sep, '/')}" if os.path.exists(ocst_path) else "❌"

        tableau.append([
            id_liv, row["date"], row["commande"], row["bl"], row["depot"],
            str(row.get("nom_transporteur", "")).strip() or "❌ Inconnu",
            row["tracteur"], row["citerne"], row["chauffeur"],
            vol_super, vol_diesel, vol_petrole, total_l,
            manq_super, manq_diesel, manq_petrole, total_m,
            val_super, val_diesel, val_petrole, total_x,
            f'<a href="{lien_pdf}" target="_blank">Voir PDF</a>' if lien_pdf != "❌" else "❌",
            f'<a href="{lien_bl}" target="_blank">Voir BL</a>' if lien_bl != "❌" else "❌",
            f'<a href="{lien_ocst}" target="_blank">Voir OCST</a>' if lien_ocst != "❌" else "❌",

        ])
    
    columns = pd.MultiIndex.from_tuples([
        ("INFORMATION GÉNÉRALE", "Id"), ("INFORMATION GÉNÉRALE", "Date"), ("INFORMATION GÉNÉRALE", "Commande"),
        ("INFORMATION GÉNÉRALE", "BL"), ("INFORMATION GÉNÉRALE", "Dépôt"), ("INFORMATION GÉNÉRALE", "Transporteur"),
        ("INFORMATION GÉNÉRALE", "Tracteur"), ("INFORMATION GÉNÉRALE", "Citerne"), ("INFORMATION GÉNÉRALE", "Chauffeur"),

        ("VOLUME LIVRÉ", f"{nom_produits['PDT1']} (L)"), ("VOLUME LIVRÉ", f"{nom_produits['PDT2']} (L)"),
        ("VOLUME LIVRÉ", f"{nom_produits['PDT3']} (L)"), ("VOLUME LIVRÉ", "Total (L)"),

        ("MANQUANT EN LITRE", f"{nom_produits['PDT1']} (L)"), ("MANQUANT EN LITRE", f"{nom_produits['PDT2']} (L)"),
        ("MANQUANT EN LITRE", f"{nom_produits['PDT3']} (L)"), ("MANQUANT EN LITRE", "Total (L)"),

        ("MANQUANT EN XOF", f"{nom_produits['PDT1']} (XOF)"), ("MANQUANT EN XOF", f"{nom_produits['PDT2']} (XOF)"),
        ("MANQUANT EN XOF", f"{nom_produits['PDT3']} (XOF)"), ("MANQUANT EN XOF", "Total (XOF)"),

        ("PIÈCES JOINTES", "PDF récap"), ("PIÈCES JOINTES", "BL"), ("PIÈCES JOINTES", "OCST")
    ])

    df_all = pd.DataFrame(tableau, columns=columns)
    import xlsxwriter
    from collections import defaultdict
    from io import BytesIO

    # ✅ Exclure les colonnes de pièces jointes
    colonnes_exclues = [("PIÈCES JOINTES", "PDF récap"), ("PIÈCES JOINTES", "BL"), ("PIÈCES JOINTES", "OCST")]
    df_export = df_all.drop(columns=colonnes_exclues)

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer)
    worksheet = workbook.add_worksheet("RECAP")

    # ✅ Définir les couleurs par catégorie
    couleurs = {
        "INFORMATION GÉNÉRALE": ("#B7DEE8", "#DCEEF4"),
        "VOLUME LIVRÉ": ("#FCD5B4", "#FDE9D9"),
        "MANQUANT EN LITRE": ("#FFF2CC", "#FFF9E5"),
        "MANQUANT EN XOF": ("#D9D2E9", "#EDEAF5"),
    }

    # ✅ Créer les formats
    formats_header = {}
    formats_sub = {}
    for cat, (bg_header, bg_sub) in couleurs.items():
        formats_header[cat] = workbook.add_format({
            "bold": True, "align": "center", "valign": "vcenter", "border": 1,
            "bg_color": bg_header
        })
        formats_sub[cat] = workbook.add_format({
            "bold": True, "align": "center", "valign": "vcenter", "border": 1,
            "bg_color": bg_sub
        })

    format_cell_gauche = workbook.add_format({"align": "left", "valign": "vcenter", "border": 1})
    format_cell_centre = workbook.add_format({"align": "center", "valign": "vcenter", "border": 1})
    format_cell_droite = workbook.add_format({"align": "right", "valign": "vcenter", "border": 1})

    # ✅ Fusion des en-têtes
    groupes = defaultdict(list)
    for col in df_export.columns:
        groupes[col[0]].append(col[1])

    col = 0
    colonne_to_categorie = {}
    for cat, subcols in groupes.items():
        largeur = len(subcols)
        worksheet.merge_range(0, col, 0, col + largeur - 1, cat, formats_header[cat])
        for i, sub in enumerate(subcols):
            worksheet.write(1, col + i, sub, formats_sub[cat])
            colonne_to_categorie[col + i] = cat
        col += largeur

    # ✅ Écriture des données
    for row_idx, row in enumerate(df_export.values):
        for col_idx, val in enumerate(row):
            cat = colonne_to_categorie.get(col_idx, "")
            if cat == "INFORMATION GÉNÉRALE":
                fmt = format_cell_gauche
            elif cat == "MANQUANT EN XOF":
                fmt = format_cell_droite
            else:
                fmt = format_cell_centre
            # ✅ Appliquer format numérique avec séparateur pour VOLUME LIVRÉ et MANQUANT EN XOF
            if cat in ["VOLUME LIVRÉ", "MANQUANT EN XOF"]:
                fmt.set_num_format("# ##0")
                worksheet.write_number(row_idx + 2, col_idx, float(val) if val != "" else 0, fmt)
            else:
                worksheet.write(row_idx + 2, col_idx, val, fmt)

    # ✅ Auto-ajustement
    for i in range(col):
        worksheet.set_column(i, i, 18)

    workbook.close()
    buffer.seek(0)

    # ✅ Bouton de téléchargement
    st.download_button(
        label="📥 Exporter en Excel",
        data=buffer,
        file_name="recap_manquant.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ✅ Formatage des colonnes numériques
    for col in df_all.columns:
        if df_all[col].dtype in ["float64", "int64"]:
            df_all[col] = df_all[col].apply(lambda val: f"{int(round(val)):,}".replace(",", " ") if pd.notnull(val) else val)

    # ✅ Affichage du tableau
    if df_all.empty:
        st.warning("⚠️ Aucun tableau de livraisons n’a été généré. Vérifiez les données ou les prix applicables.")
    else:
        st.markdown("""
        <style>
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 6px 12px;
            text-align: left;
            white-space: nowrap;
        }
        </style>
        """, unsafe_allow_html=True)
        st.write(df_all.to_html(escape=False, index=False), unsafe_allow_html=True)

# -------------------- FONCTION : afficher_menu_prix --------------------
def afficher_menu_prix():
    st.title("💰 GESTION DES PRIX")

    conn = sqlite3.connect(chemin_parametres)
    cursor = conn.cursor()

    # Récupérer les produits
    df_produits = pd.read_sql_query("SELECT id, nom FROM produits", conn)
    produits = dict(zip(df_produits["id"], df_produits["nom"]))

    # Choisir une date de référence
    date_ref = st.date_input("📅 Date de référence", value=datetime.today().date())

    st.subheader("📌 Prix en vigueur à la date choisie")

    # Afficher les prix en vigueur ou message d’absence
    for pid, nom in produits.items():
        cursor.execute("""
            SELECT prix FROM prix_vente
            WHERE produit_id = ? AND date_debut <= ? AND date_fin >= ?
            ORDER BY date_modification DESC LIMIT 1
        """, (pid, date_ref, date_ref))
        result = cursor.fetchone()
        if result:
            st.metric(nom, f"{int(result[0]):,} XOF".replace(",", " "))
        else:
            st.warning(f"❌ {nom} — Prix non disponible")
            st.caption("👉 Cliquez sur « Saisir un prix » ci-dessous pour l’ajouter.")

    st.markdown("---")
    st.subheader("🆕 Saisie ou modification d’un prix")

    if st.button("➕ Saisir un prix"):
        st.session_state.show_form_prix = True

    if st.session_state.get("show_form_prix", False):
        with st.form("form_prix_vente"):
            nom_produit = st.selectbox("🛢️ Produit", list(produits.values()))
            produit_id = [k for k, v in produits.items() if v == nom_produit][0]
            prix = st.number_input("💰 Prix (XOF)", min_value=0.0, step=0.1)
            date_debut = st.date_input("📅 Date de début")
            date_fin = st.date_input("📅 Date de fin")

            confirmer = st.form_submit_button("✅ Ajouter")

        if confirmer:
            cursor.execute("""
                SELECT id FROM prix_vente
                WHERE produit_id = ? AND date_debut <= ? AND date_fin >= ?
            """, (produit_id, date_fin, date_debut))
            conflit = cursor.fetchone()

            if conflit:
                st.warning(f"⚠️ Un prix existe déjà pour {nom_produit} sur cette plage.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Confirmer la modification"):
                        cursor.execute("DELETE FROM prix_vente WHERE id = ?", (conflit[0],))
                        cursor.execute("""
                            INSERT INTO prix_vente (produit_id, prix, date_debut, date_fin, date_modification)
                            VALUES (?, ?, ?, ?, ?)
                        """, (produit_id, prix, str(date_debut), str(date_fin), datetime.now()))
                        conn.commit()
                        st.success("✅ Prix modifié avec succès.")
                        st.session_state.show_form_prix = False
                        st.rerun()
                with col2:
                    if st.button("❌ Annuler"):
                        st.info("Modification annulée.")
                        st.session_state.show_form_prix = False
            else:
                cursor.execute("""
                    INSERT INTO prix_vente (produit_id, prix, date_debut, date_fin, date_modification)
                    VALUES (?, ?, ?, ?, ?)
                """, (produit_id, prix, str(date_debut), str(date_fin), datetime.now()))
                conn.commit()
                st.success("✅ Prix enregistré.")
                st.session_state.show_form_prix = False
                st.rerun()

    # Historique des prix
    st.subheader("📜 Historique des prix enregistrés")
    df_prix = pd.read_sql_query("""
        SELECT produit_id, prix, date_debut, date_fin, date_modification
        FROM prix_vente
        ORDER BY date_modification DESC
    """, conn)

    df_prix["Produit"] = df_prix["produit_id"].map(produits)
    df_prix = df_prix[["Produit", "prix", "date_debut", "date_fin", "date_modification"]]
    st.dataframe(df_prix, use_container_width=True)

    conn.close()

# -------------------- FONCTION : afficher_menu_memo --------------------
def afficher_menu_memo():
    st.title("📄 GÉNÉRATION DU MÉMO DE RÉGULARISATION")

    mois_options = [
        "Janvier 2025", "Février 2025", "Mars 2025", "Avril 2025", "Mai 2025", "Juin 2025",
        "Juillet 2025", "Août 2025", "Septembre 2025", "Octobre 2025", "Novembre 2025", "Décembre 2025"
    ]
    mois_selectionne = st.selectbox("🗓️ Choisir le mois du mémo", mois_options, key="mois_memo")

    if st.button("📄 Télécharger le mémo"):
        nom_fichier = generer_memo_mensuel(mois_selectionne)
        import os
        if not os.path.isfile(nom_fichier):
            print("📭 Aucune donnée disponible pour ce mois.")
            # Affiche un message dans l’interface Streamlit ou autre
            st.warning("Aucune donnée disponible pour ce mois.")
        else:
            with open(nom_fichier, "rb") as f:
                st.download_button(
                    label="📥 Télécharger le fichier Word",
                    data=f,
                    file_name=nom_fichier,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            st.success(f"✅ Mémo généré pour {mois_selectionne}")

    # ✅ Affichage des tableaux
    df_transpo, df_sites = generer_memo_mensuel(mois_selectionne, afficher=True)
    st.subheader("🚚 Montants par transporteur")
    st.dataframe(df_transpo, use_container_width=True)

    st.subheader("🏢 Montants par site")
    st.dataframe(df_sites, use_container_width=True)

# -------------------- FONCTION : afficher_menu_comptes --------------------
def afficher_menu_comptes():
    st.title("👥 GESTION DES COMPTES")
    st.subheader("🆕 Créer un nouvel utilisateur")

    col1, col2, col3 = st.columns(3)

    with col1:
        nouveau_nom = st.text_input("👤 Nom d'utilisateur")

    with col2:
        nouveau_mdp = st.text_input("🔐 Mot de passe", type="password")

    with col3:
        nouveau_role = st.selectbox("🎯 Rôle", ["admin", "transporteur", "commercial"])

    transporteur_id = None
    if nouveau_role == "transporteur":
        conn = sqlite3.connect(chemin_parametres)
        df_trans = pd.read_sql_query("SELECT id, nom FROM transporteurs", conn)
        conn.close()

        transporteurs = dict(zip(df_trans["nom"], df_trans["id"]))
        transporteur_nom = st.selectbox("🚚 Choisir le transporteur", list(transporteurs.keys()))
        transporteur_id = transporteurs[transporteur_nom]

    if st.button("✅ Ajouter l'utilisateur"):
        if not nouveau_nom or not nouveau_mdp:
            st.warning("⚠️ Veuillez remplir tous les champs.")
        elif nouveau_role == "transporteur" and transporteur_id is None:
            st.warning("⚠️ Veuillez sélectionner un transporteur.")
        else:
            hash_mdp = hashlib.sha256(nouveau_mdp.encode()).hexdigest()
            conn = sqlite3.connect(chemin_parametres)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO utilisateurs (nom_utilisateur, mot_de_passe_clair, mot_de_passe_hash, role, transporteur_id)
                VALUES (?, ?, ?, ?, ?)
            """, (nouveau_nom, nouveau_mdp, hash_mdp, nouveau_role, transporteur_id))
            conn.commit()
            conn.close()
            st.success(f"✅ Utilisateur {nouveau_nom} ajouté avec succès.")

    st.subheader("🗂️ Utilisateurs existants")
    conn = sqlite3.connect(chemin_parametres)
    df_users = pd.read_sql_query("""
        SELECT u.id, u.nom_utilisateur, u.mot_de_passe_clair AS mot_de_passe, u.role,
            t.nom AS nom_transporteur
        FROM utilisateurs u
        LEFT JOIN transporteurs t ON u.transporteur_id = t.id
        ORDER BY u.id ASC
    """, conn)

    conn.close()
    st.dataframe(df_users, use_container_width=True)

    id_supprimer = st.text_input("🗑️ ID de l'utilisateur à supprimer")
    if st.button("❌ Supprimer l'utilisateur"):
        if not id_supprimer:
            st.warning("⚠️ Veuillez entrer un ID.")
        else:
            try:
                conn = sqlite3.connect(chemin_parametres)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM utilisateurs WHERE id = ?", (id_supprimer,))
                conn.commit()
                conn.close()
                st.success(f"✅ Utilisateur avec ID {id_supprimer} supprimé.")
            except Exception as e:
                st.error(f"❌ Erreur lors de la suppression : {e}")

# -------------------- LAYOUT PRINCIPAL --------------------
if "utilisateur" in st.session_state:
    menu_selectionne = afficher_menu_principal()

    admin_mode = st.session_state["utilisateur"]["role"] == "admin"

    if menu_selectionne == "🚛 Visualisation des livraisons":
        afficher_menu_livraisons()
    elif menu_selectionne == "💰 Gestion des prix":
        if admin_mode:
            afficher_menu_prix()
        else:
            st.warning("⚠️ Accès réservé aux administrateurs.")
    elif menu_selectionne == "📄 Mémo de régularisation":
        afficher_menu_memo()
    elif menu_selectionne == "👥 Gestion des comptes":
        if admin_mode:
            afficher_menu_comptes()
        else:
            st.warning("⚠️ Accès réservé aux administrateurs.")
# -------------------- FIN DU SCRIPT --------------------