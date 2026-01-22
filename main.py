from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from fastapi import FastAPI, UploadFile, File
import shutil
from fastapi import UploadFile, File, Form
import shutil, os
from sqlalchemy import text
from fastapi import FastAPI, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import date
from typing import List

# 🔌 Connexion à la base
load_dotenv()
db_url = os.getenv("DB_URL")
engine = create_engine(db_url)

app = FastAPI()

# 🔓 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Endpoint : Commerciaux
# -------------------------------
@app.get("/commerciaux")
def get_commerciaux():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom_prenom FROM commerciaux")).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Sites (lié à un commercial)
# -------------------------------
@app.get("/sites")
def get_sites(commercial_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, nom_site FROM sites WHERE commercial_id = :cid")
        result = conn.execute(query, {"cid": commercial_id}).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Transporteurs
# -------------------------------
@app.get("/transporteurs")
def get_transporteurs():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM transporteurs")).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Chauffeurs (lié à un transporteur)
# -------------------------------
@app.get("/chauffeurs")
def get_chauffeurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, nom_chauffeur FROM chauffeurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Tracteurs (lié à un transporteur)
# -------------------------------
@app.get("/tracteurs")
def get_tracteurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT tracteur_id, tracteur FROM tracteurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Citernes (lié à un transporteur)
# -------------------------------
@app.get("/citernes")
def get_citernes(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, num_citerne FROM citernes WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Produits (liste déroulante)
# -------------------------------
@app.get("/produits")
def get_produits():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM produits")).mappings().all()
        return list(result)

# -------------------------------
# Endpoint : Dépôts de chargement (liste déroulante)
# -------------------------------
@app.get("/depots")
def get_depots():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM depots")).mappings().all()
        return list(result)

# Endpoint : Upload BL
# -------------------------------
@app.post("/upload/bl")
async def upload_bl(file: UploadFile = File(...)):
    save_path = f"uploads/bl_{file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"path": save_path}

# -------------------------------
# Endpoint : Upload OCST
# -------------------------------
@app.post("/upload/ocst")
async def upload_ocst(file: UploadFile = File(...)):
    save_path = f"uploads/ocst_{file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"path": save_path}

#------ Endpoint : post chauffeurs -------------------------------
@app.post("/chauffeurs")
async def create_chauffeur(nom_chauffeur: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        # Récupérer le dernier numéro en base
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(id FROM 3) AS INTEGER)) FROM chauffeurs")
        ).scalar()

        if last_num is None:
            new_id = "CH1"
        else:
            new_id = f"CH{last_num + 1}"

        # Insérer le nouveau chauffeur
        conn.execute(
            text("INSERT INTO chauffeurs (id, nom_chauffeur, transporteur_id) VALUES (:id, :nom, :tid)"),
            {"id": new_id, "nom": nom_chauffeur, "tid": transporteur_id}
        )

    return {"id": new_id, "nom_chauffeur": nom_chauffeur}

#-------------------------------

#------ Endpoint : post citernes -------------------------------
@app.post("/citernes")
async def create_citerne(num_citerne: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        # Récupérer le dernier numéro en base
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(id FROM 4) AS INTEGER)) FROM citernes")
        ).scalar()

        if last_num is None:
            new_id = "CIT1"
        else:
            new_id = f"CIT{last_num + 1}"

        conn.execute(
            text("INSERT INTO citernes (id, num_citerne, transporteur_id) VALUES (:id, :num, :tid)"),
            {"id": new_id, "num": num_citerne, "tid": transporteur_id}
        )

    return {"id": new_id, "num_citerne": num_citerne}
#-------------------------------

