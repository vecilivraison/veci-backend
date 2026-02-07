from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from datetime import date
import shutil, os, json
from typing import List
from fpdf import FPDF
from database import SessionLocal, Livraison

# Google Cloud
from google.cloud import storage
from google.oauth2.credentials import Credentials

# 🔌 Connexion DB
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
# Utilitaires GCS avec ADC JSON
# -------------------------------
BUCKET_NAME = "veci-documents"

def get_storage_client():
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("Credentials not found in environment")
    creds_dict = json.loads(creds_json)

    # ✅ Utiliser Credentials.from_authorized_user_info pour ADC OAuth
    credentials = Credentials.from_authorized_user_info(creds_dict)

    return storage.Client(credentials=credentials, project=creds_dict.get("quota_project_id"))

def upload_to_gcs(file_path: str, destination_blob: str):
    client = get_storage_client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_blob)
    blob.upload_from_filename(file_path)

    # ✅ Avec UBLA + allUsers Storage Object Viewer
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{destination_blob}"

# -------------------------------
# Endpoints de base (commerciaux, sites, transporteurs, etc.)
# -------------------------------
@app.get("/commerciaux")
def get_commerciaux():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom_prenom FROM commerciaux")).mappings().all()
        return list(result)

@app.get("/sites")
def get_sites(commercial_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, nom_site FROM sites WHERE commercial_id = :cid")
        result = conn.execute(query, {"cid": commercial_id}).mappings().all()
        return list(result)

@app.get("/transporteurs")
def get_transporteurs():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM transporteurs")).mappings().all()
        return list(result)

# -------------------------------
# Chauffeurs
# -------------------------------
@app.get("/chauffeurs")
def get_chauffeurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, nom_chauffeur FROM chauffeurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Tracteurs
# -------------------------------
@app.get("/tracteurs")
def get_tracteurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT tracteur_id, tracteur FROM tracteurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Citernes
# -------------------------------
@app.get("/citernes")
def get_citernes(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, num_citerne FROM citernes WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

# -------------------------------
# Produits
# -------------------------------
@app.get("/produits")
def get_produits():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM produits")).mappings().all()
        return list(result)

# -------------------------------
# Dépôts
# -------------------------------
@app.get("/depots")
def get_depots():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM depots")).mappings().all()
        return list(result)
# Chauffeurs
@app.post("/chauffeurs")
async def create_chauffeur(nom_chauffeur: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(id FROM 3) AS INTEGER)) FROM chauffeurs")
        ).scalar()
        new_id = "CH1" if last_num is None else f"CH{last_num + 1}"
        conn.execute(
            text("INSERT INTO chauffeurs (id, nom_chauffeur, transporteur_id) VALUES (:id, :nom, :tid)"),
            {"id": new_id, "nom": nom_chauffeur, "tid": transporteur_id}
        )
        return {"id": new_id, "nom_chauffeur": nom_chauffeur}

# Citernes
@app.post("/citernes")
async def create_citerne(num_citerne: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(id FROM 4) AS INTEGER)) FROM citernes")
        ).scalar()
        new_id = "CIT1" if last_num is None else f"CIT{last_num + 1}"
        conn.execute(
            text("INSERT INTO citernes (id, num_citerne, transporteur_id) VALUES (:id, :num, :tid)"),
            {"id": new_id, "num": num_citerne, "tid": transporteur_id}
        )
        return {"id": new_id, "num_citerne": num_citerne}

# Tracteurs
@app.post("/tracteurs")
async def create_tracteur(tracteur: str = Form(...), transporteur_id: str = Form(...)):
    with engine.begin() as conn:
        last_num = conn.execute(
            text("SELECT MAX(CAST(SUBSTRING(tracteur_id FROM 5) AS INTEGER)) FROM tracteurs")
        ).scalar()
        new_id = "TRAC1" if last_num is None else f"TRAC{last_num + 1}"
        conn.execute(
            text("INSERT INTO tracteurs (tracteur_id, tracteur, transporteur_id) VALUES (:id, :tr, :tid)"),
            {"id": new_id, "tr": tracteur, "tid": transporteur_id}
        )
        return {"tracteur_id": new_id, "tracteur": tracteur}

