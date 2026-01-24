# database.py
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()
DB_URL = os.getenv("DB_URL")

# Connexion SQLAlchemy
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles
Base = declarative_base()

# Modèle Livraison (correspond à ta table livraison)
class Livraison(Base):
    __tablename__ = "livraison"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date)
    station_id = Column(String)   # utilisé dans ton endpoint /livraisons
    bl_num = Column(String)
    volume_livre = Column(Integer)
    volume_manquant = Column(Integer)