#------ Endpoint : post Tracteurs -------------------------------
@app.post("/tracteurs")
async def create_tracteur(tracteur: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        # Récupérer le dernier numéro en base
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(tracteur_id FROM 5) AS INTEGER)) FROM tracteurs")
        ).scalar()

        if last_num is None:
            new_id = "TRAC1"
        else:
            new_id = f"TRAC{last_num + 1}"

        conn.execute(
            text("INSERT INTO tracteurs (tracteur_id, tracteur, transporteur_id) VALUES (:id, :tr, :tid)"),
            {"id": new_id, "tr": tracteur, "tid": transporteur_id}
        )

    return {"tracteur_id": new_id, "tracteur": tracteur}
# -------------------------------

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/livraison")
async def create_livraison(
    commercial_id: str = Form(...),
    site_id: str = Form(...),
    transporteur_id: str = Form(...),
    chauffeur_id: str = Form(...),   # ID
    tracteur_id: str = Form(...),    # ID
    citerne_id: str = Form(...),     # ID
    depot_id: str = Form(...),
    date: str = Form(...),
    commande: str = Form(...),
    bl_num: str = Form(...),
    volume_total: str = Form(...),
    manquant_remboursable: str = Form(...),
    compartiments: str = Form(...),  # ✅ JSON string
    bl: UploadFile = File(None),
    ocst: UploadFile = File(None),
):
    bl_path, ocst_path = None, None

    # Sauvegarde BL
    if bl:
        bl_path = f"uploads/bl_{bl.filename}"
        with open(bl_path, "wb") as buffer:
            shutil.copyfileobj(bl.file, buffer)

    # Sauvegarde OCST
    if ocst:
        ocst_path = f"uploads/ocst_{ocst.filename}"
        with open(ocst_path, "wb") as buffer:
            shutil.copyfileobj(ocst.file, buffer)

    # ✅ Log pour vérifier la valeur reçue
    print("BL inséré:", bl_num)
    # ✅ Utilisation de engine.begin() pour une transaction complète
    with engine.begin() as conn:
        # Chauffeur
        ch = conn.execute(
            text("SELECT nom_chauffeur FROM chauffeurs WHERE id = :cid"),
            {"cid": chauffeur_id}
        ).scalar()
        if ch is None:
            raise ValueError("Chauffeur introuvable")

        # Tracteur
        tr = conn.execute(
            text("SELECT tracteur FROM tracteurs WHERE tracteur_id = :tid"),
            {"tid": tracteur_id}
        ).scalar()
        if tr is None:
            raise ValueError("Tracteur introuvable")

        # Citerne
        ci = conn.execute(
            text("SELECT num_citerne FROM citernes WHERE id = :iid"),
            {"iid": citerne_id}
        ).scalar()
        if ci is None:
            raise ValueError("Citerne introuvable")

        # 🔹 Insertion livraison
        result = conn.execute(text("""
            INSERT INTO livraison (
                commercial_id, site_id, transporteur_id, chauffeur,
                tracteur, citerne, depot, date,
                commande, bl_num, volume_total, manquant_remboursable,
                doc_bl, doc_ocst
            )
            VALUES (
                :commercial_id, :site_id, :transporteur_id, :chauffeur,
                :tracteur, :citerne, :depot, :date,
                :commande, :bl_num, :volume_total, :manquant_remboursable,
                :doc_bl, :doc_ocst
            )
            RETURNING id
        """), {
            "commercial_id": commercial_id,
            "site_id": site_id,
            "transporteur_id": transporteur_id,
            "chauffeur": ch,
            "tracteur": tr,
            "citerne": ci,
            "depot": depot_id,
            "date": date,
            "commande": commande,
            "bl_num": bl_num,
            "volume_total": int(volume_total),
            "manquant_remboursable": int(manquant_remboursable),
            "doc_bl": bl_path,
            "doc_ocst": ocst_path
        })
        livraison_id = result.scalar()

        # 🔹 Insertion compartiments
        import json
        compartiments_data = json.loads(compartiments)
        for c in compartiments_data:
            conn.execute(text("""
                INSERT INTO compartiments (
                    livraison_id, num_compartiment, produit_id,
                    volume_livre, volume_manquant, commentaire
                )
                VALUES (
                    :livraison_id, :num_compartiment, :produit_id,
                    :volume_livre, :volume_manquant, :commentaire
                )
            """), {
                "livraison_id": livraison_id,
                "num_compartiment": c["num_compartiment"],
                "produit_id": c["produit_id"],  # ✅ ID produit alphanumérique
                "volume_livre": c["volume_livre"],
                "volume_manquant": c["volume_manquant"],
                "commentaire": c["commentaire"],
            })

    return {
        "id": livraison_id,
        "doc_bl": bl_path,
        "doc_ocst": ocst_path
    }

