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
    df_p = df[df["produit"] == produit_id]
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

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        date_debut = st.date_input("📅 Date de début", value=datetime.today())
    with col2:
        date_fin = st.date_input("📅 Date de fin", value=datetime.today())
    with col3:
        afficher = st.button("🔍 Afficher")

    # Charger les données
    df_liv = pd.read_sql("SELECT * FROM livraison", engine)
    df_comp = pd.read_sql("SELECT * FROM compartiments", engine)

    if st.session_state["utilisateur"]["role"] == "transporteur":
        df_liv = df_liv[df_liv["transporteur_id"] == st.session_state["utilisateur"]["transporteur_id"]]

    if afficher:
        df_liv["date"] = pd.to_datetime(df_liv["date"]).dt.date
        df_liv = df_liv[(df_liv["date"] >= date_debut) & (df_liv["date"] <= date_fin)]

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

            tableau.append([row["id"], row["date"], row["commande"], row["bl"], row["depot"],
                            row["transporteur_id"], row["tracteur"], row["citerne"], row["chauffeur"],
                            vol_super, vol_diesel, vol_petrole, total_l,
                            manq_super, manq_diesel, manq_petrole, total_m,
                            val_super, val_diesel, val_petrole, total_x])

        df_all = pd.DataFrame(tableau, columns=[
            "Id", "Date", "Commande", "BL", "Dépôt", "Transporteur",
            "Tracteur", "Citerne", "Chauffeur",
            "Super (L)", "Diesel (L)", "Pétrole (L)", "Total (L)",
            "Super manquant", "Diesel manquant", "Pétrole manquant", "Total manquant",
            "Super (XOF)", "Diesel (XOF)", "Pétrole (XOF)", "Total (XOF)"
        ])

        st.dataframe(df_all, use_container_width=True)

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

    mois_options = [
        "Janvier 2025", "Février 2025", "Mars 2025", "Avril 2025", "Mai 2025", "Juin 2025",
        "Juillet 2025", "Août 2025", "Septembre 2025", "Octobre 2025", "Novembre 2025", "Décembre 2025"
    ]
    mois_selectionne = st.selectbox("🗓️ Choisir le mois du mémo", mois_options, key="mois_memo")

    if st.button("📄 Télécharger le mémo"):
        nom_fichier = generer_memo_mensuel(mois_selectionne)
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
            st.success(f"✅ Mémo généré pour {mois_selectionne}")

    # ✅ Affichage des tableaux générés par la fonction
    df_transpo, df_sites = generer_memo_mensuel(mois_selectionne, afficher=True)
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