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
from google.cloud import storage   # ✅ ajout pour GCS

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
# Utilitaires GCS
# -------------------------------
BUCKET_NAME = "veci-documents"  # ⚠️ remplace par ton bucket

def upload_to_gcs(file_path: str, destination_blob: str):
    client = storage.Client()  # ADC utilise ton compte configuré
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_blob)
    blob.upload_from_filename(file_path)
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{destination_blob}"

# -------------------------------
# Commerciaux / Sites / Transporteurs / Chauffeurs / Tracteurs / Citernes / Produits / Dépôts
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

@app.get("/chauffeurs")
def get_chauffeurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, nom_chauffeur FROM chauffeurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

@app.get("/tracteurs")
def get_tracteurs(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT tracteur_id, tracteur FROM tracteurs WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

@app.get("/citernes")
def get_citernes(transporteur_id: str):
    with engine.connect() as conn:
        query = text("SELECT id, num_citerne FROM citernes WHERE transporteur_id = :tid")
        result = conn.execute(query, {"tid": transporteur_id}).mappings().all()
        return list(result)

@app.get("/produits")
def get_produits():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM produits")).mappings().all()
        return list(result)

@app.get("/depots")
def get_depots():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, nom FROM depots")).mappings().all()
        return list(result)

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
        ch = conn.execute(text("SELECT nom_chauffeur FROM chauffeurs WHERE id = :cid"), {"cid": chauffeur_id}).scalar()
        tr = conn.execute(text("SELECT tracteur FROM tracteurs WHERE tracteur_id = :tid"), {"tid": tracteur_id}).scalar()
        ci = conn.execute(text("SELECT num_citerne FROM citernes WHERE id = :iid"), {"iid": citerne_id}).scalar()

        if ch is None: raise ValueError("Chauffeur introuvable")
        if tr is None: raise ValueError("Tracteur introuvable")
        if ci is None: raise ValueError("Citerne introuvable")

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

        # 🔹 Insertion des compartiments
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
                "produit_id": c["produit_id"],
                "volume_livre": c["volume_livre"],
                "volume_manquant": c["volume_manquant"],
                "commentaire": c["commentaire"],
            })

    return {
        "id": livraison_id,
        "doc_bl": bl_path,
        "doc_ocst": ocst_path
    }

# -------------------------------
# Génération résumé PDF vers GCS
# -------------------------------
@app.get("/livraisons/pdf")
def generer_resume_pdf(bl: str):
    with engine.connect() as conn:
        livraison = conn.execute(
            text("""SELECT id, date, site_id, transporteur_id, chauffeur, tracteur, citerne,
                    commande, bl_num, volume_total, manquant_remboursable, doc_bl, doc_ocst
                    FROM livraison WHERE bl_num = :bl"""),
            {"bl": bl}
        ).mappings().first()

        if not livraison:
            return {"error": f"Livraison introuvable pour BL {bl}"}

        site = conn.execute(text("SELECT nom_site FROM sites WHERE id = :sid"), {"sid": livraison["site_id"]}).scalar()
        transporteur = conn.execute(text("SELECT nom FROM transporteurs WHERE id = :tid"), {"tid": livraison["transporteur_id"]}).scalar()

        compartiments = conn.execute(
            text("""SELECT c.num_compartiment, p.nom AS produit,
                    c.volume_livre, c.volume_manquant, c.commentaire
                    FROM compartiments c
                    JOIN produits p ON c.produit_id = p.id
                    WHERE c.livraison_id = :lid"""),
            {"lid": livraison["id"]}
        ).mappings().all()

        # 🔢 Totaux
        totaux = {}
        for c in compartiments:
            produit = c["produit"]
            if produit not in totaux:
                totaux[produit] = {"volume": 0, "manquant": 0}
            totaux[produit]["volume"] += c["volume_livre"]
            if c["commentaire"] == "Remboursable":
                totaux[produit]["manquant"] += c["volume_manquant"]

        # 📄 PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(200, 10, txt=f"RÉSUMÉ LIVRAISON BL {livraison['bl_num']}", ln=True, align="C")

        # ... (génération identique à ton script original)

        filename = f"Livraison_{site}_BL {livraison['bl_num']} du {livraison['date']}.pdf"
        pdf_path = f"{UPLOAD_DIR}/{filename}"
        pdf.output(pdf_path)

        gcs_url = upload_to_gcs(pdf_path, f"resume/{filename}")
        return {"resume_pdf_url": gcs_url}

# -------------------------------
# Dépendance DB et récupération livraisons
# -------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/livraisons")
def get_livraisons(
    station_id: str,
    date_debut: date = Query(...),
    date_fin: date = Query(...),
    db: Session = Depends(get_db)
):
    try:
        livraisons = (
            db.query(Livraison)
            .filter(
                Livraison.station_id == station_id,
                Livraison.date >= date_debut,
                Livraison.date <= date_fin,
            )
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