from fastapi.responses import FileResponse
from fpdf import FPDF


@app.get("/livraisons/pdf")
def generer_resume_pdf(bl: str):
    # Log pour vérifier la valeur reçue
    print("BL reçu:", bl)

    with engine.connect() as conn:
        # 🔍 Récupération de la livraison
        livraison = conn.execute(
            text("""SELECT id, date, site_id, transporteur_id, chauffeur, tracteur, citerne,
                           commande, bl_num, volume_total, manquant_remboursable, doc_bl, doc_ocst
                    FROM livraison WHERE bl_num = :bl"""),
            {"bl": bl}
        ).mappings().first()

        if not livraison:
            return {"error": f"Livraison introuvable pour BL {bl}"}

        # 🔍 Récupération des noms liés
        site = conn.execute(
            text("SELECT nom_site FROM sites WHERE id = :sid"),
            {"sid": livraison["site_id"]}
        ).scalar()
        transporteur = conn.execute(
            text("SELECT nom FROM transporteurs WHERE id = :tid"),
            {"tid": livraison["transporteur_id"]}
        ).scalar()

        # 🔍 Récupération des compartiments
        compartiments = conn.execute(
            text("""SELECT c.num_compartiment, p.nom AS produit, 
                           c.volume_livre, c.volume_manquant, c.commentaire
                    FROM compartiments c
                    JOIN produits p ON c.produit_id = p.id
                    WHERE c.livraison_id = :lid"""),
            {"lid": livraison["id"]}
        ).mappings().all()

        # 🔢 Calcul des totaux par produit
        totaux = {}
        for c in compartiments:
            produit = c["produit"]
            if produit not in totaux:
                totaux[produit] = {"volume": 0, "manquant": 0}
            totaux[produit]["volume"] += c["volume_livre"]
            if c["commentaire"] == "Remboursable":
                totaux[produit]["manquant"] += c["volume_manquant"]

    # 📄 Création du PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt=f"RÉSUMÉ LIVRAISON BL {livraison['bl_num']}", ln=True, align="C")
    pdf.ln(5)

    # 🟧 Partie 1 : Informations générales
    pdf.set_fill_color(255, 204, 153)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(200, 10, txt="PARTIE 1 : INFORMATIONS GÉNÉRALES", ln=True, fill=True)
    pdf.ln(3)

    infos = [
        ("DATE DE LIVRAISON", livraison["date"]),
        ("SITE", site),
        ("NUMÉRO DE COMMANDE", livraison["commande"]),
        ("NUMÉRO DE BL", livraison["bl_num"]),
        ("TRANSPORTEUR", transporteur),
        ("CITERNE", livraison["citerne"]),
        ("TRACTEUR", livraison["tracteur"]),
        ("CHAUFFEUR", livraison["chauffeur"]),
    ]

    pdf.set_font("Arial", "B", 10)
    for libelle, desc in infos:
        pdf.set_fill_color(255, 204, 153)
        pdf.cell(60, 10, libelle, 1, 0, 'L', True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(130, 10, str(desc), 1, ln=True)

    pdf.ln(5)

    # 🟧 Partie 2 : Détail livraison
    pdf.set_font("Arial", "B", 12)
    pdf.set_fill_color(255, 204, 153)
    pdf.cell(200, 10, txt="PARTIE 2 : DÉTAIL LIVRAISON", ln=True, fill=True)
    pdf.ln(3)

    headers = ["NUM_CPT", "PRODUIT", "VOLUME (L)", "MANQUANT (L)", "COMMENTAIRE"]
    widths = [30, 50, 40, 40, 30]

    pdf.set_font("Arial", "B", 10)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 10, h, 1, 0, 'C', True)
    pdf.ln()

    pdf.set_font("Arial", "", 10)
    for c in compartiments:
        pdf.cell(widths[0], 10, str(c["num_compartiment"]), 1)
        pdf.cell(widths[1], 10, str(c["produit"]), 1)
        pdf.cell(widths[2], 10, str(c["volume_livre"]), 1)
        pdf.cell(widths[3], 10, str(c["volume_manquant"]), 1)
        pdf.cell(widths[4], 10, str(c["commentaire"]), 1)
        pdf.ln()

    pdf.ln(5)

    # 🟧 Partie 3 : Totaux par produit
    pdf.set_font("Arial", "B", 12)
    pdf.set_fill_color(255, 204, 153)
    pdf.cell(200, 10, txt="PARTIE 3 : TOTAL LIVRÉ / MANQUANT REMBOURSABLE", ln=True, fill=True)
    pdf.ln(3)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(70, 10, "PRODUIT", 1, 0, 'C', True)
    pdf.cell(60, 10, "VOLUME LIVRÉ (L)", 1, 0, 'C', True)
    pdf.cell(60, 10, "MANQUANT REMBOURSABLE", 1, ln=True, fill=True)

    pdf.set_font("Arial", "", 10)
    total_volume = 0
    total_manquant = 0
    for produit, data in totaux.items():
        pdf.cell(70, 10, produit, 1)
        pdf.cell(60, 10, str(data["volume"]), 1)
        pdf.cell(60, 10, str(data["manquant"]), 1)
        pdf.ln()
        total_volume += data["volume"]
        total_manquant += data["manquant"]

    pdf.set_font("Arial", "B", 10)
    pdf.cell(70, 10, "TOTAL", 1)
    pdf.cell(60, 10, str(total_volume), 1)
    pdf.cell(60, 10, str(total_manquant), 1)
    pdf.ln(10)

    # 📁 Sauvegarde
    filename = f"Livraison_{site}_BL {livraison['bl_num']} du {livraison['date']}.pdf"
    pdf_path = f"uploads/{filename}"
    pdf.output(pdf_path)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": "attachment"}
    )

# -------------------------------
# Endpoint : Visualisation des livraisons
# -------------------------------
@app.get("/livraisons")
def get_livraisons(
    site_id: str,   # ✅ remplacer station_id par site_id
    date_debut: date = Query(...),
    date_fin: date = Query(...),
):
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, date, bl_num,
                       volume_total AS volume_livre,
                       manquant_remboursable AS volume_manquant
                FROM livraison
                WHERE site_id = :sid   -- ✅ utiliser site_id
                  AND date BETWEEN :d1 AND :d2
                ORDER BY date ASC
            """)
            result = conn.execute(query, {"sid": site_id, "d1": date_debut, "d2": date_fin}).mappings().all()

            livraisons = []
            for r in result:
                date_val = r["date"]
                if hasattr(date_val, "isoformat"):
                    date_str = date_val.isoformat()
                else:
                    date_str = str(date_val) if date_val else None

                livraisons.append({
                    "id": r["id"],
                    "date": date_str,
                    "bl_num": r["bl_num"],
                    "volume_livre": r.get("volume_livre", 0),
                    "volume_manquant": r.get("volume_manquant", 0),
                    "resume_pdf_url": f"/livraisons/pdf?bl={r['bl_num']}"
                })
            return livraisons

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {e}")

# -------------------------------