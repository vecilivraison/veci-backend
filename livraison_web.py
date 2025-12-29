# -------------------- CONFIGURATION GÉNÉRALE --------------------
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import hashlib
import os
from sqlalchemy import create_engine, text
from generer_memo import generer_memo_mensuel


# ✅ Connexion PostgreSQL via Render
DATABASE_URL = os.getenv("DATABASE_URL")  # doit être défini dans Render
engine = create_engine(DATABASE_URL)


st.set_page_config(page_title="🚛 Visualisation des livraisons", layout="wide")

# -------------------- BLOC 1 — PAGE DE CONNEXION --------------------
if "utilisateur" not in st.session_state:
    st.title("🔐 Connexion requise")
    col1, col2 = st.columns(2)
    with col1:
        identifiant = st.text_input("👤 Nom d'utilisateur")
    with col2:
        mot_de_passe = st.text_input("🔐 Mot de passe", type="password")

    if st.button("✅ Se connecter"):
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT nom_utilisateur, mot_de_passe_hash, role, transporteur_id FROM utilisateurs WHERE nom_utilisateur = :id"),
                {"id": identifiant}
            ).fetchone()

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
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT prix FROM prix_vente
            WHERE produit_id = :pid AND date_debut <= :d AND date_fin >= :d
            ORDER BY date_debut DESC LIMIT 1
        """), {"pid": produit_id, "d": date_reference}).fetchone()
    return f"{result[0]:,.0f} XOF".replace(",", " ") if result else "❌ Non défini"

def get_prix_applicable(produit_id, date_livraison):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT prix FROM prix_vente
            WHERE produit_id = :pid AND date_debut <= :d AND date_fin >= :d
            ORDER BY date_debut DESC LIMIT 1
        """), {"pid": produit_id, "d": date_livraison}).fetchone()
    if result:
        return result[0]
    else:
        raise ValueError(f"Aucun prix enregistré pour {produit_id} à la date {date_livraison}")

def calcul_volume(df, produit_id, prix):
    df_p = df[df["produit_id"] == produit_id]
    vol_livre = df_p["volume_livre"].sum()
    vol_manq = df_p[df_p["commentaire"] == "Remboursable"]["volume_manquant"].sum()
    val_manq = vol_manq * prix
    return vol_livre, vol_manq, val_manq

# -------------------- BLOC 3 — MENU LATÉRAL --------------------
def afficher_menu_principal():
    menus = {
        "🚛 Visualisation des livraisons": "livraisons",
        "💰 Gestion des prix": "prix",
        "📄 Mémo de régularisation": "memo",
        "👥 Gestion des comptes": "comptes"
    }
    admin_mode = ("utilisateur" in st.session_state and st.session_state["utilisateur"]["role"] == "admin")

    if "menu_selectionne" not in st.session_state:
        st.session_state.menu_selectionne = list(menus.keys())[0]

    st.sidebar.markdown("<h3>🧭 Menu principal</h3>", unsafe_allow_html=True)
    for label, identifiant in menus.items():
        if identifiant == "comptes" and not admin_mode:
            continue
        if st.sidebar.button(label, key=f"menu_{identifiant}"):
            st.session_state.menu_selectionne = label
            st.rerun()

    if "utilisateur" in st.session_state:
        user = st.session_state["utilisateur"]
        st.sidebar.markdown(f"""
        <hr>
        Connecté en tant que <b>{user['nom']}</b><br>
        Rôle : <b>{user['role'].capitalize()}</b>
        """, unsafe_allow_html=True)
        if st.sidebar.button("🚪 Se déconnecter"):
            del st.session_state["utilisateur"]
            st.rerun()

    return st.session_state.menu_selectionne