# -------------------------------
# Upload BL / OCST vers GCS
# -------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload/bl")
async def upload_bl(file: UploadFile = File(...)):
    local_path = f"{UPLOAD_DIR}/bl_{file.filename}"
    with open(local_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    gcs_url = upload_to_gcs(local_path, f"bl/{file.filename}")
    return {"gcs_url": gcs_url}

@app.post("/upload/ocst")
async def upload_ocst(file: UploadFile = File(...)):
    local_path = f"{UPLOAD_DIR}/ocst_{file.filename}"
    with open(local_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    gcs_url = upload_to_gcs(local_path, f"ocst/{file.filename}")
    return {"gcs_url": gcs_url}
# -------------------------------
# Endpoint : Livraison
# -------------------------------
@app.post("/livraison")
async def create_livraison(
    commercial_id: str = Form(...),
    site_id: str = Form(...),
    transporteur_id: str = Form(...),
    chauffeur_id: str = Form(...),
    tracteur_id: str = Form(...),
    citerne_id: str = Form(...),
    depot_id: str = Form(...),
    date: str = Form(...),
    commande: str = Form(...),
    bl_num: str = Form(...),
    volume_total: str = Form(...),
    manquant_remboursable: str = Form(...),
    compartiments: str = Form(...),
    bl: UploadFile = File(None),
    ocst: UploadFile = File(None),
):
    bl_path, ocst_path = None, None

    if bl:
        local_bl = f"{UPLOAD_DIR}/bl_{bl.filename}"
        with open(local_bl, "wb") as buffer:
            shutil.copyfileobj(bl.file, buffer)
        bl_path = upload_to_gcs(local_bl, f"bl/{bl.filename}")

    if ocst:
        local_ocst = f"{UPLOAD_DIR}/ocst_{ocst.filename}"
        with open(local_ocst, "wb") as buffer:
            shutil.copyfileobj(ocst.file, buffer)
        ocst_path = upload_to_gcs(local_ocst, f"ocst/{ocst.filename}")

    with engine.begin() as conn:
        # ... vérifications chauffeur/tracteur/citerne
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
            "chauffeur": chauffeur_id,
            "tracteur": tracteur_id,
            "citerne": citerne_id,
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

    return {"id": livraison_id, "doc_bl": bl_path, "doc_ocst": ocst_path}

# -------------------------------
# Génération résumé PDF vers GCS
# -------------------------------
@app.get("/livraisons/pdf")
def generer_resume_pdf(bl: str):
    with engine.connect() as conn:
        # 🔍 Récupération de la livraison
        livraison = conn.execute(
            text("""SELECT id, date, site_id, transporteur_id, chauffeur, tracteur, citerne,
                    commande, bl_num
                    FROM livraison WHERE bl_num = :bl"""),
            {"bl": bl}
        ).mappings().first()

        if not livraison:
            return {"error": f"Livraison introuvable pour BL {bl}"}

        # 🔍 Récupération des noms liés
        site = conn.execute(text("SELECT nom_site FROM sites WHERE id = :sid"),
                            {"sid": livraison["site_id"]}).scalar()
        transporteur = conn.execute(text("SELECT nom FROM transporteurs WHERE id = :tid"),
                                    {"tid": livraison["transporteur_id"]}).scalar()

        # ✅ Traduction des IDs en noms
        chauffeur_nom = conn.execute(
            text("SELECT nom_chauffeur FROM chauffeurs WHERE id = :cid"),
            {"cid": livraison["chauffeur"]}
        ).scalar()

        tracteur_nom = conn.execute(
            text("SELECT tracteur FROM tracteurs WHERE tracteur_id = :tid"),
            {"tid": livraison["tracteur"]}
        ).scalar()

        citerne_nom = conn.execute(
            text("SELECT num_citerne FROM citernes WHERE id = :iid"),
            {"iid": livraison["citerne"]}
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
            ("CITERNE", citerne_nom),
            ("TRACTEUR", tracteur_nom),
            ("CHAUFFEUR", chauffeur_nom),
        ]

        pdf.set_font("Arial", "B", 10)
        for libelle, desc in infos:
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

        # 📁 Sauvegarde locale
        filename = f"Livraison_{livraison['bl_num']}.pdf"
        pdf_path = f"{UPLOAD_DIR}/{filename}"
        pdf.output(pdf_path)

        # 🚀 Upload vers GCS et retour de l’URL publique
        gcs_url = upload_to_gcs(pdf_path, f"resume/{filename}")
        return {"resume_pdf_url": gcs_url}

# -------------------------------
# Récupération livraisons
# -------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/livraisons")
def get_livraisons(site_id: str, date_debut: date = Query(...), date_fin: date = Query(...), db: Session = Depends(get_db)):
    livraisons = (
        db.query(Livraison)
        .filter(Livraison.site_id == site_id, Livraison.date >= date_debut, Livraison.date <= date_fin)
        .all()
    )
    return [
        {
            "id": l.id,
            "date": l.date.isoformat(),
            "bl_num": l.bl_num,
            "volume_livre": l.volume_livre,
            "volume_manquant": l.volume_manquant,
            "resume_pdf_url": f"/livraisons/{l.id}/resume_pdf"
        }
        for l in livraisons
    ]