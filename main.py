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

    # ✅ Générer une URL signée valable 1h
    url = blob.generate_signed_url(expiration=3600)
    return url

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
        livraison = conn.execute(
            text("SELECT id, date, site_id, transporteur_id, chauffeur, tracteur, citerne, commande, bl_num FROM livraison WHERE bl_num = :bl"),
            {"bl": bl}
        ).mappings().first()
        if not livraison:
            return {"error": f"Livraison introuvable pour BL {bl}"}

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(200, 10, txt=f"Résumé Livraison BL {livraison['bl_num']}", ln=True, align="C")

        filename = f"Livraison_{livraison['bl_num']}.pdf"
        pdf_path = f"{UPLOAD_DIR}/{filename}"
        pdf.output(pdf_path)

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