# -------------------- BLOC 4 — VISUALISATION DES LIVRAISONS --------------------
def afficher_menu_livraisons():
    st.title("🚛 VISUALISATION DES LIVRAISONS")

    # ✅ État persistant pour garder la section visible
    if "livraisons_visible" not in st.session_state:
        st.session_state.livraisons_visible = False

    col1, col2, col3 = st.columns([2, 2, 2])
    from datetime import date

    premier_jour_mois = date.today().replace(day=1)
    aujourdhui = date.today()

    with col1:
        date_debut = st.date_input("📅 Date de début", value=premier_jour_mois)
    with col2:
        date_fin = st.date_input("📅 Date de fin", value=aujourdhui)
    with col3:
        afficher_btn = st.button("🔍 Afficher")

    if afficher_btn:
        st.session_state.livraisons_visible = True

    df_liv = pd.read_sql("SELECT * FROM livraison", engine)
    df_comp = pd.read_sql("SELECT * FROM compartiments", engine)

    if st.session_state["utilisateur"]["role"] == "transporteur":
        df_liv = df_liv[df_liv["transporteur_id"] == st.session_state["utilisateur"]["transporteur_id"]]

    if st.session_state.livraisons_visible:
        df_liv["date"] = pd.to_datetime(df_liv["date"]).dt.date
        df_liv = df_liv[(df_liv["date"] >= date_debut) & (df_liv["date"] <= date_fin)]

        nom_produits = {"PDT1": "Super", "PDT2": "Diesel", "PDT3": "Pétrole"}
        tableau = []

        for _, row in df_liv.iterrows():
            id_liv = row["id"]
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

            pdf_path = os.path.join(os.path.expanduser("~"), "Documents",
                                    f"Résumé_livraison_{row['commande']}_{row['bl_num']}_{row['date']}.pdf").replace(" ", "_")
            bl_path = os.path.join("docs", os.path.basename(str(row.get("photo_bl_path", ""))))
            ocst_path = os.path.join("docs", os.path.basename(str(row.get("photo_ocst_path", ""))))

            lien_pdf = f'<a href="file:///{pdf_path.replace(os.sep, "/")}" target="_blank"><button>Voir Résumé PDF</button></a>' if os.path.exists(pdf_path) else "❌"
            lien_bl = f'<a href="file:///{bl_path.replace(os.sep, "/")}" target="_blank"><button>Voir BL</button></a>' if os.path.exists(bl_path) else "❌"
            lien_ocst = f'<a href="file:///{ocst_path.replace(os.sep, "/")}" target="_blank"><button>Voir OCST</button></a>' if os.path.exists(ocst_path) else "❌"

            tableau.append([
                row["id"], row["date"], row["commande"], row["bl_num"], row["depot"],
                row["transporteur_id"], row["tracteur"], row["citerne"], row["chauffeur"],
                vol_super, vol_diesel, vol_petrole, total_l,
                manq_super, manq_diesel, manq_petrole, total_m,
                val_super, val_diesel, val_petrole, total_x, lien_pdf, lien_bl, lien_ocst
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
            ("PIÈCES JOINTES", "Résumé PDF"), ("PIÈCES JOINTES", "BL"), ("PIÈCES JOINTES", "OCST")
        ])

        df_all = pd.DataFrame(tableau, columns=columns)

        # ✅ Filtres avec champ de saisie + selectbox
        st.markdown("### 🔎 Filtres par colonne")
        colonnes_info = [
            ("INFORMATION GÉNÉRALE", "Id"),
            ("INFORMATION GÉNÉRALE", "Commande"),
            ("INFORMATION GÉNÉRALE", "BL"),
            ("INFORMATION GÉNÉRALE", "Dépôt"),
            ("INFORMATION GÉNÉRALE", "Transporteur"),
            ("INFORMATION GÉNÉRALE", "Tracteur"),
            ("INFORMATION GÉNÉRALE", "Citerne"),
            ("INFORMATION GÉNÉRALE", "Chauffeur")
        ]

        colonnes_streamlit = st.columns(len(colonnes_info))
        choix_filtres = {}
        for i, col_tuple in enumerate(colonnes_info):
            with colonnes_streamlit[i]:
                st.markdown(f"**{col_tuple[1]}**")
                saisie = st.text_input(f"Recherche {col_tuple[1]}", key=f"search_{col_tuple[1]}")
                options = sorted(df_all[col_tuple].dropna().unique())
                if saisie:
                    options = [opt for opt in options if saisie.lower() in str(opt).lower()]
                choix = st.selectbox(f"Sélection {col_tuple[1]}", [""] + options, key=f"select_{col_tuple[1]}")
                if choix:
                    choix_filtres[col_tuple] = choix

        if st.button("🔍 Appliquer les filtres"):
            for col_tuple, choix in choix_filtres.items():
                if choix:
                    df_all = df_all[df_all[col_tuple] == choix]
        # ✅ Export Excel sans PIÈCES JOINTES
        buffer = BytesIO()
        import xlsxwriter
        from collections import defaultdict

        # Exclure les colonnes PIÈCES JOINTES
        df_export = df_all[[col for col in df_all.columns if col[0] != "PIÈCES JOINTES"]]

        workbook = xlsxwriter.Workbook(buffer)
        worksheet = workbook.add_worksheet("RECAP")

        # Couleurs par grandes catégories
        couleurs = {
            "INFORMATION GÉNÉRALE": ("#B7DEE8", "#DCEEF4"),
            "VOLUME LIVRÉ": ("#FCD5B4", "#FDE9D9"),
            "MANQUANT EN LITRE": ("#FFF2CC", "#FFF9E5"),
            "MANQUANT EN XOF": ("#D9D2E9", "#EDEAF5"),
        }

        formats_header, formats_sub = {}, {}
        for cat, (bg_header, bg_sub) in couleurs.items():
            formats_header[cat] = workbook.add_format({
                "bold": True, "align": "center", "valign": "vcenter",
                "border": 1, "bg_color": bg_header
            })
            formats_sub[cat] = workbook.add_format({
                "bold": True, "align": "center", "valign": "vcenter",
                "border": 1, "bg_color": bg_sub
            })

        format_cell_gauche = workbook.add_format({"align": "left", "valign": "vcenter", "border": 1})
        format_cell_centre = workbook.add_format({"align": "center", "valign": "vcenter", "border": 1})
        format_cell_droite = workbook.add_format({"align": "right", "valign": "vcenter", "border": 1})

        # ✅ Regrouper les colonnes par catégorie
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

                if cat in ["VOLUME LIVRÉ", "MANQUANT EN XOF"]:
                    fmt.set_num_format("# ##0")
                    try:
                        worksheet.write_number(row_idx + 2, col_idx, float(val) if val != "" else 0, fmt)
                    except:
                        worksheet.write(row_idx + 2, col_idx, str(val), fmt)
                else:
                    worksheet.write(row_idx + 2, col_idx, val, fmt)

        # ✅ Ajuster largeur des colonnes
        for i in range(col):
            worksheet.set_column(i, i, 18)

        workbook.close()
        buffer.seek(0)

        # ✅ Bouton de téléchargement Excel
        st.download_button(
            label="📥 Exporter en Excel",
            data=buffer,
            file_name="recap_manquant.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # ✅ Affichage enrichi du tableau dans Streamlit
        st.markdown("""
        <style>
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 6px 12px; text-align: left; white-space: nowrap; }
        </style>
        """, unsafe_allow_html=True)

        st.write(df_all.to_html(escape=False, index=False), unsafe_allow_html=True)

# -------------------- BLOC 5 — GESTION DES PRIX --------------------
def afficher_menu_prix():
    st.title("💰 GESTION DES PRIX")

    # Charger les produits depuis la base
    df_produits = pd.read_sql("SELECT id, nom FROM produits", engine)
    produits = dict(zip(df_produits["id"], df_produits["nom"]))

    # Choisir une date de référence
    date_ref = st.date_input("📅 Date de référence", value=datetime.today().date())
    st.subheader("📌 Prix en vigueur à la date choisie")

    # Afficher les prix en vigueur
    for pid, nom in produits.items():
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT prix FROM prix_vente
                WHERE produit_id = :pid AND date_debut <= :d AND date_fin >= :d
                ORDER BY date_modification DESC LIMIT 1
            """), {"pid": pid, "d": date_ref}).fetchone()

        if result:
            st.metric(nom, f"{int(result[0]):,} XOF".replace(",", " "))
        else:
            st.warning(f"❌ {nom} — Prix non disponible")

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
                with engine.begin() as conn:
                    # Vérifier conflit
                    conflit = conn.execute(text("""
                        SELECT id FROM prix_vente
                        WHERE produit_id = :pid AND date_debut <= :fin AND date_fin >= :deb
                    """), {"pid": produit_id, "fin": date_fin, "deb": date_debut}).fetchone()

                    if conflit:
                        st.warning(f"⚠️ Un prix existe déjà pour {nom_produit} sur cette plage.")
                        if st.button("✅ Confirmer la modification"):
                            conn.execute(text("DELETE FROM prix_vente WHERE id = :id"), {"id": conflit[0]})
                            conn.execute(text("""
                                INSERT INTO prix_vente (produit_id, prix, date_debut, date_fin, date_modification)
                                VALUES (:pid, :prix, :deb, :fin, :modif)
                            """), {"pid": produit_id, "prix": prix, "deb": str(date_debut), "fin": str(date_fin), "modif": datetime.now()})
                            st.success("✅ Prix modifié avec succès.")
                            st.session_state.show_form_prix = False
                            st.rerun()
                    else:
                        try:
                            with engine.begin() as conn:
                                conn.execute(text("""
                                    INSERT INTO prix_vente (produit_id, prix, date_debut, date_fin, date_modification)
                                    VALUES (:pid, :prix, :deb, :fin, :modif)
                                """), {
                                    "pid": produit_id,
                                    "prix": prix,
                                    "deb": date_debut,   # ✅ garder l'objet date
                                    "fin": date_fin,     # ✅ garder l'objet date
                                    "modif": datetime.now()
                                })
                            st.success("✅ Prix enregistré.")
                            st.session_state.show_form_prix = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de l'enregistrement : {e}")
                    
                        st.success("✅ Prix enregistré.")
                        st.session_state.show_form_prix = False
                        st.rerun()

    # Historique des prix
    st.subheader("📜 Historique des prix enregistrés")
    df_prix = pd.read_sql("""
        SELECT produit_id, prix, date_debut, date_fin, date_modification
        FROM prix_vente
        ORDER BY date_modification DESC
    """, engine)
    df_prix["Produit"] = df_prix["produit_id"].map(produits)
    df_prix = df_prix[["Produit", "prix", "date_debut", "date_fin", "date_modification"]]
    st.dataframe(df_prix, use_container_width=True)

# -------------------- BLOC 6 — MÉMO DE RÉGULARISATION --------------------
def afficher_menu_memo():
    st.title("📄 GÉNÉRATION DU MÉMO DE RÉGULARISATION")

    # ✅ Liste des mois en français (sans année figée)
    mois_options = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]

    # ✅ Dictionnaire de correspondance FR → EN pour datetime
    mois_map_fr_en = {
        "Janvier": "January", "Février": "February", "Mars": "March", "Avril": "April",
        "Mai": "May", "Juin": "June", "Juillet": "July", "Août": "August",
        "Septembre": "September", "Octobre": "October", "Novembre": "November", "Décembre": "December"
    }

    # ✅ Déterminer le mois courant
    from datetime import date
    aujourdhui = date.today()
    mois_courant_fr = mois_options[aujourdhui.month - 1]   # ex: "Décembre"
    annee_courante = aujourdhui.year

    # ✅ Sélecteur avec valeur par défaut = mois courant
    mois_selectionne = st.selectbox(
        "🗓️ Choisir le mois du mémo",
        mois_options,
        index=mois_options.index(mois_courant_fr),
        key="mois_memo"
    )

    # ✅ Construire la chaîne complète "Mois Année" pour la fonction generer_memo_mensuel
    mois_selectionne_complet = f"{mois_selectionne} {annee_courante}"

    if st.button("📄 Télécharger le mémo"):
        nom_fichier = generer_memo_mensuel(mois_selectionne_complet)
        if not os.path.isfile(nom_fichier):
            st.warning("📭 Aucune donnée disponible pour ce mois.")
        else:
            with open(nom_fichier, "rb") as f:
                st.download_button(
                    label="📥 Télécharger le fichier Word",
                    data=f,
                    file_name=nom_fichier,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            st.success(f"✅ Mémo généré pour {mois_selectionne_complet}")

    # ✅ Affichage des tableaux générés par la fonction
    df_transpo, df_sites = generer_memo_mensuel(mois_selectionne_complet, afficher=True)
    st.subheader("🚚 Montants par transporteur")
    st.dataframe(df_transpo, use_container_width=True)
    st.subheader("🏢 Montants par site")
    st.dataframe(df_sites, use_container_width=True)

# -------------------- BLOC 7 — GESTION DES COMPTES --------------------
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

    if st.button("✅ Ajouter l'utilisateur"):
        if not nouveau_nom or not nouveau_mdp:
            st.warning("⚠️ Veuillez remplir tous les champs.")
        else:
            hash_mdp = hashlib.sha256(nouveau_mdp.encode()).hexdigest()
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO utilisateurs (nom_utilisateur, mot_de_passe_clair, mot_de_passe_hash, role, transporteur_id)
                    VALUES (:nom, :mdp_clair, :mdp_hash, :role, :tid)
                """), {
                    "nom": nouveau_nom,
                    "mdp_clair": nouveau_mdp,
                    "mdp_hash": hash_mdp,
                    "role": nouveau_role,
                    "tid": None
                })
            st.success(f"✅ Utilisateur {nouveau_nom} ajouté avec succès.")

    st.subheader("🗂️ Utilisateurs existants")
    df_users = pd.read_sql("""
        SELECT id, nom_utilisateur, mot_de_passe_clair AS mot_de_passe, role
        FROM utilisateurs
        ORDER BY id ASC
    """, engine)
    st.dataframe(df_users, use_container_width=True)

    id_supprimer = st.text_input("🗑️ ID de l'utilisateur à supprimer")
    if st.button("❌ Supprimer l'utilisateur"):
        if not id_supprimer:
            st.warning("⚠️ Veuillez entrer un ID.")
        else:
            try:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM utilisateurs WHERE id = :id"), {"id": id_supprimer})
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

# ------------------------------FIN DU SCRIPT--------------------------