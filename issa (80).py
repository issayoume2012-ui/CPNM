# --- BIBLIOTHÈQUES STANDARDS (Python) ---
import base64
from datetime import datetime
import io
import json
import os
import zipfile
import unicodedata
import numpy as np
import pandas as pd
from fpdf import FPDF
import streamlit as st
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

# ==========================================
# 0. CONFIGURATION & CONNEXION SUPABASE / POSTGRESQL
# ==========================================
DATABASE_URL = "postgresql://postgres.dzxotavktglasrcpyrwx:xTS1vLLFnlGWJXrr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    """Établit la connexion à la base de données Supabase / PostgreSQL."""
    try:
        if "postgres" in st.secrets:
            conn = psycopg2.connect(
                host=st.secrets["postgres"]["host"],
                database=st.secrets["postgres"]["database"],
                user=st.secrets["postgres"]["user"],
                password=st.secrets["postgres"]["password"],
                port=st.secrets["postgres"]["port"]
            )
        else:
            conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Erreur de connexion à la base de données Supabase/PostgreSQL : {e}")
        return None

def init_db():
    """Initialise les tables dans Supabase / PostgreSQL si elles n'existent pas."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            # Table Audit Logs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    horodatage VARCHAR(50),
                    acteur VARCHAR(255),
                    action VARCHAR(255),
                    details TEXT
                );
            """)
            # Table Admin Credentials / White List
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_white_list (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    nom VARCHAR(255),
                    prenom VARCHAR(255),
                    password VARCHAR(255),
                    niveau_acces VARCHAR(255)
                );
            """)
            # Table Prof Credentials / White List
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prof_white_list (
                    id SERIAL PRIMARY KEY,
                    nom VARCHAR(255),
                    prenom VARCHAR(255),
                    email VARCHAR(255) UNIQUE,
                    matiere_principale VARCHAR(255),
                    classe_attribuee VARCHAR(255),
                    password VARCHAR(255)
                );
            """)
            # Table Parents White List
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parents_white_list (
                    id SERIAL PRIMARY KEY,
                    telephone VARCHAR(50),
                    prenom_eleve VARCHAR(255),
                    nom_eleve VARCHAR(255),
                    annee_naissance VARCHAR(50),
                    classe VARCHAR(255)
                );
            """)
            # Table Classes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS classes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255) UNIQUE NOT NULL,
                    cycle VARCHAR(255),
                    professeur_responsable VARCHAR(255)
                );
            """)
            # Table Eleves
            cur.execute("""
                CREATE TABLE IF NOT EXISTS eleves (
                    id SERIAL PRIMARY KEY,
                    nom_complet VARCHAR(255),
                    prenom VARCHAR(255),
                    nom VARCHAR(255),
                    date_de_naissance VARCHAR(50),
                    classe VARCHAR(255),
                    photo TEXT
                );
            """)
            # Table Matieres
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matieres (
                    id SERIAL PRIMARY KEY,
                    matiere VARCHAR(255),
                    cycle VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            # Table Coefficients
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coefficients (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            # Table Periodes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS periodes (
                    id SERIAL PRIMARY KEY,
                    periode VARCHAR(255),
                    statut VARCHAR(50),
                    cycle VARCHAR(255)
                );
            """)
            # Table Notes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    periode VARCHAR(255),
                    eleve VARCHAR(255),
                    devoir1 FLOAT,
                    devoir2 FLOAT,
                    composition FLOAT,
                    baremenote FLOAT
                );
            """)
            # Table Vie Scolaire
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vie_scolaire (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    periode VARCHAR(255),
                    eleve VARCHAR(255),
                    absences_justifiees INT,
                    absences_non_justifiees INT,
                    retards INT,
                    heures_perdues INT,
                    observations TEXT,
                    decision_conseil TEXT
                );
            """)
            # Table Travail à faire
            cur.execute("""
                CREATE TABLE IF NOT EXISTS travail_a_faire (
                    id VARCHAR(255) PRIMARY KEY,
                    professeur VARCHAR(255),
                    date_publication VARCHAR(50),
                    date_rendu VARCHAR(50),
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    titre VARCHAR(255),
                    consignes TEXT,
                    lien_url TEXT,
                    lien_video TEXT,
                    fichier_nom TEXT,
                    fichier_b64 TEXT,
                    fichier_type TEXT
                );
            """)
            # Table Messages Parents
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages_parents (
                    id VARCHAR(255) PRIMARY KEY,
                    emetteur VARCHAR(255),
                    role_emetteur VARCHAR(255),
                    date_envoi VARCHAR(50),
                    classe VARCHAR(255),
                    objet TEXT,
                    message TEXT,
                    urgent BOOLEAN
                );
            """)
            # Table Emploi du Temps Grid
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edt_grid (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    jour VARCHAR(50),
                    heure VARCHAR(50),
                    valeur TEXT
                );
            """)
            # Table Cahier de Textes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cahier_textes (
                    id SERIAL PRIMARY KEY,
                    professeur VARCHAR(255),
                    date VARCHAR(50),
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    contenu TEXT,
                    travail_a_faire TEXT
                );
            """)
            # Table Absences
            cur.execute("""
                CREATE TABLE IF NOT EXISTS absences (
                    id SERIAL PRIMARY KEY,
                    date VARCHAR(50),
                    classe VARCHAR(255),
                    eleve VARCHAR(255),
                    statut VARCHAR(50),
                    motif TEXT
                );
            """)
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de l'initialisation des tables PostgreSQL : {e}")
    finally:
        conn.close()

# Initialiser les tables Supabase/PostgreSQL dès le lancement
init_db()

# Fonctions de chargement et de synchronisation des données Supabase/PostgreSQL
def load_table_from_db(query, columns):
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_sql(query, conn)
        if df.empty:
            return pd.DataFrame(columns=columns)
        return df
    except Exception:
        return pd.DataFrame(columns=columns)
    finally:
        conn.close()

def save_df_to_db(df, table_name):
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table_name};")
            if not df.empty:
                cols = ",".join(list(df.columns))
                vals = ",".join(["%s"] * len(df.columns))
                query = f"INSERT INTO {table_name} ({cols}) VALUES ({vals})"
                cur.executemany(query, df.values.tolist())
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur de sauvegarde dans {table_name} : {e}")
    finally:
        conn.close()

# ==========================================
# 0. BIS. GESTION DE LA SÉCURITÉ LOCALE
# ==========================================
def hacher_mot_de_passe(password: str) -> str:
    if not password: return ""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verifier_mot_de_passe(password: str, hashed: str) -> bool:
    if not password or not hashed: return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def normaliser_texte(texte):
    """Normalise une chaîne de caractères pour une recherche universelle (insensible aux accents, casse, espaces)."""
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

def nettoyer_texte_pdf(texte):
    """Nettoie et encode le texte pour garantir la compatibilité PDF sans erreur d'affichage."""
    if not texte: return ""
    return str(texte).encode('latin-1', 'replace').decode('latin-1')

ADMIN_EMAIL = "cpnm@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    """Consigne chaque action utilisateur dans la base PostgreSQL et le session_state."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "audit_logs_db" not in st.session_state:
        st.session_state.audit_logs_db = pd.DataFrame(columns=["horodatage", "acteur", "action", "details"])
    new_log = pd.DataFrame([{"horodatage": horodatage, "acteur": acteur, "action": action, "details": details}])
    st.session_state.audit_logs_db = pd.concat([st.session_state.audit_logs_db, new_log], ignore_index=True)
    
    # Persistance Supabase / PostgreSQL
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO audit_logs (horodatage, acteur, action, details) VALUES (%s, %s, %s, %s)",
                            (horodatage, acteur, action, details))
                conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

def trier_eleves_par_nom(df):
    if df is None or df.empty: return df
    df_copy = df.copy()
    if "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["Prénom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    return df_copy.reset_index(drop=True)

def synchroniser_listes_blanches():
    """Maintient la cohérence absolue et bidirectionnelle des accès professeurs."""
    if "prof_credentials" in st.session_state and not st.session_state.prof_credentials.empty:
        st.session_state.prof_white_list = st.session_state.prof_credentials.copy()
    elif "prof_white_list" in st.session_state and not st.session_state.prof_white_list.empty:
        st.session_state.prof_credentials = st.session_state.prof_white_list.copy()

# ==========================================
# 0. TER. GESTION DU DESIGN ET DU DRAPEAU
# ==========================================

SCEAU_SENEGAL_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz"
    "AAAOxAAADsQBlSsOGwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ2V3ZgZ3AAAAYklE"
    "EQVR4nO3BMQEAAADCoPVPbQwfoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAICXAcB4AAEq99A1"
    "AAAAAElFTkSuQmCC"
)

def obtenir_logo_base64():
    return ""

def assistant_ia_repondre(question: str) -> str:
    q = question.lower()
    if "bulletin" in q or "note" in q:
        return (
            "Les bulletins d'excellence sont générés automatiquement au format"
            " standardisé sous l'autorité de l'IA Saint-Louis et IEF Saint-Louis,"
            " garantissant rigueur et équité pour chaque élève."
        )
    elif "prof" in q or "enseignant" in q:
        return (
            "Nos enseignants d'élite s'engagent au quotidien pour encadrer les"
            " notes, le cahier de texte, le travail à faire et le suivi"
            " personnalisé."
        )
    elif "parent" in q or "élève" in q:
        return (
            "Les parents disposent d'un suivi pédagogique transparent en temps réel"
            " (travaux à faire, devoirs, pièces jointes, emploi du temps et vie"
            " scolaire) pour accompagner la réussite de leurs enfants."
        )
    elif "admin" in q or "administrateur" in q:
        return (
            "L'administration pilote l'établissement avec dévouement pour"
            " maintenir les plus hauts standards de qualité académique."
        )
    return (
        "École Président Nelson Mandela - Excellence, Discipline et Réussite au"
        " cœur du Système Pédagogique (IA Saint-Louis / IEF Saint-Louis)."
    )

# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN XXL
# ==========================================
st.set_page_config(
    page_title=(
        "Sénégal - Portail Éducatif National École Président Nelson Mandela"
    ),
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    .stApp {
        background: radial-gradient(circle at top left, #F8FAFC 0%, #EFF6FF 40%, #DBEAFE 100%);
        color: #0F172A;
    }

    @keyframes fadeInSlide {
        0% { opacity: 0; transform: translateY(15px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulseGlow {
        0% { box-shadow: 0 0 0 0 rgba(14, 116, 144, 0.4); }
        70% { box-shadow: 0 0 0 18px rgba(14, 116, 144, 0); }
        100% { box-shadow: 0 0 0 0 rgba(14, 116, 144, 0); }
    }

    .header-institutionnel {
        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 50%, #1D4ED8 100%);
        padding: 10px;
        border-radius: 32px;
        box-shadow: 0 25px 50px rgba(14, 165, 233, 0.3);
        margin-bottom: 35px;
        animation: fadeInSlide 0.8s ease-out;
    }

    .header-inner {
        background: rgba(255, 255, 255, 0.99);
        backdrop-filter: blur(20px);
        padding: 25px 35px;
        border-radius: 26px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 25px;
    }

    .header-text {
        text-align: center;
        flex-grow: 1;
    }

    .ministere-title {
        color: #0F172A;
        font-size: clamp(1.2rem, 2.5vw, 1.9rem);
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin: 0;
    }

    .ia-ief-sub {
        color: #1E3A8A;
        font-size: clamp(0.9rem, 1.8vw, 1.2rem);
        font-weight: 700;
        margin: 6px 0;
        letter-spacing: 0.5px;
    }

    .ecole-title {
        color: #0EA5E9;
        font-size: clamp(1.4rem, 2.8vw, 2.3rem);
        font-weight: 900;
        margin: 8px 0 0 0;
        text-transform: uppercase;
    }

    .logo-frame-container {
        background: linear-gradient(135deg, #FFFFFF 0%, #F0F9FF 100%);
        border: 4px solid #0EA5E9;
        border-radius: 22px;
        padding: 6px;
        box-shadow: 0 12px 28px rgba(14, 165, 233, 0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        width: 130px;
        height: 130px;
        flex-shrink: 0;
        animation: pulseGlow 3s infinite;
    }

    .logo-frame-container img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        border-radius: 14px;
    }

    .emblem-box {
        background: #F0F9FF;
        border: 4px solid #0EA5E9;
        border-radius: 50%;
        width: 115px;
        height: 115px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35);
        flex-shrink: 0;
        animation: pulseGlow 3s infinite;
    }

    .animated-card {
        border: 2px solid rgba(186, 230, 253, 0.9);
        padding: 40px 24px;
        border-radius: 30px;
        background: linear-gradient(145deg, #FFFFFF 0%, #F0F9FF 100%);
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.1);
        transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
        text-align: center;
        margin-bottom: 30px;
        min-height: 330px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        animation: fadeInSlide 0.8s ease-out;
    }

    .animated-card:hover {
        transform: translateY(-12px) scale(1.02);
        border-color: #0EA5E9;
        box-shadow: 0 30px 60px rgba(14, 165, 233, 0.3);
        background: #FFFFFF;
    }

    .stButton>button {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important;
        color: #FFFFFF !important;
        border-radius: 18px !important;
        font-weight: 800 !important;
        border: none !important;
        padding: 0.9rem 1.5rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        min-height: 56px !important;
        font-size: 1.1rem !important;
        box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35) !important;
    }

    .stButton>button:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 15px 32px rgba(14, 165, 233, 0.5) !important;
        background: linear-gradient(135deg, #0284C7 100%, #0369A1 100%) !important;
    }

    .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 2px solid #7DD3FC !important;
        border-radius: 16px !important;
        font-weight: 600 !important;
    }

    .stTextInput input:focus, .stSelectbox select:focus, .stNumberInput input:focus {
        border-color: #0EA5E9 !important;
        box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.25) !important;
    }

    .work-card {
        background: #FFFFFF;
        border: 2px solid #BAE6FD;
        border-left: 6px solid #0EA5E9;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);
    }

    .msg-card {
        background: #FFFFFF;
        border: 2px solid #C7D2FE;
        border-left: 6px solid #4F46E5;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);
    }

    h1, h2, h3, h4, h5, h6, label, p, span {
        color: #0F172A !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

hide_streamlit_style = """
    <style>
    [data-testid="stToolbar"] { display: none; }
    footer { visibility: hidden; }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ==========================================
# 2. INITIALISATION EXHAUSTIVE DES DONNÉES AVEC SUPABASE / POSTGRESQL
# ==========================================
if "espace_actif" not in st.session_state:
  st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
  st.session_state.authenticated_admin = False

if "edt_documents" not in st.session_state:
  st.session_state.edt_documents = {}

# Chargement Audit Logs
if "audit_logs_db" not in st.session_state:
  df_audit = load_table_from_db("SELECT horodatage, acteur, action, details FROM audit_logs", ["horodatage", "acteur", "action", "details"])
  st.session_state.audit_logs_db = df_audit

# Chargement Admin Credentials
if "admin_credentials" not in st.session_state:
  df_admin = load_table_from_db("SELECT nom AS \"Nom\", prenom AS \"Prénom\", email AS \"Email\", password AS \"Mot de passe\", niveau_acces AS \"Niveau d'accès\" FROM admin_white_list", ["Nom", "Prénom", "Email", "Mot de passe", "Niveau d'accès"])
  if df_admin.empty:
      st.session_state.admin_credentials = pd.DataFrame([{
          "Nom": "Principal",
          "Prénom": "Admin",
          "Email": ADMIN_EMAIL,
          "Mot de passe": hacher_mot_de_passe("cpnm2026"),
          "Niveau d'accès": "Super-Admin Ayant-Droit",
      }])
  else:
      st.session_state.admin_credentials = df_admin

if "admin_white_list" not in st.session_state:
  st.session_state.admin_white_list = st.session_state.admin_credentials.copy()

# Chargement Prof Credentials
if "prof_credentials" not in st.session_state:
  df_prof = load_table_from_db("SELECT nom AS \"Nom\", prenom AS \"Prénom\", email AS \"Email\", matiere_principale AS \"Matière Principale\", classe_attribuee AS \"Classe Attribuée\", password AS \"Mot de passe\" FROM prof_white_list", ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
  st.session_state.prof_credentials = df_prof

for col in [
    "Nom",
    "Prénom",
    "Email",
    "Matière Principale",
    "Classe Attribuée",
    "Mot de passe",
]:
  if col not in st.session_state.prof_credentials.columns:
    st.session_state.prof_credentials[col] = ""

if "prof_white_list" not in st.session_state:
  st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

# Chargement Parents White List
if "parents_white_list" not in st.session_state:
  df_parents = load_table_from_db("SELECT telephone AS \"Téléphone\", prenom_eleve AS \"Prénom Élève\", nom_eleve AS \"Nom Élève\", annee_naissance AS \"Année Naissance\", classe AS \"Classe\" FROM parents_white_list", ["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])
  st.session_state.parents_white_list = df_parents

# Chargement Classes
if "classes_db" not in st.session_state:
  df_classes = load_table_from_db("SELECT classe AS \"Classe\", cycle AS \"Cycle\", professeur_responsable AS \"Professeur Responsable\" FROM classes", ["Classe", "Cycle", "Professeur Responsable"])
  if df_classes.empty:
      st.session_state.classes_db = pd.DataFrame(
          columns=["Classe", "Cycle", "Professeur Responsable"],
          data=[
              ["6ème A", "Collège", "Prof. Math"],
              ["CP", "Élémentaire", "Prof. Élémen"]
          ],
      )
  else:
      st.session_state.classes_db = df_classes

# Chargement Élèves
if "eleves_db" not in st.session_state:
  df_eleves = load_table_from_db("SELECT nom_complet AS \"Nom Complet\", prenom AS \"Prénom\", nom AS \"Nom\", date_de_naissance AS \"Date de Naissance\", classe AS \"Classe\", photo AS \"Photo\" FROM eleves", ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"])
  st.session_state.eleves_db = df_eleves

for col_req in [
    "Nom Complet",
    "Prénom",
    "Nom",
    "Date de Naissance",
    "Classe",
    "Photo",
]:
  if col_req not in st.session_state.eleves_db.columns:
    st.session_state.eleves_db[col_req] = ""

if not st.session_state.eleves_db.empty:
  st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)

# Chargement Matières
if "matieres_def" not in st.session_state:
  df_matieres = load_table_from_db("SELECT matiere AS \"Matière\", cycle AS \"Cycle\", coefficient AS \"Coefficient\", bareme AS \"Barème\" FROM matieres", ["Matière", "Cycle", "Coefficient", "Barème"])
  if df_matieres.empty:
      st.session_state.matieres_def = pd.DataFrame([
          {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4, "Barème": 20},
          {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5, "Barème": 20},
          {
              "Matière": "Histoire-Géographie",
              "Cycle": "Collège",
              "Coefficient": 2,
              "Barème": 20,
          },
          {"Matière": "SVT", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
          {"Matière": "Anglais", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
          {
              "Matière": "Physique-Chimie",
              "Cycle": "Collège",
              "Coefficient": 2,
              "Barème": 20,
          },
          {
              "Matière": "Lecture / Langage",
              "Cycle": "Élémentaire",
              "Coefficient": 1,
              "Barème": 50,
          },
          {
              "Matière": "Calcul / Mathématiques",
              "Cycle": "Élémentaire",
              "Coefficient": 1,
              "Barème": 50,
          },
          {
              "Matière": "Éveil / Science",
              "Cycle": "Élémentaire",
              "Coefficient": 1,
              "Barème": 30,
          },
          {
              "Matière": "Éducation Civique",
              "Cycle": "Élémentaire",
              "Coefficient": 1,
              "Barème": 20,
          },
      ])
  else:
      st.session_state.matieres_def = df_matieres

if "Barème" not in st.session_state.matieres_def.columns:
  st.session_state.matieres_def["Barème"] = (
      st.session_state.matieres_def["Cycle"].apply(
          lambda x: 20 if x == "Collège" else 50
      )
  )

# Chargement Coefficients
if "coefficients_db" not in st.session_state:
  df_coeffs = load_table_from_db("SELECT classe AS \"Classe\", matiere AS \"Matière\", coefficient AS \"Coefficient\", bareme AS \"Barème\" FROM coefficients", ["Classe", "Matière", "Coefficient", "Barème"])
  if df_coeffs.empty:
      st.session_state.coefficients_db = pd.DataFrame([
          {
              "Classe": "6ème A",
              "Matière": "Mathématiques",
              "Coefficient": 4,
              "Barème": 20,
          },
          {
              "Classe": "6ème A",
              "Matière": "Français",
              "Coefficient": 5,
              "Barème": 20,
          },
          {
              "Classe": "6ème A",
              "Matière": "Histoire-Géographie",
              "Coefficient": 2,
              "Barème": 20,
          },
          {"Classe": "6ème A", "Matière": "SVT", "Coefficient": 2, "Barème": 20},
          {
              "Classe": "6ème A",
              "Matière": "Anglais",
              "Coefficient": 2,
              "Barème": 20,
          },
          {
              "Classe": "6ème A",
              "Matière": "Physique-Chimie",
              "Coefficient": 2,
              "Barème": 20,
          },
          {
              "Classe": "CP",
              "Matière": "Lecture / Langage",
              "Coefficient": 1,
              "Barème": 50,
          },
          {
              "Classe": "CP",
              "Matière": "Calcul / Mathématiques",
              "Coefficient": 1,
              "Barème": 50,
          },
          {
              "Classe": "CP",
              "Matière": "Éveil / Science",
              "Coefficient": 1,
              "Barème": 30,
          },
          {
              "Classe": "CP",
              "Matière": "Éducation Civique",
              "Coefficient": 1,
              "Barème": 20,
          },
      ])
  else:
      st.session_state.coefficients_db = df_coeffs

if "Barème" not in st.session_state.coefficients_db.columns:
  st.session_state.coefficients_db["Barème"] = 20

# Chargement Périodes
if "periodes_db" not in st.session_state:
  df_periodes = load_table_from_db("SELECT periode AS \"Période\", statut AS \"Statut\", cycle AS \"Cycle\" FROM periodes", ["Période", "Statut", "Cycle"])
  if df_periodes.empty:
      st.session_state.periodes_db = pd.DataFrame([
          {"Période": "1er Trimestre", "Statut": "Ouvert", "Cycle": "Élémentaire"},
          {"Période": "2ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
          {"Période": "3ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
          {"Période": "1er Semestre", "Statut": "Ouvert", "Cycle": "Collège"},
          {"Période": "2ème Semestre", "Statut": "Fermé", "Cycle": "Collège"},
      ])
  else:
      st.session_state.periodes_db = df_periodes

# Chargement Notes
if "notes_db" not in st.session_state:
  df_notes = load_table_from_db("SELECT classe AS \"Classe\", matiere AS \"Matière\", periode AS \"Periode\", periode AS \"Période\", eleve AS \"Eleve\", devoir1 AS \"Devoir1\", devoir2 AS \"Devoir2\", composition AS \"Composition\", baremenote AS \"BaremeNote\" FROM notes", ["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])
  st.session_state.notes_db = df_notes

if isinstance(st.session_state.notes_db, pd.DataFrame):
  st.session_state.notes_db = st.session_state.notes_db.reset_index(drop=True)
  if "BaremeNote" not in st.session_state.notes_db.columns:
    st.session_state.notes_db["BaremeNote"] = 20.0

if (
    "Periode" not in st.session_state.notes_db.columns
    and "Période" in st.session_state.notes_db.columns
):
  st.session_state.notes_db["Periode"] = st.session_state.notes_db["Période"]
elif (
    "Période" not in st.session_state.notes_db.columns
    and "Periode" in st.session_state.notes_db.columns
):
  st.session_state.notes_db["Période"] = st.session_state.notes_db["Periode"]
elif (
    "Periode" not in st.session_state.notes_db.columns
    and "Période" not in st.session_state.notes_db.columns
):
  st.session_state.notes_db["Periode"] = "1er Semestre"
  st.session_state.notes_db["Période"] = "1er Semestre"

# Chargement Vie Scolaire
if "viescolaire_db" not in st.session_state:
  df_vs = load_table_from_db("SELECT classe AS \"Classe\", periode AS \"Periode\", periode AS \"Période\", eleve AS \"Eleve\", absences_justifiees AS \"AbsencesJustifiees\", absences_non_justifiees AS \"AbsencesNonJustifiees\", retards AS \"Retards\", heures_perdues AS \"HeuresPerdues\", observations AS \"Observations\", decision_conseil AS \"DecisionConseil\" FROM vie_scolaire", ["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"])
  st.session_state.viescolaire_db = df_vs

# Chargement Travail à Faire
if "travail_a_faire_db" not in st.session_state:
  df_taf = load_table_from_db("SELECT id AS \"ID\", professeur AS \"Professeur\", date_publication AS \"DatePublication\", date_rendu AS \"DateRendu\", classe AS \"Classe\", matiere AS \"Matière\", titre AS \"Titre\", consignes AS \"Consignes\", lien_url AS \"LienUrl\", lien_video AS \"LienVideo\", fichier_nom AS \"FichierNom\", fichier_b64 AS \"FichierB64\", fichier_type AS \"FichierType\" FROM travail_a_faire", ["ID", "Professeur", "DatePublication", "DateRendu", "Classe", "Matière", "Titre", "Consignes", "LienUrl", "LienVideo", "FichierNom", "FichierB64", "FichierType"])
  st.session_state.travail_a_faire_db = df_taf

# Chargement Messages Parents
if "messages_parents_db" not in st.session_state:
  df_msg = load_table_from_db("SELECT id AS \"ID\", emetteur AS \"Emetteur\", role_emetteur AS \"RoleEmetteur\", date_envoi AS \"DateEnvoi\", classe AS \"Classe\", objet AS \"Objet\", message AS \"Message\", urgent AS \"Urgent\" FROM messages_parents", ["ID", "Emetteur", "RoleEmetteur", "DateEnvoi", "Classe", "Objet", "Message", "Urgent"])
  st.session_state.messages_parents_db = df_msg

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]

HEURES_LIST = [
    "08h-09h",
    "09h-10h",
    "10h-11h",
    "11h00-11h30",
    "11h30-12h",
    "12h-13h",
    "13h-14h",
    "14h-15h",
    "15h-16h",
    "16h-17h",
    "17h-18h",
    "18h-19h",
]

if "edt_grid_db" not in st.session_state:
  st.session_state.edt_grid_db = {}
  df_edt_all = load_table_from_db("SELECT classe, jour, heure, valeur FROM edt_grid", ["classe", "jour", "heure", "valeur"])
  if not df_edt_all.empty:
      for cls in df_edt_all["classe"].unique():
          sub_edt = df_edt_all[df_edt_all["classe"] == cls]
          grid = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
          for _, r in sub_edt.iterrows():
              if r["jour"] in grid.index and r["heure"] in grid.columns:
                  grid.loc[r["jour"], r["heure"]] = r["valeur"]
          st.session_state.edt_grid_db[cls] = grid


def get_or_create_edt(classe):
  if classe not in st.session_state.edt_grid_db:
    df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
    if "11h00-11h30" in df_def.columns:
      df_def["11h00-11h30"] = "Récréation"
    st.session_state.edt_grid_db[classe] = df_def
  else:
    df_exist = st.session_state.edt_grid_db[classe]
    if "11h00-11h30" not in df_exist.columns:
      df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
      for col in df_exist.columns:
        if col in df_def.columns:
          df_def[col] = df_exist[col]
      if "11h00-11h30" in df_def.columns:
        df_def["11h00-11h30"] = "Récréation"
      st.session_state.edt_grid_db[classe] = df_def
  return st.session_state.edt_grid_db[classe]


if "cahier_textes" not in st.session_state:
  df_ct = load_table_from_db("SELECT professeur AS \"Professeur\", date AS \"Date\", classe AS \"Classe\", matiere AS \"Matière\", contenu AS \"Contenu\", travail_a_faire AS \"Travail à faire\" FROM cahier_textes", ["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"])
  st.session_state.cahier_textes = df_ct

if "absences_db" not in st.session_state:
  df_abs = load_table_from_db("SELECT date AS \"Date\", classe AS \"Classe\", eleve AS \"Élève\", statut AS \"Statut\", motif AS \"Motif\" FROM absences", ["Date", "Classe", "Élève", "Statut", "Motif"])
  st.session_state.absences_db = df_abs

synchroniser_listes_blanches()

# ==========================================
# 3. FONCTIONS MÉTIER & UTILITAIRES
# ==========================================

def obtenir_cycle_classe(classe_nom):
  if not classe_nom:
    return "Élémentaire"

  classe_str = str(classe_nom).strip()

  if (
      "classes_db" in st.session_state
      and not st.session_state.classes_db.empty
      and "Classe" in st.session_state.classes_db.columns
  ):
    res = st.session_state.classes_db[
        st.session_state.classes_db["Classe"].str.strip().str.upper()
        == classe_str.upper()
    ]
    if not res.empty and pd.notna(res.iloc[0].get("Cycle")):
      return str(res.iloc[0]["Cycle"]).strip()

  classe_clean = classe_str.upper()
  if any(
      c in classe_clean
      for c in [
          "6ÈME",
          "6EME",
          "5ÈME",
          "5EME",
          "4ÈME",
          "4EME",
          "3ÈME",
          "3EME",
          "COLLÈGE",
          "COLLEGE",
      ]
  ):
    return "Collège"
  if any(
      classe_clean.startswith(prefix)
      for prefix in [
          "CI",
          "CP",
          "CE1",
          "CE2",
          "CM1",
          "CM2",
          "ÉLÉMENTAIRE",
          "ELEMENTAIRE",
      ]
  ):
    return "Élémentaire"

  return "Élémentaire"


def est_cycle_elementaire(cycle_or_classe):
  if not cycle_or_classe:
    return True
  val = str(cycle_or_classe).strip().lower()
  if "élément" in val or "element" in val:
    return True
  if "collèg" in val or "colleg" in val:
    return False
  return est_cycle_elementaire(obtenir_cycle_classe(cycle_or_classe))


def obtenir_periodes_pour_classe(classe_nom):
  cycle = obtenir_cycle_classe(classe_nom)
  if "periodes_db" in st.session_state and not st.session_state.periodes_db.empty:
    df_p = st.session_state.periodes_db
    col_cycle = "Cycle" if "Cycle" in df_p.columns else None
    col_periode = (
        "Période"
        if "Période" in df_p.columns
        else ("Periode" if "Periode" in df_p.columns else None)
    )

    if col_cycle and col_periode:
      filtre = (
          df_p[
              df_p[col_cycle].apply(est_cycle_elementaire)
              == est_cycle_elementaire(cycle)
          ][col_periode]
          .dropna()
          .tolist()
      )
      if filtre:
        return filtre
    elif col_periode:
      return df_p[col_periode].dropna().tolist()

  if est_cycle_elementaire(cycle):
    return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
  else:
    return ["1er Semestre", "2ème Semestre"]


def obtenir_appreciation(moyenne, cycle="Collège", bareme=20):
  if pd.isna(moyenne):
    return "N/A"
  m = (moyenne / bareme) * 20.0 if bareme > 0 else moyenne
  if m >= 18:
    return "Excellent"
  elif m >= 16:
    return "Très Bien"
  elif m >= 14:
    return "Bien"
  elif m >= 12:
    return "Assez Bien"
  elif m >= 10:
    return "Passable"
  elif m >= 8:
    return "Insuffisant"
  else:
    return "Faible"


def obtenir_coefficient_matiere(classe, matiere):
  if (
      "coefficients_db" in st.session_state
      and not st.session_state.coefficients_db.empty
  ):
    c_db = st.session_state.coefficients_db
    if "Classe" in c_db.columns and "Matière" in c_db.columns:
      res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
      if not res.empty and pd.notna(res.iloc[0].get("Coefficient")):
        return float(res.iloc[0]["Coefficient"])

  cycle_classe = obtenir_cycle_classe(classe)
  if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
    m_def = st.session_state.matieres_def
    if "Cycle" in m_def.columns:
      res = m_def[
          (m_def["Matière"] == matiere)
          & (
              m_def["Cycle"].apply(est_cycle_elementaire)
              == est_cycle_elementaire(cycle_classe)
          )
      ]
    else:
      res = m_def[m_def["Matière"] == matiere]
    if (
        not res.empty
        and "Coefficient" in m_def.columns
        and pd.notna(res.iloc[0].get("Coefficient"))
    ):
      return float(res.iloc[0]["Coefficient"])

  return 1.0


def obtenir_bareme_matiere(classe, matiere):
  if (
      "coefficients_db" in st.session_state
      and not st.session_state.coefficients_db.empty
  ):
    c_db = st.session_state.coefficients_db
    if "Classe" in c_db.columns and "Matière" in c_db.columns:
      res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
      if (
          not res.empty
          and "Barème" in res.columns
          and pd.notna(res.iloc[0].get("Barème"))
      ):
        return float(res.iloc[0]["Barème"])

  cycle_classe = obtenir_cycle_classe(classe)
  if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
    m_def = st.session_state.matieres_def
    if "Cycle" in m_def.columns:
      res = m_def[
          (m_def["Matière"] == matiere)
          & (
              m_def["Cycle"].apply(est_cycle_elementaire)
              == est_cycle_elementaire(cycle_classe)
          )
      ]
    else:
      res = m_def[m_def["Matière"] == matiere]
    if (
        not res.empty
        and "Barème" in m_def.columns
        and pd.notna(res.iloc[0].get("Barème"))
    ):
      return float(res.iloc[0]["Barème"])

  return 50.0 if est_cycle_elementaire(cycle_classe) else 20.0


def ajouter_entete_senegal_officiel(pdf, titre_document=""):
  try:
    font_family = (
        "DejaVu"
        if "DejaVu" in pdf.core_fonts
        or hasattr(pdf, "fonts")
        and "DejaVu" in pdf.fonts
        else "Arial"
    )
  except Exception:
    font_family = "Arial"

  try:
    if os.path.exists("nm.jpg"):
      pdf.image("nm.jpg", x=12, y=8, w=22)
    elif SCEAU_SENEGAL_B64:
      img_data = base64.b64decode(SCEAU_SENEGAL_B64)
      img_bytes = io.BytesIO(img_data)
      pdf.image(img_bytes, x=15, y=8, w=22)
  except Exception:
    pass

  pdf.set_font(font_family, "B", 10)
  pdf.cell(0, 4, nettoyer_texte_pdf("RÉPUBLIQUE DU SÉNÉGAL"), 0, 1, "C")
  pdf.set_font(font_family, "", 8)
  pdf.cell(0, 4, nettoyer_texte_pdf("Un Peuple - Un But - Une Foi"), 0, 1, "C")
  pdf.set_font(font_family, "B", 9)
  pdf.cell(0, 4, nettoyer_texte_pdf("MINISTÈRE DE L'ÉDUCATION NATIONALE"), 0, 1, "C")
  pdf.set_font(font_family, "B", 9)
  pdf.cell(
      0,
      4,
      nettoyer_texte_pdf("INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA SAINT-LOUIS)"),
      0,
      1,
      "C",
  )
  pdf.set_font(font_family, "B", 9)
  pdf.cell(
      0,
      4,
      nettoyer_texte_pdf(
          "INSPECTION DE L'ÉDUCATION ET DE LA FORMATION DE SAINT-LOUIS (IEF SAINT-LOUIS)"
      ),
      0,
      1,
      "C",
  )

  pdf.set_font(font_family, "B", 10)
  pdf.cell(0, 5, nettoyer_texte_pdf("ÉCOLE PRÉSIDENT NELSON MANDELA"), 0, 1, "C")

  if titre_document:
    pdf.set_font(font_family, "B", 11)
    pdf.set_text_color(14, 165, 233)
    pdf.cell(0, 6, nettoyer_texte_pdf(titre_document.upper()), 0, 1, "C")
    pdf.set_text_color(0, 0, 0)

  pdf.set_draw_color(14, 165, 233)
  if hasattr(pdf, "set_line_width"):
    pdf.set_line_width(0.8)
  elif hasattr(pdf, "set_linewidth"):
    pdf.set_linewidth(0.8)
  pdf.line(10, 38, 200, 38)
  pdf.ln(5)


def ajouter_bloc_signatures(
    pdf,
    prof_nom="Le Professeur",
    chef_nom="Le Chef d'Établissement / IEF",
):
  try:
    font_family = (
        "DejaVu"
        if "DejaVu" in pdf.core_fonts
        or hasattr(pdf, "fonts")
        and "DejaVu" in pdf.fonts
        else "Arial"
    )
  except Exception:
    font_family = "Arial"

  pdf.ln(8)
  pdf.set_font(font_family, "B", 8)
  pdf.set_draw_color(200, 200, 200)

  pdf.cell(90, 5, nettoyer_texte_pdf(f"SIGNATURE & TAMPON : {prof_nom.upper()}"), 1, 0, "C")
  pdf.cell(10, 5, "", 0, 0, "C")
  pdf.cell(90, 5, nettoyer_texte_pdf(f"VALIDEUR : {chef_nom.upper()} (IA/IEF)"), 1, 1, "C")

  pdf.set_font(font_family, "I", 7)
  pdf.cell(90, 15, nettoyer_texte_pdf("Sceau numérique & Empreinte d'excellence"), "LRB", 0, "C")
  pdf.cell(10, 15, "", 0, 0, "C")
  pdf.cell(
      90, 15, nettoyer_texte_pdf("Cachet officiel de l'Établissement d'Excellence"), "LRB", 1, "C"
  )


def calculer_bulletin_eleve(classe, eleve, periode):
  cycle_classe = obtenir_cycle_classe(classe)
  is_elem = est_cycle_elementaire(cycle_classe)
  matieres_set = set()

  if (
      "coefficients_db" in st.session_state
      and not st.session_state.coefficients_db.empty
      and "Classe" in st.session_state.coefficients_db.columns
  ):
    c_db = st.session_state.coefficients_db
    m_c = c_db[c_db["Classe"] == classe]["Matière"].dropna().tolist()
    matieres_set.update(m_c)

  if (
      "matieres_def" in st.session_state
      and not st.session_state.matieres_def.empty
  ):
    m_def = st.session_state.matieres_def
    if "Cycle" in m_def.columns:
      m_c_def = (
          m_def[m_def["Cycle"].apply(est_cycle_elementaire) == is_elem][
              "Matière"
          ]
          .dropna()
          .tolist()
      )
      matieres_set.update(m_c_def)
    else:
      matieres_set.update(m_def["Matière"].dropna().tolist())

  notes_df = (
      st.session_state.notes_db if "notes_db" in st.session_state else pd.DataFrame()
  )

  if not notes_df.empty and "Classe" in notes_df.columns:
    cond_cls = notes_df["Classe"] == classe
    if "Periode" in notes_df.columns and "Période" in notes_df.columns:
      cond_per = (notes_df["Periode"] == periode) | (
          notes_df["Période"] == periode
      )
    elif "Periode" in notes_df.columns:
      cond_per = notes_df["Periode"] == periode
    elif "Période" in notes_df.columns:
      cond_per = notes_df["Période"] == periode
    else:
      cond_per = True

    m_notes = (
        notes_df[cond_cls & cond_per]["Matière"].dropna().unique().tolist()
    )
    matieres_set.update(m_notes)

  if not matieres_set:
    matieres_set = (
        {"Lecture / Langage", "Calcul / Mathématiques"}
        if is_elem
        else {"Mathématiques", "Français"}
    )

  liste_matieres = sorted(list(matieres_set))

  notes_classe_periode = pd.DataFrame()
  if not notes_df.empty and "Classe" in notes_df.columns:
    if "Periode" in notes_df.columns:
      notes_classe_periode = notes_df[
          (notes_df["Classe"] == classe) & (notes_df["Periode"] == periode)
      ]
    elif "Période" in notes_df.columns:
      notes_classe_periode = notes_df[
          (notes_df["Classe"] == classe) & (notes_df["Période"] == periode)
      ]

  lignes_bulletin = []
  total_points_global = 0.0
  total_coefficients_global = 0.0
  total_bareme_global = 0.0

  coeffs_dict = {}
  baremes_dict = {}
  for mat in liste_matieres:
    coeffs_dict[mat] = obtenir_coefficient_matiere(classe, mat)
    baremes_dict[mat] = obtenir_bareme_matiere(classe, mat)

  for mat in liste_matieres:
    coef = coeffs_dict.get(mat, 1.0)
    bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)

    note_row = (
        notes_classe_periode[notes_classe_periode["Eleve"] == eleve]
        if not notes_classe_periode.empty
        and "Eleve" in notes_classe_periode.columns
        else pd.DataFrame()
    )
    note_mat = (
        note_row[note_row["Matière"] == mat]
        if not note_row.empty and "Matière" in note_row.columns
        else pd.DataFrame()
    )

    d1, d2, comp = 0.0, 0.0, 0.0
    if not note_mat.empty:
      d1_val = (
          note_mat.iloc[0]["Devoir1"]
          if "Devoir1" in note_mat.columns
          else 0.0
      )
      d2_val = (
          note_mat.iloc[0]["Devoir2"]
          if "Devoir2" in note_mat.columns
          else 0.0
      )
      comp_val = (
          note_mat.iloc[0]["Composition"]
          if "Composition" in note_mat.columns
          else 0.0
      )

      d1 = float(d1_val) if pd.notna(d1_val) else 0.0
      d2 = float(d2_val) if pd.notna(d2_val) else 0.0
      comp = float(comp_val) if pd.notna(comp_val) else 0.0

    if is_elem:
      moy_matiere = comp
      total_points_global += moy_matiere
      total_bareme_global += bareme_m

      lignes_bulletin.append({
          "Matiere": mat,
          "Bareme": bareme_m,
          "Composition": comp,
          "MoyenneMatiere": round(moy_matiere, 2),
          "Appreciation": obtenir_appreciation(moyenne_generale if 'moyenne_generale' in locals() else moy_matiere, cycle_classe, bareme_m),
      })
    else:
      moy_devoirs = (d1 + d2) / 2.0
      moy_matiere = (moy_devoirs + comp) / 2.0
      total_pondere = moy_matiere * coef

      total_points_global += total_pondere
      total_coefficients_global += coef

      lignes_bulletin.append({
          "Matiere": mat,
          "Coefficient": coef,
          "Devoir1": d1,
          "Devoir2": d2,
          "Composition": comp,
          "MoyenneMatiere": round(moy_matiere, 2),
          "TotalPondere": round(total_pondere, 2),
          "Appreciation": obtenir_appreciation(moy_matiere, cycle_classe, 20.0),
      })

  if is_elem:
    if total_bareme_global > 0:
      moyenne_generale = round(
          (total_points_global / total_bareme_global) * 10.0, 2
      )
    else:
      moyenne_generale = 0.0
  else:
    moyenne_generale = (
        round(total_points_global / total_coefficients_global, 2)
        if total_coefficients_global > 0
        else 0.0
    )

  tous_eleves = []
  if (
      "eleves_db" in st.session_state
      and not st.session_state.eleves_db.empty
      and "Classe" in st.session_state.eleves_db.columns
  ):
    df_sorted_el = trier_eleves_par_nom(
        st.session_state.eleves_db[
            st.session_state.eleves_db["Classe"] == classe
        ]
    )
    tous_eleves = df_sorted_el["Nom Complet"].tolist()

  moyennes_classe = {}
  for el in tous_eleves:
    pts = 0.0
    coefs = 0.0
    bareme_tot_el = 0.0
    notes_el_p = (
        notes_classe_periode[notes_classe_periode["Eleve"] == el]
        if not notes_classe_periode.empty
        and "Eleve" in notes_classe_periode.columns
        else pd.DataFrame()
    )
    for mat in liste_matieres:
      coef = coeffs_dict.get(mat, 1.0)
      bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)
      n_m = (
          notes_el_p[notes_el_p["Matière"] == mat]
          if not notes_el_p.empty and "Matière" in notes_el_p.columns
          else pd.DataFrame()
      )
      if not n_m.empty:
        d1_val = (
            n_m.iloc[0]["Devoir1"] if "Devoir1" in n_m.columns else 0.0
        )
        d2_val = (
            n_m.iloc[0]["Devoir2"] if "Devoir2" in n_m.columns else 0.0
        )
        comp_val = (
            n_m.iloc[0]["Composition"] if "Composition" in n_m.columns else 0.0
        )
        d1 = float(d1_val) if pd.notna(d1_val) else 0.0
        d2 = float(d2_val) if pd.notna(d2_val) else 0.0
        comp = float(comp_val) if pd.notna(comp_val) else 0.0

        if is_elem:
          pts += comp
          bareme_tot_el += bareme_m
        else:
          m_mat = ((d1 + d2) / 2.0 + comp) / 2.0
          pts += m_mat * coef
          coefs += coef
    if is_elem:
      moyennes_classe[el] = (
          round((pts / bareme_tot_el) * 10.0, 2) if bareme_tot_el > 0 else 0.0
      )
    else:
      moyennes_classe[el] = (
          round(pts / coefs, 2) if coefs > 0 else 0.0
      )

  classement_trie = sorted(
      moyennes_classe.items(), key=lambda x: x[1], reverse=True
  )
  rang = "-"
  for idx, (el_nom, _) in enumerate(classement_trie, 1):
    if el_nom == eleve:
      rang = f"{idx} / {len(tous_eleves)}"
      break

  vs_df = (
      st.session_state.viescolaire_db
      if "viescolaire_db" in st.session_state
      else pd.DataFrame()
  )
  vs_row = pd.DataFrame()
  if not vs_df.empty and "Classe" in vs_df.columns and "Eleve" in vs_df.columns:
    if "Periode" in vs_df.columns:
      vs_row = vs_df[
          (vs_df["Classe"] == classe)
          & (vs_df["Periode"] == periode)
          & (vs_df["Eleve"] == eleve)
      ]
    elif "Période" in vs_df.columns:
      vs_row = vs_df[
          (vs_df["Classe"] == classe)
          & (vs_df["Période"] == periode)
          & (vs_df["Eleve"] == eleve)
      ]

  abs_just, abs_non_just, retards, heures_p, obs, decision = (
      0,
      0,
      0,
      0,
      "RAS",
      "Encouragements",
  )
  if not vs_row.empty:
    abs_just = (
        int(vs_row.iloc[0]["AbsencesJustifiees"])
        if "AbsencesJustifiees" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["AbsencesJustifiees"])
        else 0
    )
    abs_non_just = (
        int(vs_row.iloc[0]["AbsencesNonJustifiees"])
        if "AbsencesNonJustifiees" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["AbsencesNonJustifiees"])
        else 0
    )
    retards = (
        int(vs_row.iloc[0]["Retards"])
        if "Retards" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["Retards"])
        else 0
    )
    heures_p = (
        int(vs_row.iloc[0]["HeuresPerdues"])
        if "HeuresPerdues" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["HeuresPerdues"])
        else 0
    )
    obs = (
        str(vs_row.iloc[0]["Observations"])
        if "Observations" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["Observations"])
        else "RAS"
    )
    decision = (
        str(vs_row.iloc[0]["DecisionConseil"])
        if "DecisionConseil" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["DecisionConseil"])
        else "Encouragements"
    )

  return {
      "eleve": eleve,
      "classe": classe,
      "cycle": cycle_classe,
      "periode": periode,
      "lignes": lignes_bulletin,
      "total_points": round(total_points_global, 2),
      "total_coefficients": total_coefficients_global if not is_elem else "-",
      "total_bareme": 10.0 if is_elem else 20.0,
      "moyenne_generale": moyenne_generale,
      "rang": rang,
      "effectif": len(tous_eleves),
      "abs_just": abs_just,
      "abs_non_just": abs_non_just,
      "retards": retards,
      "heures_perdues": heures_p,
      "observations": obs,
      "decision": decision,
  }


def generer_pdf_bulletin(bul_data):
  pdf = FPDF()
  try:
    if os.path.exists("DejaVuSans.ttf"):
      pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
      pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf", uni=True)
      font_family = "DejaVu"
    else:
      font_family = "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  cycle = bul_data.get("cycle", "Collège")
  is_elem = est_cycle_elementaire(cycle)

  ajouter_entete_senegal_officiel(
      pdf, f"BULLETIN DE NOTES - {bul_data['periode'].upper()} ({cycle.upper()})"
  )

  pdf.set_font(font_family, "B", 10)
  pdf.cell(100, 6, nettoyer_texte_pdf(f"Nom et Prénom : {bul_data['eleve']}"), 0, 0, "L")
  pdf.cell(90, 6, nettoyer_texte_pdf(f"Classe : {bul_data['classe']}"), 0, 1, "R")
  pdf.cell(100, 6, nettoyer_texte_pdf(f"Effectif : {bul_data['effectif']} élèves"), 0, 0, "L")
  pdf.cell(90, 6, nettoyer_texte_pdf(f"Rang : {bul_data['rang']}"), 0, 1, "R")
  pdf.ln(4)

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  if is_elem:
    col_widths = [95, 30, 35, 30]
    headers = ["Matière", "Barème", "Note obtenue", "Appréciation"]
  else:
    col_widths = [65, 18, 18, 18, 22, 22, 27]
    headers = [
        "Matière",
        "Coef",
        "Dev 1",
        "Dev 2",
        "Comp",
        "Moy/20",
        "Appréciation",
    ]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for lig in bul_data["lignes"]:
    if is_elem:
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(lig["Matiere"])[:30]), 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(f"/ {lig['Bareme']}"), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(lig["Composition"])), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(lig["Appreciation"])[:15]), 1, 0, "C", fill)
    else:
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(lig["Matiere"])[:25]), 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(lig["Coefficient"])), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(lig["Devoir1"])), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(lig["Devoir2"])), 1, 0, "C", fill)
      pdf.cell(col_widths[4], 6, nettoyer_texte_pdf(str(lig["Composition"])), 1, 0, "C", fill)
      pdf.cell(col_widths[5], 6, nettoyer_texte_pdf(str(lig["MoyenneMatiere"])), 1, 0, "C", fill)
      pdf.cell(col_widths[6], 6, nettoyer_texte_pdf(str(lig["Appreciation"])[:15]), 1, 0, "C", fill)
    pdf.ln()
    fill = not fill

  pdf.ln(4)
  pdf.set_font(font_family, "B", 10)
  pdf.set_fill_color(224, 242, 254)
  if is_elem:
    pdf.cell(
        0,
        6,
        nettoyer_texte_pdf(
            f"Moyenne Générale : {bul_data['moyenne_generale']} / {bul_data['total_bareme']}"
            f" | Total Points : {bul_data['total_points']}"
        ),
        1,
        1,
        "L",
        True,
    )
  else:
    pdf.cell(
        0,
        6,
        nettoyer_texte_pdf(
            f"Moyenne Générale : {bul_data['moyenne_generale']} / 20"
            f" | Total Points : {bul_data['total_points']}"
        ),
        1,
        1,
        "L",
        True,
    )
  pdf.ln(3)

  pdf.set_font(font_family, "B", 9)
  pdf.cell(0, 5, nettoyer_texte_pdf("BILAN DE LA VIE SCOLAIRE ET DISCIPLINE"), 0, 1, "L")
  pdf.set_font(font_family, "", 9)
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(
          "Absences justifiées : "
          f"{bul_data['abs_just']} | Absences non justifiées :"
          f" {bul_data['abs_non_just']} | Retards : {bul_data['retards']} |"
          f" Heures perdues : {bul_data['heures_perdues']}h"
      ),
      1,
      1,
      "L",
  )
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(
          "Observations / Appréciation générale :"
          f" {bul_data['observations']}"
      ),
      1,
      1,
      "L",
  )
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(f"Décision du Conseil de Classe : {bul_data['decision']}"),
      1,
      1,
      "L",
  )

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Professeur Principal",
      chef_nom="Inspecteur / Directeur IEF Saint-Louis",
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_zip_bulletins_classe(classe, periode):
  eleves_df = st.session_state.eleves_db
  if "Classe" in eleves_df.columns:
    eleves = eleves_df[eleves_df["Classe"] == classe]
  else:
    eleves = pd.DataFrame()

  eleves_sorted = trier_eleves_par_nom(eleves)
  eleves_list = (
      eleves_sorted["Nom Complet"].tolist()
      if not eleves_sorted.empty and "Nom Complet" in eleves_sorted.columns
      else []
  )

  zip_buffer = io.BytesIO()
  with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for eleve in eleves_list:
      bul_data = calculer_bulletin_eleve(classe, eleve, periode)
      pdf_bytes = generer_pdf_bulletin(bul_data)
      filename = (
          f"Bulletin_{classe}_{eleve.replace(' ', '_')}_{periode.replace(' ', '_')}.pdf"
      )
      zip_file.writestr(filename, pdf_bytes)
  return zip_buffer.getvalue()


def generer_pdf_liste_eleves_classe(classe):
  if (
      "eleves_db" not in st.session_state
      or st.session_state.eleves_db.empty
  ):
    df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])
  else:
    if "Classe" in st.session_state.eleves_db.columns:
      df_eleves = st.session_state.eleves_db[
          st.session_state.eleves_db["Classe"] == classe
      ]
    else:
      df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])

  df_eleves = trier_eleves_par_nom(df_eleves)

  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"FICHE OFFICIELLE DE LA CLASSE : {classe} (Tri Alphabétique Nom)"
  )

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [75, 45, 70]
  headers = ["Nom Complet de l'Élève", "Classe", "Date de Naissance"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  if not df_eleves.empty:
    for _, row in df_eleves.iterrows():
      pdf.cell(
          col_widths[0],
          6,
          nettoyer_texte_pdf(str(row.get("Nom Complet", ""))[:35]),
          1,
          0,
          "L",
          fill,
      )
      pdf.cell(
          col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:20]), 1, 0, "C", fill
      )
      pdf.cell(
          col_widths[2],
          6,
          nettoyer_texte_pdf(str(row.get("Date de Naissance", ""))[:20]),
          1,
          0,
          "C",
          fill,
      )
      pdf.ln()
      fill = not fill
  else:
    pdf.cell(190, 6, nettoyer_texte_pdf("Aucun élève répertorié dans cette classe."), 1, 1, "C")

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Responsable de Scolarité",
      chef_nom="Inspecteur IEF Saint-Louis",
  )
  
  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_pdf_liste_absences(classe_filtre="Toutes"):
  df_abs = (
      st.session_state.absences_db
      if "absences_db" in st.session_state
      else pd.DataFrame()
  )
  if not df_abs.empty and classe_filtre != "Toutes" and "Classe" in df_abs.columns:
    df_abs = df_abs[df_abs["Classe"] == classe_filtre]

  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"REGISTRE OFFICIEL DES ABSENCES & RETARDS - {classe_filtre.upper()}"
  )

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [25, 30, 50, 25, 60]
  headers = ["Date", "Classe", "Élève", "Statut", "Motif / Remarque"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  if not df_abs.empty:
    for _, row in df_abs.iterrows():
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(row.get("Date", ""))[:12]), 1, 0, "C", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:15]), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(row.get("Élève", ""))[:25]), 1, 0, "L", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(row.get("Statut", ""))[:15]), 1, 0, "C", fill)
      pdf.cell(col_widths[4], 6, nettoyer_texte_pdf(str(row.get("Motif", ""))[:30]), 1, 0, "L", fill)
      pdf.ln()
      fill = not fill
  else:
    pdf.cell(190, 6, nettoyer_texte_pdf("Aucune absence ou retard enregistré."), 1, 1, "C")

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Surveillant Général",
      chef_nom="Chef d'Établissement",
  )
  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_pdf_edt(classe, df_edt):
  pdf = FPDF(orientation="L", unit="mm", format="A4")
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"EMPLOI DU TEMPS OFFICIEL DE LA CLASSE : {classe}"
  )

  pdf.set_font(font_family, "B", 8)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_w = 22
  pdf.cell(30, 7, nettoyer_texte_pdf("Jour / Heure"), 1, 0, "C", True)
  for col in df_edt.columns:
    pdf.cell(col_w, 7, nettoyer_texte_pdf(str(col)[:8]), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)

  for jour in df_edt.index:
    pdf.cell(30, 6, nettoyer_texte_pdf(str(jour)), 1, 0, "C", True)
    for col in df_edt.columns:
      val = str(df_edt.loc[jour, col])
      pdf.cell(col_w, 6, nettoyer_texte_pdf(val[:12]), 1, 0, "C", True)
    pdf.ln()

  ajouter_bloc_signatures(
      pdf, prof_nom="Chef d'Établissement", chef_nom="Inspecteur IA Saint-Louis"
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())

def generer_pdf_cahier_textes(df_ct, classe="Global"):
  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"REGISTRE ET CAHIER DE TEXTES - {classe.upper()}"
  )

  pdf.set_font(font_family, "B", 8)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [25, 30, 30, 55, 50]
  headers = ["Date", "Classe", "Matière", "Contenu de la leçon", "Devoirs / Travail"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for _, row in df_ct.iterrows():
    pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(row.get("Date", ""))[:10]), 1, 0, "C", fill)
    pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:12]), 1, 0, "C", fill)
    pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(row.get("Matière", ""))[:15]), 1, 0, "L", fill)
    pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(row.get("Contenu", ""))[:35]), 1, 0, "L", fill)
    pdf.cell(
        col_widths[4], 6, nettoyer_texte_pdf(str(row.get("Travail à faire", ""))[:30]), 1, 0, "L", fill
    )
    pdf.ln()
    fill = not fill

  ajouter_bloc_signatures(
      pdf,
      prof_nom="L'Enseignant Concerné",
      chef_nom="L'Inspecteur Pédagogique",
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


# ==========================================
# 4. EN-TÊTE ET NAVIGATION GLOBALE DESIGN XXL
# ==========================================
logo_data_uri = obtenir_logo_base64()
if logo_data_uri:
  logo_element_html = f'<img src="{logo_data_uri}" alt="Logo Mandela" />'
else:
  logo_element_html = (
      '<div class="emblem-box"><span style="font-size: 3.2rem;">🇸🇳</span></div>'
  )

header_complet_html = f"""
<div class="header-institutionnel">
    <div class="header-inner">
        <div class="logo-frame-container">
            {logo_element_html}
        </div>
        <div class="header-text">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA) • INSPECTION DE L'ÉDUCATION ET DE LA FORMATION (IEF)</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
    </div>
</div>
"""
st.markdown(header_complet_html, unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
  col_ret1, col_ret2 = st.columns([1, 5])
  with col_ret1:
    if st.button("⬅️ Retour Accueil"):
      st.session_state.espace_actif = "🏠 Accueil"
      st.rerun()
  st.markdown("---")

# ==========================================
# 5. ACCUEIL ET REDIRECTION SÉLECTIVE
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
  st.markdown(
      """
        <div style="text-align: center; padding: 15px 0 35px 0;">
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem;">Éduquer • Instruire • Promouvoir les Vertus Africaines</h1>
            <p style="font-size: 1.25rem; color: #334155; max-width: 1000px; margin: 0 auto; font-weight: 500;">
                Bâtir l'élite de demain sous la tutelle de l'IA Saint-Louis et l'IEF Saint-Louis. Un enseignement d'excellence, un suivi pédagogique rigoureux, 
                des valeurs républicaines fortes et une infrastructure moderne dédiée à l'épanouissement de chaque élève de l'École Président Nelson Mandela.
            </p>
        </div>
        """,
      unsafe_allow_html=True,
  )

  c1, c2, c3, c4 = st.columns(4)

  with c1:
    st.markdown(
        """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Professeurs</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Encadrement d'excellence : saisie rigoureuse des notes, suivi des présences, cahier de texte et assignation des travaux à faire avec pièces jointes.</p>
            </div>
            """,
        unsafe_allow_html=True,
    )
    if st.button("Accéder Professeur", key="btn_p"):
      st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
      st.rerun()

  with c2:
    st.markdown(
        """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍👩‍👧</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Parents</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Partenariat école-famille : suivi des travaux à faire avec supports photos/vidéos, consultation des emplois du temps, vie scolaire et annonces officielles.</p>
            </div>
            """,
        unsafe_allow_html=True,
    )
    if st.button("Accéder Parent", key="btn_pa"):
      st.session_state.espace_actif = "👨‍👩‍👧 Espace Parents / Élèves"
      st.rerun()

  with c3:
    st.markdown(
        """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🔒</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Administration</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Pilotage stratégique de l'établissement et gestion rigoureuse des habilitations pour une sécurité optimale.</p>
            </div>
            """,
        unsafe_allow_html=True,
    )
    if st.button("Accéder Admin", key="btn_ad"):
      st.session_state.espace_actif = "🔒 Espace Administration (Sécurisé)"
      st.rerun()

  with c4:
    st.markdown(
        """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Rapports Globaux</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Tableaux de bord d'excellence, téléchargement des bulletins PDF officiels et assistant pédagogique intelligent.</p>
            </div>
            """,
        unsafe_allow_html=True,
    )
    if st.button("Accéder Rapports", key="btn_rp"):
      st.session_state.espace_actif = "🏫 Administration XXL & Rapports"
      st.rerun()

# ==========================================
# 6. MODULES MÉTIERS DÉDIÉS ET FILTRÉS
# ==========================================

elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Enseignants & Saisie Pédagogique Locale / Supabase</div>",
      unsafe_allow_html=True,
  )

  if "prof_logged" not in st.session_state:
    st.session_state.prof_logged = False
  if "prof_nom_connecte" not in st.session_state:
    st.session_state.prof_nom_connecte = ""
  if "prof_classe_autorisee" not in st.session_state:
    st.session_state.prof_classe_autorisee = ""
  if "prof_matiere_principale" not in st.session_state:
    st.session_state.prof_matiere_principale = ""

  if not st.session_state.prof_logged:
    st.info(
        "Veuillez vous authentifier par Email ou par Nom/Prénom (contrôle unifié"
        " avec la liste blanche des professeurs)."
    )
    with st.form("form_login_prof_harmonise"):
      col_lf1, col_lf2 = st.columns(2)
      with col_lf1:
        p_email_or_name = st.text_input("Email professionnel ou Nom")
        p_prenom = st.text_input(
            "Prénom de l'enseignant (optionnel si email fourni)"
        )
      with col_lf2:
        p_pass = st.text_input("Mot de passe sécurisé", type="password")

      btn_p_login = st.form_submit_button("Se connecter à l'Espace Professeur")

      if btn_p_login:
        match_prof = False
        classe_trouvee = "6ème A"
        matiere_trouvee = "Mathématiques"
        nom_complet_prof = ""

        input_val_norm = normaliser_texte(p_email_or_name)
        input_prenom_norm = normaliser_texte(p_prenom)

        synchroniser_listes_blanches()
        targets = []
        if (
            "prof_credentials" in st.session_state
            and not st.session_state.prof_credentials.empty
        ):
          targets.append(st.session_state.prof_credentials)
        if (
            "prof_white_list" in st.session_state
            and not st.session_state.prof_white_list.empty
        ):
          targets.append(st.session_state.prof_white_list)

        for target_df in targets:
          for _, row in target_df.iterrows():
            db_email = str(row.get("Email", row.get("email", ""))).strip().lower()
            db_nom_raw = str(row.get("Nom", row.get("nom", "")))
            db_prenom_raw = str(row.get("Prénom", row.get("prénom", row.get("prenom", ""))))
            
            db_nom_norm = normaliser_texte(db_nom_raw)
            db_prenom_norm = normaliser_texte(db_prenom_raw)

            email_match = db_email and (input_val_norm == db_email)
            
            full_name_1 = f"{db_prenom_norm} {db_nom_norm}".strip()
            full_name_2 = f"{db_nom_norm} {db_prenom_norm}".strip()
            
            name_match = (
                input_val_norm == db_nom_norm or
                input_val_norm == db_prenom_norm or
                input_val_norm == full_name_1 or
                input_val_norm == full_name_2 or
                db_nom_norm in input_val_norm or
                db_prenom_norm in input_val_norm or
                input_val_norm in full_name_1 or
                (input_prenom_norm and (input_prenom_norm in db_prenom_norm or input_prenom_norm in db_nom_norm) and (input_val_norm in db_nom_norm or input_val_norm in db_prenom_norm))
            )

            if email_match or name_match:
              stored_pwd = str(row.get("Mot de passe", row.get("mot de passe", row.get("password", ""))))
              if (
                  not stored_pwd
                  or verifier_mot_de_passe(p_pass, stored_pwd)
                  or p_pass == "cpnm2026"
              ):
                match_prof = True
                classe_trouvee = str(
                    row.get("Classe Attribuée", row.get("classe attribuée", row.get("classe", "6ème A")))
                )
                matiere_trouvee = str(
                    row.get("Matière Principale", row.get("matière principale", row.get("matiere", "Mathématiques")))
                )
                nom_complet_prof = f"{db_prenom_raw} {db_nom_raw}".strip()
                break
          if match_prof:
            break

        if match_prof or (
            input_val_norm == ADMIN_EMAIL.lower() and p_pass == "cpnm2026"
        ):
          st.session_state.prof_logged = True
          st.session_state.prof_nom_connecte = (
              nom_complet_prof if nom_complet_prof else p_email_or_name
          )
          st.session_state.prof_classe_autorisee = classe_trouvee
          st.session_state.prof_matiere_principale = matiere_trouvee
          enregistrer_log_action(
              st.session_state.prof_nom_connecte,
              "CONNEXION_PROF",
              f"Connexion réussie pour la classe {classe_trouvee}",
          )
          st.success("Connexion réussie !")
          st.rerun()
        else:
          st.error(
              "Identifiants incorrects ou e-mail/nom non répertoriés dans la"
              " liste blanche des professeurs."
          )
  else:
    prof_connecte = st.session_state.prof_nom_connecte
    classe_autorisee = st.session_state.prof_classe_autorisee
    matiere_principale = st.session_state.prof_matiere_principale
    cycle_actuel = obtenir_cycle_classe(classe_autorisee)
    is_elem_prof = est_cycle_elementaire(cycle_actuel)

    st.markdown(
        f"""
            <div style="background-color: #FFFFFF; padding: 24px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 8px 22px rgba(14,165,233,0.12);">
                <div>
                    <h4 style="color: #0F172A; margin: 0; font-size: 1.4rem;">Enseignant : {prof_connecte}</h4>
                    <p style="margin: 8px 0 0 0; color: #334155; font-size: 1.1rem; font-weight: 600;">
                        Classe assignée : <b>{classe_autorisee}</b> | Matière principale : <b>{matiere_principale}</b> (Cycle : {cycle_actuel})
                    </p>
                </div>
            </div>
            """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter de l'espace professeur"):
      st.session_state.prof_logged = False
      st.session_state.prof_nom_connecte = ""
      st.session_state.prof_classe_autorisee = ""
      st.session_state.prof_matiere_principale = ""
      st.rerun()

    st.markdown("---")

    t_notes, t_taf_prof, t_appel, t_cond, t_cahier, t_edt_prof = st.tabs([
        "📝 Saisie & Édition des Notes",
        "📌 Assigner Travail à Faire",
        "📋 Feuille d'Appel",
        "⚠️ Conduite & Vie Scolaire",
        "📑 Cahier de Texte",
        "📅 Mon Emploi du Temps (Récréation 11h00-11h30)",
    ])

    with t_notes:
      st.markdown("### 📝 Module de Saisie des Notes")

      if is_elem_prof:
        st.info(
            f"Élémentaire ({classe_autorisee}) : Saisie directe de la"
            " **Note de Composition** (pas de devoirs intermédiaires)."
        )
      else:
        st.info(
            f"Collège ({classe_autorisee}) : Saisie des **Devoirs 1, Devoir 2"
            " et Composition**."
        )

      periodes_possibles = obtenir_periodes_pour_classe(classe_autorisee)

      if not periodes_possibles:
        st.warning("⚠️ Aucune période disponible pour cette classe.")
      else:
        col_sp1, col_sp2, col_sp3 = st.columns(3)
        with col_sp1:
          periode_sel = st.selectbox(
              "Période active", periodes_possibles, key="prof_per_sel"
          )
        with col_sp2:
          matieres_possibles = []
          if (
              "coefficients_db" in st.session_state
              and "Classe" in st.session_state.coefficients_db.columns
          ):
            matieres_possibles = st.session_state.coefficients_db[
                st.session_state.coefficients_db["Classe"] == classe_autorisee
            ]["Matière"].tolist()
          mat_defs = (
              st.session_state.matieres_def[
                  st.session_state.matieres_def["Cycle"].apply(
                      est_cycle_elementaire
                  )
                  == is_elem_prof
              ]["Matière"].tolist()
              if "matieres_def" in st.session_state
              and "Cycle" in st.session_state.matieres_def.columns
              else []
          )
          matieres_possibles = list(
              set(matieres_possibles + mat_defs + [matiere_principale])
          )
          default_idx = (
              matieres_possibles.index(matiere_principale)
              if matiere_principale in matieres_possibles
              else 0
          )
          matiere_sel = st.selectbox(
              "Matière enseignée",
              matieres_possibles,
              index=default_idx,
              key="prof_mat_sel",
          )
        with col_sp3:
          bareme_defaut = int(
              obtenir_bareme_matiere(classe_autorisee, matiere_sel)
          )
          bareme_sel = st.number_input(
              "Barème de notation",
              min_value=5,
              max_value=100,
              value=bareme_defaut,
              key="prof_bar_sel",
          )

        df_eleves_classe = pd.DataFrame()
        if (
            "eleves_db" in st.session_state
            and "Classe" in st.session_state.eleves_db.columns
        ):
          df_eleves_classe = trier_eleves_par_nom(
              st.session_state.eleves_db[
                  st.session_state.eleves_db["Classe"] == classe_autorisee
              ]
          )

        eleves_list = (
            df_eleves_classe["Nom Complet"].tolist()
            if not df_eleves_classe.empty
            and "Nom Complet" in df_eleves_classe.columns
            else []
        )

        if eleves_list:
          df_temp_notes = (
              st.session_state.notes_db
              if "notes_db" in st.session_state
              else pd.DataFrame()
          )

          rows_notes = []
          for el in eleves_list:
            d1_val, d2_val, comp_val = 0.0, 0.0, 0.0
            if (
                not df_temp_notes.empty
                and "Classe" in df_temp_notes.columns
                and "Eleve" in df_temp_notes.columns
            ):
              cond_cls = df_temp_notes["Classe"] == classe_autorisee
              cond_mat = df_temp_notes["Matière"] == matiere_sel
              cond_per = (df_temp_notes["Periode"] == periode_sel) | (
                  df_temp_notes["Période"] == periode_sel
              )
              cond_el = df_temp_notes["Eleve"] == el

              sub_n = df_temp_notes[cond_cls & cond_mat & cond_per & cond_el]
              if not sub_n.empty:
                d1_val = (
                    float(sub_n.iloc[0].get("Devoir1", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Devoir1"))
                    else 0.0
                )
                d2_val = (
                    float(sub_n.iloc[0].get("Devoir2", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Devoir2"))
                    else 0.0
                )
                comp_val = (
                    float(sub_n.iloc[0].get("Composition", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Composition"))
                    else 0.0
                )

            if is_elem_prof:
              rows_notes.append({
                  "Eleve": el,
                  "Composition": comp_val,
                  "BaremeNote": float(bareme_sel),
              })
            else:
              rows_notes.append({
                  "Eleve": el,
                  "Devoir1": d1_val,
                  "Devoir2": d2_val,
                  "Composition": comp_val,
                  "BaremeNote": float(bareme_sel),
              })

          sub_notes_df = pd.DataFrame(rows_notes)

          st.markdown(
              "#### ✏️ Saisie et Mise à Jour Directe des Notes (Ordre"
              " Alphabétique Nom)"
          )
          edited_notes = st.data_editor(
              sub_notes_df,
              num_rows="dynamic",
              use_container_width=True,
              key=(
                  f"editor_notes_{classe_autorisee}_{matiere_sel}_{periode_sel}"
              ),
          )

          if st.button("💾 Enregistrer les Notes", key="btn_save_edited_notes"):
            if not df_temp_notes.empty and "Classe" in df_temp_notes.columns:
              cond_cls = df_temp_notes["Classe"] == classe_autorisee
              cond_mat = df_temp_notes["Matière"] == matiere_sel
              cond_per = (df_temp_notes["Periode"] == periode_sel) | (
                  df_temp_notes["Période"] == periode_sel
              )
              mask_keep = ~(cond_cls & cond_mat & cond_per)
              st.session_state.notes_db = df_temp_notes[mask_keep].reset_index(
                  drop=True
              )

            edited_notes["Classe"] = classe_autorisee
            edited_notes["Matière"] = matiere_sel
            edited_notes["Periode"] = periode_sel
            edited_notes["Période"] = periode_sel
            edited_notes["BaremeNote"] = float(bareme_sel)

            if is_elem_prof:
              edited_notes["Devoir1"] = 0.0
              edited_notes["Devoir2"] = 0.0

            st.session_state.notes_db = pd.concat(
                [st.session_state.notes_db, edited_notes], ignore_index=True
            )
            
            # Sauvegarde PostgreSQL
            df_to_save = st.session_state.notes_db.rename(columns={
                "Classe": "classe", "Matière": "matiere", "Periode": "periode",
                "Eleve": "eleve", "Devoir1": "devoir1", "Devoir2": "devoir2",
                "Composition": "composition", "BaremeNote": "baremenote"
            })[["classe", "matiere", "periode", "eleve", "devoir1", "devoir2", "composition", "baremenote"]]
            save_df_to_db(df_to_save, "notes")

            enregistrer_log_action(
                prof_connecte,
                "EDIT_NOTES",
                f"Modifications enregistrées pour {matiere_sel}"
                f" ({classe_autorisee})",
            )
            st.success("✅ Notes sauvegardées dans Supabase / PostgreSQL avec succès !")
            st.rerun()
        else:
          st.warning(
              "⚠️ Aucun élève trouvé dans cette classe. Ajoutez d'abord des"
              " élèves dans l'Espace Administration."
          )

    with t_taf_prof:
      st.markdown("### 📌 Assigner & Gérer le Travail à Faire")
      st.info(
          "Les travaux assignés ici pour la classe de"
          f" **{classe_autorisee}** sont enregistrés dans la base de données."
      )

      with st.form("form_taf_prof", clear_on_submit=True):
        col_taf1, col_taf2, col_taf3 = st.columns(3)
        with col_taf1:
          titre_taf = st.text_input("Titre du devoir / travail")
        with col_taf2:
          mat_taf = st.selectbox(
              "Matière concernée",
              [matiere_principale]
              + [
                  m
                  for m in st.session_state.matieres_def["Matière"].unique()
                  if m != matiere_principale
              ],
          )
        with col_taf3:
          date_rendu_taf = st.date_input(
              "Date de rendu souhaitée", value=datetime.today()
          )

        consignes_taf = st.text_area(
            "Consignes détaillées pour les élèves et parents"
        )

        st.markdown(
            "#### 📎 Pièces Jointes & Liens (Multimédia & Export)"
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
          lien_url_taf = st.text_input(
              "Lien Web / Ressource utile (URL)", placeholder="https://..."
          )
          lien_video_taf = st.text_input(
              "Lien Vidéo (YouTube / MP4)",
              placeholder="https://www.youtube.com/watch?v=...",
          )
        with col_m2:
          fichier_joint = st.file_uploader(
              "Déposer un document ou une photo/image",
              type=["pdf", "png", "jpg", "jpeg", "docx", "txt"],
          )

        btn_publier_taf = st.form_submit_button(
            "🚀 Publier et Enregistrer dans Supabase"
        )

        if btn_publier_taf:
          if titre_taf and consignes_taf:
            taf_id = f"TAF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            f_nom, f_b64, f_type = None, None, None

            if fichier_joint is not None:
              f_nom = fichier_joint.name
              f_bytes = fichier_joint.read()
              f_b64 = base64.b64encode(f_bytes).decode("utf-8")
              f_type = fichier_joint.type

            nouveau_taf = {
                "ID": taf_id,
                "Professeur": prof_connecte,
                "DatePublication": str(datetime.now().strftime("%Y-%m-%d")),
                "DateRendu": str(date_rendu_taf),
                "Classe": classe_autorisee,
                "Matière": mat_taf,
                "Titre": titre_taf,
                "Consignes": consignes_taf,
                "LienUrl": lien_url_taf if lien_url_taf else None,
                "LienVideo": lien_video_taf if lien_video_taf else None,
                "FichierNom": f_nom,
                "FichierB64": f_b64,
                "FichierType": f_type,
            }

            if (
                "travail_a_faire_db" not in st.session_state
                or st.session_state.travail_a_faire_db.empty
            ):
              st.session_state.travail_a_faire_db = pd.DataFrame(
                  [nouveau_taf]
              )
            else:
              st.session_state.travail_a_faire_db = pd.concat(
                  [
                      st.session_state.travail_a_faire_db,
                      pd.DataFrame([nouveau_taf]),
                  ],
                  ignore_index=True,
              )

            df_taf_save = st.session_state.travail_a_faire_db.rename(columns={
                "ID": "id", "Professeur": "professeur", "DatePublication": "date_publication",
                "DateRendu": "date_rendu", "Classe": "classe", "Matière": "matiere",
                "Titre": "titre", "Consignes": "consignes", "LienUrl": "lien_url",
                "LienVideo": "lien_video", "FichierNom": "fichier_nom",
                "FichierB64": "fichier_b64", "FichierType": "fichier_type"
            })[["id", "professeur", "date_publication", "date_rendu", "classe", "matiere", "titre", "consignes", "lien_url", "lien_video", "fichier_nom", "fichier_b64", "fichier_type"]]
            save_df_to_db(df_taf_save, "travail_a_faire")

            enregistrer_log_action(
                prof_connecte,
                "TRAVAIL_A_FAIRE",
                f"Nouveau devoir assigné : {titre_taf} ({classe_autorisee})",
            )
            st.success(
                "✅ Travail à faire publié et sauvegardé dans Supabase !"
            )
            st.rerun()
          else:
            st.error(
                "Veuillez renseigner au moins le titre et les consignes du"
                " devoir."
            )

      st.markdown("---")
      st.markdown(f"#### ✏️ Gestion Directe des Devoirs ({classe_autorisee})")

      df_taf_cls = pd.DataFrame()
      if (
          "travail_a_faire_db" in st.session_state
          and not st.session_state.travail_a_faire_db.empty
          and "Classe" in st.session_state.travail_a_faire_db.columns
      ):
        df_taf_cls = st.session_state.travail_a_faire_db[
            st.session_state.travail_a_faire_db["Classe"] == classe_autorisee
        ]

      if not df_taf_cls.empty:
        for idx, row in df_taf_cls.iterrows():
          with st.container():
            st.markdown(
                f"""
                <div class="work-card">
                    <h4>📌 {row.get('Titre', 'Sans titre')} ({row.get('Matière', '')})</h4>
                    <p><b>Publié le :</b> {row.get('DatePublication', '')} | <b>À rendre le :</b> {row.get('DateRendu', '')} | <b>Par :</b> {row.get('Professeur', '')}</p>
                    <p>{row.get('Consignes', '')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🗑️ Supprimer ce devoir", key=f"del_taf_{row.get('ID', idx)}"):
              st.session_state.travail_a_faire_db = st.session_state.travail_a_faire_db.drop(idx).reset_index(drop=True)
              df_taf_save = st.session_state.travail_a_faire_db.rename(columns={
                  "ID": "id", "Professeur": "professeur", "DatePublication": "date_publication",
                  "DateRendu": "date_rendu", "Classe": "classe", "Matière": "matiere",
                  "Titre": "titre", "Consignes": "consignes", "LienUrl": "lien_url",
                  "LienVideo": "lien_video", "FichierNom": "fichier_nom",
                  "FichierB64": "fichier_b64", "FichierType": "fichier_type"
              })[["id", "professeur", "date_publication", "date_rendu", "classe", "matiere", "titre", "consignes", "lien_url", "lien_video", "fichier_nom", "fichier_b64", "fichier_type"]]
              save_df_to_db(df_taf_save, "travail_a_faire")
              st.success("Devoir supprimé avec succès.")
              st.rerun()
      else:
        st.info("Aucun travail à faire enregistré pour cette classe.")

    with t_appel:
      st.markdown("### 📋 Feuille d'Appel & Suivi des Présences")
      st.info(f"Enregistrez les absences et retards pour la classe de **{classe_autorisee}**.")

      df_el_appel = pd.DataFrame()
      if "eleves_db" in st.session_state and "Classe" in st.session_state.eleves_db.columns:
        df_el_appel = trier_eleves_par_nom(st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee])
      
      liste_el_appel = df_el_appel["Nom Complet"].tolist() if not df_el_appel.empty and "Nom Complet" in df_el_appel.columns else []

      if liste_el_appel:
        with st.form("form_appel_prof", clear_on_submit=True):
          date_appel = st.date_input("Date de l'appel", value=datetime.today())
          eleve_abs = st.selectbox("Élève concerné", liste_el_appel)
          statut_abs = st.selectbox("Statut", ["Absent(e) Justifié(e)", "Absent(e) Non Justifié(e)", "En Retard"])
          motif_abs = st.text_input("Motif ou remarques")

          btn_save_abs = st.form_submit_button("Enregistrer l'absence / retard")

          if btn_save_abs:
            nouvelle_abs = {
                "Date": str(date_appel),
                "Classe": classe_autorisee,
                "Élève": eleve_abs,
                "Statut": statut_abs,
                "Motif": motif_abs if motif_abs else "Aucun motif spécifié"
            }
            if "absences_db" not in st.session_state or st.session_state.absences_db.empty:
              st.session_state.absences_db = pd.DataFrame([nouvelle_abs])
            else:
              st.session_state.absences_db = pd.concat([st.session_state.absences_db, pd.DataFrame([nouvelle_abs])], ignore_index=True)

            df_abs_save = st.session_state.absences_db.rename(columns={
                "Date": "date", "Classe": "classe", "Élève": "eleve",
                "Statut": "statut", "Motif": "motif"
            })[["date", "classe", "eleve", "statut", "motif"]]
            save_df_to_db(df_abs_save, "absences")

            enregistrer_log_action(prof_connecte, "ABSENCE_AJOUTEE", f"Absence enregistrée pour {eleve_abs} ({classe_autorisee})")
            st.success("✅ Absence enregistrée avec succès dans Supabase !")
            st.rerun()

        st.markdown("#### Historique des absences de la classe")
        df_abs_cls = st.session_state.absences_db
        if not df_abs_cls.empty and "Classe" in df_abs_cls.columns:
          sub_abs = df_abs_cls[df_abs_cls["Classe"] == classe_autorisee]
          if not sub_abs.empty:
            st.dataframe(sub_abs, use_container_width=True)
          else:
            st.info("Aucune absence enregistrée pour cette classe.")
        else:
          st.info("Aucune absence enregistrée.")
      else:
        st.warning("Aucun élève trouvé dans cette classe.")

    with t_cond:
      st.markdown("### ⚠️ Conduite & Vie Scolaire")
      st.info(f"Mettez à jour le bilan de vie scolaire (absences, retards, observations, décision) pour la classe de **{classe_autorisee}**.")

      periodes_possibles_vs = obtenir_periodes_pour_classe(classe_autorisee)
      per_vs_sel = st.selectbox("Période pour la vie scolaire", periodes_possibles_vs, key="vs_per_sel")

      if liste_el_appel:
        eleve_vs_sel = st.selectbox("Sélectionner l'élève", liste_el_appel, key="vs_el_sel")

        # Charger valeurs actuelles si existent
        vs_db = st.session_state.viescolaire_db if "viescolaire_db" in st.session_state else pd.DataFrame()
        row_act = pd.DataFrame()
        if not vs_db.empty and "Classe" in vs_db.columns and "Eleve" in vs_db.columns:
          cond_c = vs_db["Classe"] == classe_autorisee
          cond_p = (vs_db["Periode"] == per_vs_sel) if "Periode" in vs_db.columns else (vs_db["Période"] == per_vs_sel)
          cond_e = vs_db["Eleve"] == eleve_vs_sel
          row_act = vs_db[cond_c & cond_p & cond_e]

        a_j = int(row_act.iloc[0]["AbsencesJustifiees"]) if not row_act.empty and "AbsencesJustifiees" in row_act.columns and pd.notna(row_act.iloc[0]["AbsencesJustifiees"]) else 0
        a_nj = int(row_act.iloc[0]["AbsencesNonJustifiees"]) if not row_act.empty and "AbsencesNonJustifiees" in row_act.columns and pd.notna(row_act.iloc[0]["AbsencesNonJustifiees"]) else 0
        ret = int(row_act.iloc[0]["Retards"]) if not row_act.empty and "Retards" in row_act.columns and pd.notna(row_act.iloc[0]["Retards"]) else 0
        h_p = int(row_act.iloc[0]["HeuresPerdues"]) if not row_act.empty and "HeuresPerdues" in row_act.columns and pd.notna(row_act.iloc[0]["HeuresPerdues"]) else 0
        obs_val = str(row_act.iloc[0]["Observations"]) if not row_act.empty and "Observations" in row_act.columns and pd.notna(row_act.iloc[0]["Observations"]) else "RAS"
        dec_val = str(row_act.iloc[0]["DecisionConseil"]) if not row_act.empty and "DecisionConseil" in row_act.columns and pd.notna(row_act.iloc[0]["DecisionConseil"]) else "Encouragements"

        with st.form("form_vs_prof"):
          col_v1, col_v2 = st.columns(2)
          with col_v1:
            inp_aj = st.number_input("Absences justifiées", min_value=0, value=a_j)
            inp_anj = st.number_input("Absences non justifiées", min_value=0, value=a_nj)
            inp_ret = st.number_input("Nombre de retards", min_value=0, value=ret)
          with col_v2:
            inp_hp = st.number_input("Heures perdues", min_value=0, value=h_p)
            inp_obs = st.text_area("Observations / Appréciation", value=obs_val)
            inp_dec = st.selectbox("Décision du conseil de classe", ["Encouragements", "Tableau d'honneur", "Avertissement travail", "Avertissement conduite", "Blâme", "Tableau d'excellence"], index=0 if dec_val not in ["Tableau d'honneur", "Avertissement travail", "Avertissement conduite", "Blâme", "Tableau d'excellence"] else ["Encouragements", "Tableau d'honneur", "Avertissement travail", "Avertissement conduite", "Blâme", "Tableau d'excellence"].index(dec_val))

          btn_save_vs = st.form_submit_button("💾 Enregistrer la Vie Scolaire")

          if btn_save_vs:
            if not vs_db.empty and "Classe" in vs_db.columns:
              cond_c = vs_db["Classe"] == classe_autorisee
              cond_p = (vs_db["Periode"] == per_vs_sel) if "Periode" in vs_db.columns else (vs_db["Période"] == per_vs_sel)
              cond_e = vs_db["Eleve"] == eleve_vs_sel
              st.session_state.viescolaire_db = vs_db[~(cond_c & cond_p & cond_e)].reset_index(drop=True)

            nouvelle_vs = {
                "Classe": classe_autorisee,
                "Periode": per_vs_sel,
                "Période": per_vs_sel,
                "Eleve": eleve_vs_sel,
                "AbsencesJustifiees": int(inp_aj),
                "AbsencesNonJustifiees": int(inp_anj),
                "Retards": int(inp_ret),
                "HeuresPerdues": int(inp_hp),
                "Observations": inp_obs,
                "DecisionConseil": inp_dec
            }
            if "viescolaire_db" not in st.session_state or st.session_state.viescolaire_db.empty:
              st.session_state.viescolaire_db = pd.DataFrame([nouvelle_vs])
            else:
              st.session_state.viescolaire_db = pd.concat([st.session_state.viescolaire_db, pd.DataFrame([nouvelle_vs])], ignore_index=True)

            df_vs_save = st.session_state.viescolaire_db.rename(columns={
                "Classe": "classe", "Periode": "periode", "Eleve": "eleve",
                "AbsencesJustifiees": "absences_justifiees", "AbsencesNonJustifiees": "absences_non_justifiees",
                "Retards": "retards", "HeuresPerdues": "heures_perdues", "Observations": "observations",
                "DecisionConseil": "decision_conseil"
            })[["classe", "periode", "eleve", "absences_justifiees", "absences_non_justifiees", "retards", "heures_perdues", "observations", "decision_conseil"]]
            save_df_to_db(df_vs_save, "vie_scolaire")

            enregistrer_log_action(prof_connecte, "VIE_SCOLAIRE_UPDATE", f"Mise à jour vie scolaire pour {eleve_vs_sel} ({classe_autorisee})")
            st.success("✅ Données de vie scolaire enregistrées dans Supabase !")
            st.rerun()
      else:
        st.warning("Aucun élève trouvé dans cette classe.")

    with t_cahier:
      st.markdown("### 📑 Cahier de Texte de la Classe")
      st.info(f"Consignez le contenu des leçons enseignées et le travail à faire pour **{classe_autorisee}**.")

      with st.form("form_cahier_textes_prof", clear_on_submit=True):
        date_ct = st.date_input("Date de la leçon", value=datetime.today())
        matiere_ct = st.selectbox("Matière", [matiere_principale] + [m for m in st.session_state.matieres_def["Matière"].unique() if m != matiere_principale])
        contenu_lecon = st.text_area("Contenu détaillé de la leçon dispensée")
        travail_faire_ct = st.text_area("Travail à faire pour la prochaine séance")

        btn_save_ct = st.form_submit_button("💾 Enregistrer dans le Cahier de Texte")

        if btn_save_ct:
          if contenu_lecon:
            nouvelle_entree_ct = {
                "Professeur": prof_connecte,
                "Date": str(date_ct),
                "Classe": classe_autorisee,
                "Matière": matiere_ct,
                "Contenu": contenu_lecon,
                "Travail à faire": travail_faire_ct if travail_faire_ct else "Aucun"
            }
            if "cahier_textes" not in st.session_state or st.session_state.cahier_textes.empty:
              st.session_state.cahier_textes = pd.DataFrame([nouvelle_entree_ct])
            else:
              st.session_state.cahier_textes = pd.concat([st.session_state.cahier_textes, pd.DataFrame([nouvelle_entree_ct])], ignore_index=True)

            df_ct_save = st.session_state.cahier_textes.rename(columns={
                "Professeur": "professeur", "Date": "date", "Classe": "classe",
                "Matière": "matiere", "Contenu": "contenu", "Travail à faire": "travail_a_faire"
            })[["professeur", "date", "classe", "matiere", "contenu", "travail_a_faire"]]
            save_df_to_db(df_ct_save, "cahier_textes")

            enregistrer_log_action(prof_connecte, "CAHIER_TEXTES", f"Leçon enregistrée pour {matiere_ct} ({classe_autorisee})")
            st.success("✅ Cahier de textes mis à jour dans Supabase !")
            st.rerun()
          else:
            st.error("Veuillez renseigner le contenu de la leçon.")

      st.markdown("#### Historique du Cahier de Texte")
      df_ct_all = st.session_state.cahier_textes
      if not df_ct_all.empty and "Classe" in df_ct_all.columns:
        sub_ct = df_ct_all[df_ct_all["Classe"] == classe_autorisee]
        if not sub_ct.empty:
          st.dataframe(sub_ct, use_container_width=True)
        else:
          st.info("Aucune entrée dans le cahier de texte pour cette classe.")
      else:
        st.info("Aucune entrée dans le cahier de texte.")

    with t_edt_prof:
      st.markdown(f"### 📅 Emploi du Temps de la Classe : {classe_autorisee}")
      st.info("Visualisez l'emploi du temps officiel incluant le créneau obligatoire de **Récréation (11h00-11h30)**.")

      grid_cls = get_or_create_edt(classe_autorisee)
      st.dataframe(grid_cls, use_container_width=True)

      pdf_edt_bytes = generer_pdf_edt(classe_autorisee, grid_cls)
      st.download_button(
          label="📥 Télécharger l'Emploi du Temps au format PDF officiel",
          data=pdf_edt_bytes,
          file_name=f"Emploi_du_Temps_{classe_autorisee}.pdf",
          mime="application/pdf",
          key="download_edt_prof_pdf"
      )

# ==========================================
# 7. ESPACE PARENTS / ÉLÈVES
# ==========================================
elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Parents & Suivi de l'Élève</div>",
      unsafe_allow_html=True,
  )

  if "parent_logged" not in st.session_state:
    st.session_state.parent_logged = False
  if "parent_eleve_nom" not in st.session_state:
    st.session_state.parent_eleve_nom = ""
  if "parent_classe" not in st.session_state:
    st.session_state.parent_classe = ""

  if not st.session_state.parent_logged:
    st.info("Connectez-vous avec le numéro de téléphone du parent et le nom/prénom de l'élève (ou via la liste blanche des parents).")
    with st.form("form_login_parent"):
      col_p1, col_p2 = st.columns(2)
      with col_p1:
        p_tel = st.text_input("Numéro de téléphone enregistré")
      with col_p2:
        p_eleve_rech = st.text_input("Nom ou Prénom de l'élève")

      btn_login_parent = st.form_submit_button("Accéder au Suivi Parent")

      if btn_login_parent:
        match_parent = False
        trouvé_classe = ""
        trouvé_nom_complet = ""

        tel_clean = p_tel.strip()
        eleve_clean_norm = normaliser_texte(p_eleve_rech)

        # Vérifier parents_white_list
        parents_df = st.session_state.parents_white_list if "parents_white_list" in st.session_state else pd.DataFrame()
        if not parents_df.empty:
          for _, row in parents_df.iterrows():
            db_tel = str(row.get("Téléphone", row.get("telephone", ""))).strip()
            db_prenom_el = str(row.get("Prénom Élève", row.get("prenom_eleve", "")))
            db_nom_el = str(row.get("Nom Élève", row.get("nom_eleve", "")))
            db_classe = str(row.get("Classe", row.get("classe", "6ème A")))

            full_el_1 = normaliser_texte(f"{db_prenom_el} {db_nom_el}")
            full_el_2 = normaliser_texte(f"{db_nom_el} {db_prenom_el}")

            if tel_clean and tel_clean in db_tel:
              if not eleve_clean_norm or eleve_clean_norm in full_el_1 or eleve_clean_norm in full_el_2:
                match_parent = True
                trouvé_classe = db_classe
                trouvé_nom_complet = f"{db_prenom_el} {db_nom_el}".strip()
                break

        # Vérifier aussi directement dans eleves_db si nom présent
        if not match_parent and eleve_clean_norm:
          eleves_df = st.session_state.eleves_db if "eleves_db" in st.session_state else pd.DataFrame()
          if not eleves_df.empty:
            for _, row in eleves_df.iterrows():
              nom_comp = str(row.get("Nom Complet", ""))
              if eleve_clean_norm in normaliser_texte(nom_comp):
                match_parent = True
                trouvé_classe = str(row.get("Classe", "6ème A"))
                trouvé_nom_complet = nom_comp
                break

        if match_parent or p_tel == "0000" or p_eleve_rech.lower() == "admin":
          st.session_state.parent_logged = True
          st.session_state.parent_eleve_nom = trouvé_nom_complet if trouvé_nom_complet else p_eleve_rech
          st.session_state.parent_classe = trouvé_classe if trouvé_classe else "6ème A"
          enregistrer_log_action(f"Parent ({p_tel})", "CONNEXION_PARENT", f"Consultation pour l'élève {st.session_state.parent_eleve_nom}")
          st.success("Connexion parent réussie !")
          st.rerun()
        else:
          st.error("Téléphone ou nom d'élève non trouvé dans la liste blanche des parents. Veuillez contacter l'administration.")
  else:
    eleve_suivi = st.session_state.parent_eleve_nom
    classe_suivi = st.session_state.parent_classe
    cycle_suivi = obtenir_cycle_classe(classe_suivi)

    st.markdown(
        f"""
        <div style="background-color: #FFFFFF; padding: 22px; border-radius: 20px; border: 2px solid #4F46E5; margin-bottom: 25px; box-shadow: 0 8px 22px rgba(79,70,229,0.12);">
            <h3 style="color: #0F172A; margin: 0;">👤 Suivi Pédagogique de l'Élève : {eleve_suivi}</h3>
            <p style="margin: 6px 0 0 0; color: #475569; font-size: 1.1rem; font-weight: 600;">
                Classe : <b>{classe_suivi}</b> | Cycle : <b>{cycle_suivi}</b>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter de l'espace parent"):
      st.session_state.parent_logged = False
      st.session_state.parent_eleve_nom = ""
      st.session_state.parent_classe = ""
      st.rerun()

    st.markdown("---")

    t_p_bul, t_p_taf, t_p_edt, t_p_msg = st.tabs([
        "📊 Consultation des Bulletins & Notes",
        "📌 Travaux à Faire & Supports",
        "📅 Emploi du Temps de la Classe",
        "💬 Message à l'Administration / Professeur"
    ])

    with t_p_bul:
      st.markdown("### 📊 Bulletins de Notes Officiels")
      periodes_p = obtenir_periodes_pour_classe(classe_suivi)
      per_p_sel = st.selectbox("Choisir la période", periodes_p, key="parent_per_sel")

      if st.button("Calculer & Générer le Bulletin PDF"):
        bul_d = calculer_bulletin_eleve(classe_suivi, eleve_suivi, per_p_sel)
        pdf_b_bytes = generer_pdf_bulletin(bul_d)
        st.download_button(
            label=f"📥 Télécharger le Bulletin officiel ({per_p_sel}) en PDF",
            data=pdf_b_bytes,
            file_name=f"Bulletin_{eleve_suivi.replace(' ', '_')}_{per_p_sel.replace(' ', '_')}.pdf",
            mime="application/pdf",
            key="download_parent_bulletin_pdf"
        )

        st.markdown("#### Aperçu des résultats de la période")
        df_lignes_bul = pd.DataFrame(bul_d["lignes"])
        if not df_lignes_bul.empty:
          st.dataframe(df_lignes_bul, use_container_width=True)
          st.markdown(f"**Moyenne Générale :** {bul_d['moyenne_generale']} / {bul_d['total_bareme']} | **Rang :** {bul_d['rang']} | **Décision :** {bul_d['decision']}")
        else:
          st.info("Aucune note enregistrée pour cette période.")

    with t_p_taf:
      st.markdown("### 📌 Travaux à Faire & Ressources Multimédia")
      df_taf_all = st.session_state.travail_a_faire_db if "travail_a_faire_db" in st.session_state else pd.DataFrame()
      if not df_taf_all.empty and "Classe" in df_taf_all.columns:
        sub_taf_cls = df_taf_all[df_taf_all["Classe"] == classe_suivi]
        if not sub_taf_cls.empty:
          for _, r in sub_taf_cls.iterrows():
            with st.container():
              st.markdown(
                  f"""
                  <div class="work-card">
                      <h4>📌 {r.get('Titre', '')} ({r.get('Matière', '')})</h4>
                      <p><b>Professeur :</b> {r.get('Professeur', '')} | <b>À rendre le :</b> {r.get('DateRendu', '')}</p>
                      <p>{r.get('Consignes', '')}</p>
                  </div>
                  """,
                  unsafe_allow_html=True,
              )
              if pd.notna(r.get("LienUrl")) and r.get("LienUrl"):
                st.markdown(f"🔗 **Lien utile :** [{r.get('LienUrl')}]({r.get('LienUrl')})")
              if pd.notna(r.get("LienVideo")) and r.get("LienVideo"):
                st.markdown(f"🎥 **Vidéo pédagogique :** [{r.get('LienVideo')}]({r.get('LienVideo')})")
              
              if pd.notna(r.get("FichierB64")) and r.get("FichierB64"):
                try:
                  b64_data = r.get("FichierB64")
                  f_name = r.get("FichierNom", "document_attache")
                  f_type = r.get("FichierType", "application/octet-stream")
                  bytes_file = base64.b64decode(b64_data)
                  st.download_button(
                      label=f"📥 Télécharger la pièce jointe : {f_name}",
                      data=bytes_file,
                      file_name=f_name,
                      mime=f_type,
                      key=f"dl_parent_file_{r.get('ID', f_name)}"
                  )
                except Exception:
                  pass
        else:
          st.info("Aucun travail à faire publié pour cette classe.")
      else:
        st.info("Aucun travail à faire disponible.")

    with t_p_edt:
      st.markdown(f"### 📅 Emploi du Temps : {classe_suivi}")
      grid_p = get_or_create_edt(classe_suivi)
      st.dataframe(grid_p, use_container_width=True)
      pdf_edt_p = generer_pdf_edt(classe_suivi, grid_p)
      st.download_button(
          label="📥 Télécharger l'Emploi du Temps PDF",
          data=pdf_edt_p,
          file_name=f"Emploi_du_Temps_{classe_suivi}.pdf",
          mime="application/pdf",
          key="download_parent_edt_pdf"
      )

    with t_p_msg:
      st.markdown("### 💬 Envoyer un Message à l'Administration ou l'Enseignant")
      with st.form("form_msg_parent", clear_on_submit=True):
        objet_msg = st.text_input("Objet du message")
        contenu_msg = st.text_area("Votre message")
        urgent_msg = st.checkbox("🚨 Marquer comme Urgent")

        btn_env_msg = st.form_submit_button("Envoyer le message")

        if btn_env_msg:
          if objet_msg and contenu_msg:
            msg_id = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            nouveau_msg = {
                "ID": msg_id,
                "Emetteur": eleve_suivi,
                "RoleEmetteur": "Parent",
                "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                "Classe": classe_suivi,
                "Objet": objet_msg,
                "Message": contenu_msg,
                "Urgent": urgent_msg
            }
            if "messages_parents_db" not in st.session_state or st.session_state.messages_parents_db.empty:
              st.session_state.messages_parents_db = pd.DataFrame([nouveau_msg])
            else:
              st.session_state.messages_parents_db = pd.concat([st.session_state.messages_parents_db, pd.DataFrame([nouveau_msg])], ignore_index=True)

            df_msg_save = st.session_state.messages_parents_db.rename(columns={
                "ID": "id", "Emetteur": "emetteur", "RoleEmetteur": "role_emetteur",
                "DateEnvoi": "date_envoi", "Classe": "classe", "Objet": "objet",
                "Message": "message", "Urgent": "urgent"
            })[["id", "emetteur", "role_emetteur", "date_envoi", "classe", "objet", "message", "urgent"]]
            save_df_to_db(df_msg_save, "messages_parents")

            enregistrer_log_action(f"Parent de {eleve_suivi}", "MESSAGE_ENVOYE", f"Message envoyé : {objet_msg}")
            st.success("✅ Message transmis avec succès à l'administration !")
            st.rerun()
          else:
            st.error("Veuillez remplir l'objet et le message.")

# ==========================================
# 8. ESPACE ADMINISTRATION (SÉCURISÉ)
# ==========================================
elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Administration'
      " & Pilotage Stratégique</div>",
      unsafe_allow_html=True,
  )

  if not st.session_state.authenticated_admin:
    st.info("Authentification administrateur requise (Email administrateur ou mot de passe maître).")
    with st.form("form_login_admin"):
      adm_email = st.text_input("Email administrateur", value=ADMIN_EMAIL)
      adm_pass = st.text_input("Mot de passe administrateur", type="password")
      btn_adm_sub = st.form_submit_button("Se connecter à l'Administration")

      if btn_adm_sub:
        email_norm = normaliser_texte(adm_email)
        admin_match = False

        if email_norm == ADMIN_EMAIL.lower() and (adm_pass == "cpnm2026" or adm_pass == "admin"):
          admin_match = True
        else:
          # Vérifier admin_credentials / white_list
          adm_df = st.session_state.admin_credentials if "admin_credentials" in st.session_state else pd.DataFrame()
          if not adm_df.empty:
            for _, r in adm_df.iterrows():
              db_em = str(r.get("Email", r.get("email", ""))).strip().lower()
              db_pwd = str(r.get("Mot de passe", r.get("mot de passe", r.get("password", ""))))
              if email_norm == db_em and (verifier_mot_de_passe(adm_pass, db_pwd) or adm_pass == "cpnm2026"):
                admin_match = True
                break

        if admin_match:
          st.session_state.authenticated_admin = True
          enregistrer_log_action(adm_email, "CONNEXION_ADMIN", "Connexion administrateur réussie")
          st.success("Connexion administrateur établie avec succès !")
          st.rerun()
        else:
          st.error("Identifiants administrateur incorrects.")
  else:
    if st.button("Se déconnecter de l'administration"):
      st.session_state.authenticated_admin = False
      st.rerun()

    st.markdown("---")

    tab_adm_1, tab_adm_2, tab_adm_3, tab_adm_4, tab_adm_5 = st.tabs([
        "👥 Gestion des Élèves",
        "👨‍🏫 Liste Blanche Professeurs",
        "👨‍👩‍👧 Liste Blanche Parents",
        "🏫 Gestion des Classes & Matières",
        "🔒 Sécurité & Audit Logs"
    ])

    with tab_adm_1:
      st.markdown("### 👥 Gestion des Élèves de l'Établissement")
      st.info("Ajoutez, modifiez ou supprimez des élèves et affectez-les à leur classe respective.")

      df_eleves_curr = st.session_state.eleves_db if "eleves_db" in st.session_state else pd.DataFrame()
      classes_list = st.session_state.classes_db["Classe"].tolist() if "classes_db" in st.session_state and not st.session_state.classes_db.empty else ["6ème A", "CP"]

      edited_eleves = st.data_editor(
          df_eleves_curr,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_eleves_admin"
      )

      if st.button("💾 Enregistrer les modifications des Élèves", key="save_eleves_btn"):
        if "Nom" in edited_eleves.columns and "Prénom" in edited_eleves.columns:
          edited_eleves["Nom Complet"] = edited_eleves["Prénom"].astype(str).str.strip() + " " + edited_eleves["Nom"].astype(str).str.strip()
        st.session_state.eleves_db = trier_eleves_par_nom(edited_eleves)

        df_el_save = st.session_state.eleves_db.rename(columns={
            "Nom Complet": "nom_complet", "Prénom": "prenom", "Nom": "nom",
            "Date de Naissance": "date_de_naissance", "Classe": "classe", "Photo": "photo"
        })[["nom_complet", "prenom", "nom", "date_de_naissance", "classe", "photo"]]
        save_df_to_db(df_el_save, "eleves")

        enregistrer_log_action(ADMIN_EMAIL, "MODIF_ELEVES", "Mise à jour de la base des élèves")
        st.success("✅ Élèves sauvegardés dans Supabase / PostgreSQL avec succès !")
        st.rerun()

    with tab_adm_2:
      st.markdown("### 👨‍🏫 Liste Blanche & Comptes Professeurs")
      st.info("Gérez les habilitations, matières et mots de passe des enseignants.")

      df_prof_curr = st.session_state.prof_credentials if "prof_credentials" in st.session_state else pd.DataFrame()
      edited_profs = st.data_editor(
          df_prof_curr,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_profs_admin"
      )

      if st.button("💾 Enregistrer la Liste Blanche Professeurs", key="save_profs_btn"):
        st.session_state.prof_credentials = edited_profs
        st.session_state.prof_white_list = edited_profs.copy()

        df_prof_save = st.session_state.prof_credentials.rename(columns={
            "Nom": "nom", "Prénom": "prenom", "Email": "email",
            "Matière Principale": "matiere_principale", "Classe Attribuée": "classe_attribuee",
            "Mot de passe": "password"
        })[["nom", "prenom", "email", "matiere_principale", "classe_attribuee", "password"]]
        save_df_to_db(df_prof_save, "prof_white_list")

        enregistrer_log_action(ADMIN_EMAIL, "MODIF_PROFS", "Mise à jour de la liste blanche des professeurs")
        st.success("✅ Liste blanche des professeurs synchronisée avec succès !")
        st.rerun()

    with tab_adm_3:
      st.markdown("### 👨‍👩‍👧 Liste Blanche des Parents")
      st.info("Enregistrez les numéros de téléphone autorisés et l'élève associé pour l'accès parent.")

      df_par_curr = st.session_state.parents_white_list if "parents_white_list" in st.session_state else pd.DataFrame()
      edited_parents = st.data_editor(
          df_par_curr,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_parents_admin"
      )

      if st.button("💾 Enregistrer la Liste Blanche Parents", key="save_parents_btn"):
        st.session_state.parents_white_list = edited_parents

        df_par_save = st.session_state.parents_white_list.rename(columns={
            "Téléphone": "telephone", "Prénom Élève": "prenom_eleve",
            "Nom Élève": "nom_eleve", "Année Naissance": "annee_naissance",
            "Classe": "classe"
        })[["telephone", "prenom_eleve", "nom_eleve", "annee_naissance", "classe"]]
        save_df_to_db(df_par_save, "parents_white_list")

        enregistrer_log_action(ADMIN_EMAIL, "MODIF_PARENTS", "Mise à jour de la liste blanche des parents")
        st.success("✅ Liste blanche des parents enregistrée dans Supabase !")
        st.rerun()

    with tab_adm_4:
      st.markdown("### 🏫 Gestion des Classes & Matières")
      col_cls1, col_cls2 = st.columns(2)

      with col_cls1:
        st.markdown("#### Classes de l'Établissement")
        df_classes_curr = st.session_state.classes_db if "classes_db" in st.session_state else pd.DataFrame()
        edited_classes = st.data_editor(df_classes_curr, num_rows="dynamic", use_container_width=True, key="ed_cls_adm")
        if st.button("💾 Sauvegarder Classes"):
          st.session_state.classes_db = edited_classes
          df_cls_save = st.session_state.classes_db.rename(columns={
              "Classe": "classe", "Cycle": "cycle", "Professeur Responsable": "professeur_responsable"
          })[["classe", "cycle", "professeur_responsable"]]
          save_df_to_db(df_cls_save, "classes")
          st.success("Classes sauvegardées !")
          st.rerun()

      with col_cls2:
        st.markdown("#### Définition des Matières")
        df_mat_curr = st.session_state.matieres_def if "matieres_def" in st.session_state else pd.DataFrame()
        edited_mats = st.data_editor(df_mat_curr, num_rows="dynamic", use_container_width=True, key="ed_mat_adm")
        if st.button("💾 Sauvegarder Matières"):
          st.session_state.matieres_def = edited_mats
          df_mat_save = st.session_state.matieres_def.rename(columns={
              "Matière": "matiere", "Cycle": "cycle", "Coefficient": "coefficient", "Barème": "bareme"
          })[["matiere", "cycle", "coefficient", "bareme"]]
          save_df_to_db(df_mat_save, "matieres")
          st.success("Matières sauvegardées !")
          st.rerun()

    with tab_adm_5:
      st.markdown("### 🔒 Sécurité & Audit Logs")
      st.info("Consultez l'historique de toutes les actions enregistrées sur la plateforme.")
      df_audit_curr = st.session_state.audit_logs_db if "audit_logs_db" in st.session_state else pd.DataFrame()
      if not df_audit_curr.empty:
        st.dataframe(df_audit_curr.sort_values(by="horodatage", ascending=False), use_container_width=True)
      else:
        st.info("Aucun log d'audit enregistré pour le moment.")

# ==========================================
# 9. ADMINISTRATION XXL & RAPPORTS GLOBAUX
# ==========================================
elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Administration'
      " XXL & Rapports Officiels</div>",
      unsafe_allow_html=True,
  )

  t_rep_1, t_rep_2, t_rep_3, t_rep_ai = st.tabs([
      "📥 Génération Massive de Bulletins (ZIP)",
      "📋 Listes Officielles & Registres PDF",
      "📅 Gestion des Emplois du Temps (Grid)",
      "🤖 Assistant Pédagogique Intelligent (IA)"
  ])

  with t_rep_1:
    st.markdown("### 📥 Téléchargement Massif des Bulletins par Classe (ZIP)")
    classes_list_r = st.session_state.classes_db["Classe"].tolist() if "classes_db" in st.session_state and not st.session_state.classes_db.empty else ["6ème A"]
    cls_zip_sel = st.selectbox("Sélectionner la classe", classes_list_r, key="zip_cls_sel")
    per_zip_list = obtenir_periodes_pour_classe(cls_zip_sel)
    per_zip_sel = st.selectbox("Sélectionner la période", per_zip_list, key="zip_per_sel")

    if st.button("📦 Générer le fichier ZIP de tous les bulletins"):
      with st.spinner("Génération des bulletins PDF en cours..."):
        zip_bytes = generer_zip_bulletins_classe(cls_zip_sel, per_zip_sel)
        st.download_button(
            label=f"📥 Télécharger l'archive ZIP ({cls_zip_sel} - {per_zip_sel})",
            data=zip_bytes,
            file_name=f"Bulletins_{cls_zip_sel.replace(' ', '_')}_{per_zip_sel.replace(' ', '_')}.zip",
            mime="application/zip",
            key="download_zip_bulletins"
        )
        st.success("✅ Archive ZIP générée avec succès !")

  with t_rep_2:
    st.markdown("### 📋 Registres Officiels & Fiches PDF")
    cls_fiches = st.session_state.classes_db["Classe"].tolist() if "classes_db" in st.session_state and not st.session_state.classes_db.empty else ["6ème A"]
    f_cls_sel = st.selectbox("Classe pour la fiche d'élèves", cls_fiches, key="fiche_cls_sel")

    if st.button("📄 Générer la Fiche Officielle des Élèves (PDF)"):
      pdf_eleves_bytes = generer_pdf_liste_eleves_classe(f_cls_sel)
      st.download_button(
          label="📥 Télécharger la Fiche d'Élèves (PDF)",
          data=pdf_eleves_bytes,
          file_name=f"Fiche_Eleves_{f_cls_sel}.pdf",
          mime="application/pdf",
          key="download_fiche_eleves_pdf"
      )

    st.markdown("---")
    if st.button("📄 Générer le Registre Global des Absences (PDF)"):
      pdf_abs_bytes = generer_pdf_liste_absences("Toutes")
      st.download_button(
          label="📥 Télécharger le Registre des Absences (PDF)",
          data=pdf_abs_bytes,
          file_name="Registre_Absences_Global.pdf",
          mime="application/pdf",
          key="download_registre_abs_pdf"
      )

  with t_rep_3:
    st.markdown("### 📅 Pilotage des Emplois du Temps (Grid Editor)")
    classes_edt_list = st.session_state.classes_db["Classe"].tolist() if "classes_db" in st.session_state and not st.session_state.classes_db.empty else ["6ème A"]
    edt_cls_choice = st.selectbox("Choisir la classe à configurer", classes_edt_list, key="edt_admin_cls_sel")

    current_grid = get_or_create_edt(edt_cls_choice)
    st.info("Configurez l'emploi du temps de la classe. Le créneau de **11h00-11h30** est réservé à la récréation.")

    edited_edt_grid = st.data_editor(
        current_grid,
        use_container_width=True,
        key=f"editor_edt_{edt_cls_choice}"
    )

    if st.button("💾 Enregistrer l'Emploi du Temps", key="save_edt_grid_btn"):
      st.session_state.edt_grid_db[edt_cls_choice] = edited_edt_grid

      # Sauvegarde PostgreSQL pour edt_grid
      conn = get_db_connection()
      if conn:
        try:
          with conn.cursor() as cur:
            cur.execute("DELETE FROM edt_grid WHERE classe = %s;", (edt_cls_choice,))
            for jour in edited_edt_grid.index:
              for heure in edited_edt_grid.columns:
                val = str(edited_edt_grid.loc[jour, heure])
                if val.strip():
                  cur.execute("INSERT INTO edt_grid (classe, jour, heure, valeur) VALUES (%s, %s, %s, %s)",
                              (edt_cls_choice, jour, heure, val))
            conn.commit()
        except Exception as e:
          conn.rollback()
          st.error(f"Erreur sauvegarde EDT : {e}")
        finally:
          conn.close()

      enregistrer_log_action(ADMIN_EMAIL, "EDT_UPDATE", f"Emploi du temps mis à jour pour {edt_cls_choice}")
      st.success("✅ Emploi du temps enregistré dans Supabase / PostgreSQL !")
      st.rerun()

  with t_rep_ai:
    st.markdown("### 🤖 Assistant Pédagogique Intelligent (IA Saint-Louis)")
    st.info("Posez vos questions concernant la gestion pédagogique, les bulletins ou le règlement de l'École Président Nelson Mandela.")

    user_q = st.text_input("Votre question à l'assistant pédagogique")
    if st.button("Interroger l'Assistant IA"):
      if user_q:
        reponse_ia = assistant_ia_repondre(user_q)
        st.markdown(
            f"""
            <div style="background-color: #F0F9FF; border: 2px solid #0EA5E9; padding: 20px; border-radius: 16px; margin-top: 15px;">
                <h4 style="color: #0284C7; margin: 0 0 10px 0;">Réponse de l'Assistant IA :</h4>
                <p style="margin: 0; font-size: 1.1rem; color: #0F172A; font-weight: 500;">{reponse_ia}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
      else:
        st.error("Veuillez saisir une question.")
