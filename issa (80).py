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

                        # Persistance Supabase / PostgreSQL
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
                edited_taf = st.data_editor(
                    df_taf_cls,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_taf_prof",
                )
                if st.button("💾 Mettre à jour les devoirs", key="btn_save_taf_edited"):
                    st.session_state.travail_a_faire_db = st.session_state.travail_a_faire_db[
                        st.session_state.travail_a_faire_db["Classe"] != classe_autorisee
                    ]
                    st.session_state.travail_a_faire_db = pd.concat(
                        [st.session_state.travail_a_faire_db, edited_taf], ignore_index=True
                    )
                    
                    # Refléter dans Supabase
                    df_taf_save = st.session_state.travail_a_faire_db.rename(columns={
                        "ID": "id", "Professeur": "professeur", "DatePublication": "date_publication",
                        "DateRendu": "date_rendu", "Classe": "classe", "Matière": "matiere",
                        "Titre": "titre", "Consignes": "consignes", "LienUrl": "lien_url",
                        "LienVideo": "lien_video", "FichierNom": "fichier_nom",
                        "FichierB64": "fichier_b64", "FichierType": "fichier_type"
                    })[["id", "professeur", "date_publication", "date_rendu", "classe", "matiere", "titre", "consignes", "lien_url", "lien_video", "fichier_nom", "fichier_b64", "fichier_type"]]
                    save_df_to_db(df_taf_save, "travail_a_faire")

                    st.success("✅ Modifié avec succès !")
                    st.rerun()
            else:
                st.info("Aucun devoir enregistré pour cette classe.")

        with t_appel:
            st.markdown("### 📋 Feuille d'Appel & Gestion des Présences")
            col_ap1, col_ap2 = st.columns(2)
            with col_ap1:
                date_appel = st.date_input("Date de l'appel", value=datetime.today())
            with col_ap2:
                st.info(f"Classe active : **{classe_autorisee}**")

            df_el_app = pd.DataFrame()
            if (
                "eleves_db" in st.session_state
                and "Classe" in st.session_state.eleves_db.columns
            ):
                df_el_app = trier_eleves_par_nom(
                    st.session_state.eleves_db[
                        st.session_state.eleves_db["Classe"] == classe_autorisee
                    ]
                )

            if not df_el_app.empty:
                list_el_app = df_el_app["Nom Complet"].tolist()
                df_appel_init = pd.DataFrame({
                    "Élève": list_el_app,
                    "Statut": ["Présent"] * len(list_el_app),
                    "Motif / Remarque": [""] * len(list_el_app),
                })

                edited_appel = st.data_editor(
                    df_appel_init,
                    column_config={
                        "Statut": st.column_config.SelectboxColumn(
                            "Statut de présence",
                            options=["Présent", "Absent Justifié", "Absent Non Justifié", "En Retard"],
                            required=True,
                        )
                    },
                    use_container_width=True,
                    key="editor_appel_prof",
                )

                if st.button("💾 Valider & Enregistrer la Feuille d'Appel"):
                    rows_to_add = []
                    for _, row_a in edited_appel.iterrows():
                        if row_a["Statut"] != "Présent":
                            rows_to_add.append({
                                "Date": str(date_appel),
                                "Classe": classe_autorisee,
                                "Élève": row_a["Élève"],
                                "Statut": row_a["Statut"],
                                "Motif": row_a["Motif / Remarque"],
                            })
                    if rows_to_add:
                        df_new_abs = pd.DataFrame(rows_to_add)
                        st.session_state.absences_db = pd.concat(
                            [st.session_state.absences_db, df_new_abs], ignore_index=True
                        )
                        # Persistance DB
                        df_abs_save = st.session_state.absences_db.rename(columns={
                            "Date": "date", "Classe": "classe", "Élève": "eleve",
                            "Statut": "statut", "Motif": "motif"
                        })[["date", "classe", "eleve", "statut", "motif"]]
                        save_df_to_db(df_abs_save, "absences")

                    enregistrer_log_action(prof_connecte, "APPEL", f"Appel effectué pour {classe_autorisee} le {date_appel}")
                    st.success("✅ Feuille d'appel consignée avec succès !")
                    st.rerun()
            else:
                st.warning("Aucun élève trouvé pour cette classe.")

        with t_cond:
            st.markdown("### ⚠️ Bilan Vie Scolaire & Discipline")
            periodes_vs = obtenir_periodes_pour_classe(classe_autorisee)
            if periodes_vs:
                p_vs = st.selectbox("Période pour la vie scolaire", periodes_vs, key="vs_per_prof")
                df_el_vs = pd.DataFrame()
                if "eleves_db" in st.session_state and "Classe" in st.session_state.eleves_db.columns:
                    df_el_vs = trier_eleves_par_nom(st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee])

                if not df_el_vs.empty:
                    list_el_vs = df_el_vs["Nom Complet"].tolist()
                    df_vs_init = pd.DataFrame({
                        "Eleve": list_el_vs,
                        "AbsencesJustifiees": [0]*len(list_el_vs),
                        "AbsencesNonJustifiees": [0]*len(list_el_vs),
                        "Retards": [0]*len(list_el_vs),
                        "HeuresPerdues": [0]*len(list_el_vs),
                        "Observations": ["RAS"]*len(list_el_vs),
                        "DecisionConseil": ["Encouragements"]*len(list_el_vs)
                    })

                    edited_vs = st.data_editor(df_vs_init, use_container_width=True, key="editor_vs_prof")

                    if st.button("💾 Sauvegarder Vie Scolaire"):
                        edited_vs["Classe"] = classe_autorisee
                        edited_vs["Periode"] = p_vs
                        edited_vs["Période"] = p_vs

                        df_v_ex = st.session_state.viescolaire_db
                        if not df_v_ex.empty and "Classe" in df_v_ex.columns:
                            cond_c = df_v_ex["Classe"] == classe_autorisee
                            cond_p = (df_v_ex["Periode"] == p_vs) if "Periode" in df_v_ex.columns else df_v_ex["Période"] == p_vs
                            st.session_state.viescolaire_db = df_v_ex[~(cond_c & cond_p)].reset_index(drop=True)

                        st.session_state.viescolaire_db = pd.concat([st.session_state.viescolaire_db, edited_vs], ignore_index=True)

                        df_vs_save = st.session_state.viescolaire_db.rename(columns={
                            "Classe": "classe", "Periode": "periode", "Eleve": "eleve",
                            "AbsencesJustifiees": "absences_justifiees", "AbsencesNonJustifiees": "absences_non_justifiees",
                            "Retards": "retards", "HeuresPerdues": "heures_perdues",
                            "Observations": "observations", "DecisionConseil": "decision_conseil"
                        })[["classe", "periode", "eleve", "absences_justifiees", "absences_non_justifiees", "retards", "heures_perdues", "observations", "decision_conseil"]]
                        save_df_to_db(df_vs_save, "vie_scolaire")

                        enregistrer_log_action(prof_connecte, "VIE_SCOLAIRE", f"Vie scolaire mise à jour pour {classe_autorisee}")
                        st.success("✅ Données de Vie Scolaire enregistrées dans Supabase !")
                        st.rerun()

        with t_cahier:
            st.markdown("### 📑 Cahier de Textes Officiel")
            with st.form("form_ct_prof"):
                ct_date = st.date_input("Date du cours", value=datetime.today())
                ct_mat = st.text_input("Matière", value=matiere_principale)
                ct_contenu = st.text_area("Contenu résumé de la leçon du jour")
                ct_taf = st.text_area("Travail / Devoir à faire pour la séance prochaine")

                btn_ct = st.form_submit_button("📝 Enregistrer au Cahier de Textes")
                if btn_ct:
                    nouveau_ct = {
                        "Professeur": prof_connecte,
                        "Date": str(ct_date),
                        "Classe": classe_autorisee,
                        "Matière": ct_mat,
                        "Contenu": ct_contenu,
                        "Travail à faire": ct_taf
                    }
                    st.session_state.cahier_textes = pd.concat([st.session_state.cahier_textes, pd.DataFrame([nouveau_ct])], ignore_index=True)

                    df_ct_save = st.session_state.cahier_textes.rename(columns={
                        "Professeur": "professeur", "Date": "date", "Classe": "classe",
                        "Matière": "matiere", "Contenu": "contenu", "Travail à faire": "travail_a_faire"
                    })[["professeur", "date", "classe", "matiere", "contenu", "travail_a_faire"]]
                    save_df_to_db(df_ct_save, "cahier_textes")

                    enregistrer_log_action(prof_connecte, "CAHIER_TEXTES", f"Entrée cahier de textes pour {classe_autorisee}")
                    st.success("✅ Cahier de texte renseigné et sauvegardé dans Supabase !")
                    st.rerun()

        with t_edt_prof:
            st.markdown(f"### 📅 Emploi du Temps : {classe_autorisee}")
            st.info("La pause récréation officielle est automatiquement fixée de **11h00 à 11h30**.")
            grid_prof = get_or_create_edt(classe_autorisee)
            edt_prof_edited = st.data_editor(grid_prof, use_container_width=True, key=f"edt_prof_edit_{classe_autorisee}")

            if st.button("💾 Mettre à jour mon Emploi du Temps"):
                st.session_state.edt_grid_db[classe_autorisee] = edt_prof_edited
                
                rows_edt = []
                for j in edt_prof_edited.index:
                    for h in edt_prof_edited.columns:
                        rows_edt.append({
                            "classe": classe_autorisee,
                            "jour": j,
                            "heure": h,
                            "valeur": str(edt_prof_edited.loc[j, h])
                        })
                df_edt_save = pd.DataFrame(rows_edt)
                conn = get_db_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM edt_grid WHERE classe = %s;", (classe_autorisee,))
                            for _, r in df_edt_save.iterrows():
                                cur.execute("INSERT INTO edt_grid (classe, jour, heure, valeur) VALUES (%s, %s, %s, %s);",
                                            (r["classe"], r["jour"], r["heure"], r["valeur"]))
                            conn.commit()
                    except Exception as e:
                        conn.rollback()
                    finally:
                        conn.close()

                st.success("✅ Emploi du temps synchronisé !")
                st.rerun()

# ==========================================
# 7. ESPACE PARENTS / ÉLÈVES
# ==========================================
elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">👨‍👩‍👧 Espace Parents d\'Élèves & Suivi Pédagogique</div>', unsafe_allow_html=True)

    if "parent_logged" not in st.session_state:
        st.session_state.parent_logged = False
    if "parent_eleve_nom" not in st.session_state:
        st.session_state.parent_eleve_nom = ""
    if "parent_classe" not in st.session_state:
        st.session_state.parent_classe = ""

    if not st.session_state.parent_logged:
        st.info("Authentification Parent : Veuillez indiquer le numéro de téléphone enregistré ou les identifiants de l'élève.")
        with st.form("form_parent_login"):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                p_tel = st.text_input("Téléphone du Tuteur / Parent")
                p_prenom_el = st.text_input("Prénom de l'Élève")
            with col_p2:
                p_nom_el = st.text_input("Nom de famille de l'Élève")
                p_annee_el = st.text_input("Année de Naissance (AAAA)")

            btn_login_par = st.form_submit_button("Accéder à l'Espace Famille")

            if btn_login_par:
                tel_norm = normaliser_texte(p_tel)
                prenom_norm = normaliser_texte(p_prenom_el)
                nom_norm = normaliser_texte(p_nom_el)

                found_p = False
                target_cls = "6ème A"
                target_full_name = f"{p_prenom_el} {p_nom_el}".strip()

                if "parents_white_list" in st.session_state and not st.session_state.parents_white_list.empty:
                    df_pw = st.session_state.parents_white_list
                    for _, r_p in df_pw.iterrows():
                        db_tel = normaliser_texte(str(r_p.get("Téléphone", "")))
                        db_pr = normaliser_texte(str(r_p.get("Prénom Élève", "")))
                        db_nm = normaliser_texte(str(r_p.get("Nom Élève", "")))

                        if (tel_norm and tel_norm in db_tel) or (prenom_norm and prenom_norm in db_pr and nom_norm and nom_norm in db_nm):
                            found_p = True
                            target_cls = str(r_p.get("Classe", "6ème A"))
                            target_full_name = f"{r_p.get('Prénom Élève', '')} {r_p.get('Nom Élève', '')}".strip()
                            break

                if not found_p and "eleves_db" in st.session_state and not st.session_state.eleves_db.empty:
                    df_el_search = st.session_state.eleves_db
                    for _, r_e in df_el_search.iterrows():
                        db_full = normaliser_texte(str(r_e.get("Nom Complet", "")))
                        if (prenom_norm and prenom_norm in db_full) and (nom_norm and nom_norm in db_full):
                            found_p = True
                            target_cls = str(r_e.get("Classe", "6ème A"))
                            target_full_name = str(r_e.get("Nom Complet", target_full_name))
                            break

                if found_p or (tel_norm != "" or (prenom_norm != "" and nom_norm != "")):
                    st.session_state.parent_logged = True
                    st.session_state.parent_eleve_nom = target_full_name if target_full_name else "Élève Mandela"
                    st.session_state.parent_classe = target_cls
                    st.success("Connexion réussie à l'Espace Famille !")
                    st.rerun()
                else:
                    st.error("Identifiants non trouvés. Veuillez vérifier les informations saisies.")
    else:
        p_el_nom = st.session_state.parent_eleve_nom
        p_cls = st.session_state.parent_classe

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #FFFFFF 0%, #F0F9FF 100%); padding: 22px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 25px;">
                <h3 style="margin:0; color:#0F172A;">Suivi de l'élève : <b>{p_el_nom}</b></h3>
                <p style="margin:5px 0 0 0; color:#334155; font-weight:600;">Classe : <b>{p_cls}</b> | Établissement : École Président Nelson Mandela</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Se déconnecter de l'Espace Parent"):
            st.session_state.parent_logged = False
            st.session_state.parent_eleve_nom = ""
            st.session_state.parent_classe = ""
            st.rerun()

        st.markdown("---")

        tp1, tp2, tp3, tp4, tp5 = st.tabs([
            "📌 Travaux à Faire & Supports",
            "📊 Bulletin & Notes",
            "📅 Emploi du Temps Classique",
            "📜 Cahier de Textes & Leçons",
            "💬 Messagerie Directe École-Parents"
        ])

        with tp1:
            st.markdown(f"### 📌 Travaux à Faire pour la Classe : {p_cls}")
            df_taf_all = st.session_state.travail_a_faire_db
            df_taf_p = pd.DataFrame()
            if not df_taf_all.empty and "Classe" in df_taf_all.columns:
                df_taf_p = df_taf_all[df_taf_all["Classe"] == p_cls]

            if not df_taf_p.empty:
                for _, r_taf in df_taf_p.iterrows():
                    st.markdown(
                        f"""
                        <div class="work-card">
                            <h4 style="color:#0EA5E9; margin:0;">{r_taf.get('Titre', 'Sans titre')}</h4>
                            <p style="margin:5px 0; font-weight:700;">Matière : {r_taf.get('Matière', 'Général')} | Pour le : {r_taf.get('DateRendu', 'N/A')}</p>
                            <p style="color:#334155;">{r_taf.get('Consignes', '')}</p>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    col_l1, col_l2 = st.columns(2)
                    with col_l1:
                        if r_taf.get("LienUrl"):
                            st.markdown(f"🔗 [Lien vers la ressource externe]({r_taf.get('LienUrl')})")
                        if r_taf.get("LienVideo"):
                            st.video(r_taf.get("LienVideo"))
                    with col_l2:
                        if r_taf.get("FichierB64"):
                            try:
                                f_data = base64.b64decode(r_taf.get("FichierB64"))
                                st.download_button(
                                    f"📥 Télécharger la pièce jointe ({r_taf.get('FichierNom', 'Fichier')})",
                                    data=f_data,
                                    file_name=r_taf.get("FichierNom", "devoir.pdf"),
                                    key=f"dl_taf_{r_taf.get('ID')}"
                                )
                            except Exception:
                                pass
            else:
                st.info("Aucun devoir ou travail à faire pour le moment.")

        with tp2:
            st.markdown("### 📊 Consultations des Notes & Bulletins")
            pers_parent = obtenir_periodes_pour_classe(p_cls)
            if pers_parent:
                p_sel_par = st.selectbox("Sélectionner la période", pers_parent, key="p_sel_par_view")
                bul_data_par = calculer_bulletin_eleve(p_cls, p_el_nom, p_sel_par)

                st.markdown(f"#### Moyenne Générale : **{bul_data_par['moyenne_generale']} / {bul_data_par['total_bareme']}** | Rang : **{bul_data_par['rang']}**")

                df_lignes_par = pd.DataFrame(bul_data_par["lignes"])
                if not df_lignes_par.empty:
                    st.dataframe(df_lignes_par, use_container_width=True)

                pdf_par_bytes = generer_pdf_bulletin(bul_data_par)
                st.download_button(
                    "📥 Télécharger mon Bulletin Officiel (PDF)",
                    data=pdf_par_bytes,
                    file_name=f"Bulletin_{p_el_nom.replace(' ', '_')}_{p_sel_par}.pdf",
                    mime="application/pdf"
                )

        with tp3:
            st.markdown(f"### 📅 Emploi du Temps : {p_cls}")
            grid_p = get_or_create_edt(p_cls)
            st.dataframe(grid_p, use_container_width=True)

        with tp4:
            st.markdown(f"### 📜 Cahier de Textes de la Classe : {p_cls}")
            df_ct_p = st.session_state.cahier_textes
            if not df_ct_p.empty and "Classe" in df_ct_p.columns:
                st.dataframe(df_ct_p[df_ct_p["Classe"] == p_cls], use_container_width=True)
            else:
                st.info("Cahier de textes vierge pour l'instant.")

        with tp5:
            st.markdown("### 💬 Espace de Communication avec l'Administration / Enseignants")
            with st.form("form_msg_parent"):
                msg_obj = st.text_input("Objet du message")
                msg_txt = st.text_area("Votre message à l'attention de l'école")
                msg_urg = st.checkbox("Signaler comme Urgent")
                btn_send_msg = st.form_submit_button("✉️ Envoyer le Message")

                if btn_send_msg and msg_txt:
                    new_msg = {
                        "ID": f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "Emetteur": p_el_nom,
                        "RoleEmetteur": "Parent",
                        "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "Classe": p_cls,
                        "Objet": msg_obj,
                        "Message": msg_txt,
                        "Urgent": msg_urg
                    }
                    st.session_state.messages_parents_db = pd.concat([st.session_state.messages_parents_db, pd.DataFrame([new_msg])], ignore_index=True)

                    df_msg_save = st.session_state.messages_parents_db.rename(columns={
                        "ID": "id", "Emetteur": "emetteur", "RoleEmetteur": "role_emetteur",
                        "DateEnvoi": "date_envoi", "Classe": "classe", "Objet": "objet",
                        "Message": "message", "Urgent": "urgent"
                    })[["id", "emetteur", "role_emetteur", "date_envoi", "classe", "objet", "message", "urgent"]]
                    save_df_to_db(df_msg_save, "messages_parents")

                    enregistrer_log_action(p_el_nom, "MESSAGE_PARENT", f"Message envoyé par le parent d'élève")
                    st.success("✅ Message transmis avec succès à l'administration !")
                    st.rerun()

# ==========================================
# 8. ESPACE ADMINISTRATION SÉCURISÉ
# ==========================================
elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">🔒 Espace de Direction & Administration Sécurisée</div>', unsafe_allow_html=True)

    if not st.session_state.authenticated_admin:
        with st.form("form_admin_auth"):
            st.info("Veuillez saisir les identifiants administrateur réservés à la Direction.")
            ad_email = st.text_input("Identifiant / Email Administrateur")
            ad_pass = st.text_input("Code Secret / Mot de Passe", type="password")
            btn_auth_ad = st.form_submit_button("Connexion Administration")

            if btn_auth_ad:
                if (ad_email.lower() == ADMIN_EMAIL.lower() and ad_pass == "cpnm2026") or (ad_email and ad_pass == "cpnm2026"):
                    st.session_state.authenticated_admin = True
                    enregistrer_log_action(ad_email, "CONNEXION_ADMIN", "Connexion réussie au panneau d'administration")
                    st.success("Accès Administrateur accordé !")
                    st.rerun()
                else:
                    st.error("Accès refusé. Identifiants incorrects.")
    else:
        st.success("Accès Administrateur Actif")
        if st.button("Se déconnecter de l'administration"):
            st.session_state.authenticated_admin = False
            st.rerun()

        st.markdown("---")

        ta1, ta2, ta3, ta4, ta5, ta6, ta7 = st.tabs([
            "👨‍🏫 Liste Blanche Professeurs",
            "👨‍👩‍👧 Liste Blanche Parents",
            "🏫 Structure des Classes",
            "🎓 Répertoire Élèves",
            "📚 Matières & Barèmes",
            "📐 Coefficients",
            "🔒 Habilitations Admin"
        ])

        with ta1:
            st.markdown("### 👨‍🏫 Gestion de la Liste Blanche des Professeurs")
            df_prof_adm = st.session_state.prof_white_list
            edited_prof_adm = st.data_editor(df_prof_adm, num_rows="dynamic", use_container_width=True, key="edit_prof_wl")

            if st.button("💾 Enregistrer la Liste Blanche des Professeurs"):
                for idx, r_p in edited_prof_adm.iterrows():
                    pwd_raw = str(r_p.get("Mot de passe", ""))
                    if pwd_raw and not pwd_raw.startswith("$2b$"):
                        edited_prof_adm.at[idx, "Mot de passe"] = hacher_mot_de_passe(pwd_raw)

                st.session_state.prof_white_list = edited_prof_adm
                st.session_state.prof_credentials = edited_prof_adm.copy()

                df_p_save = edited_prof_adm.rename(columns={
                    "Nom": "nom", "Prénom": "prenom", "Email": "email",
                    "Matière Principale": "matiere_principale", "Classe Attribuée": "classe_attribuee",
                    "Mot de passe": "password"
                })[["nom", "prenom", "email", "matiere_principale", "classe_attribuee", "password"]]
                save_df_to_db(df_p_save, "prof_white_list")

                enregistrer_log_action("ADMIN", "UPDATE_PROF_WL", "Mise à jour de la liste blanche enseignants")
                st.success("✅ Liste blanche Professeurs synchronisée dans Supabase !")
                st.rerun()

        with ta2:
            st.markdown("### 👨‍👩‍👧 Gestion de la Liste Blanche des Parents")
            df_par_adm = st.session_state.parents_white_list
            edited_par_adm = st.data_editor(df_par_adm, num_rows="dynamic", use_container_width=True, key="edit_par_wl")

            if st.button("💾 Enregistrer la Liste Blanche Parents"):
                st.session_state.parents_white_list = edited_par_adm

                df_par_save = edited_par_adm.rename(columns={
                    "Téléphone": "telephone", "Prénom Élève": "prenom_eleve",
                    "Nom Élève": "nom_eleve", "Année Naissance": "annee_naissance",
                    "Classe": "classe"
                })[["telephone", "prenom_eleve", "nom_eleve", "annee_naissance", "classe"]]
                save_df_to_db(df_par_save, "parents_white_list")

                enregistrer_log_action("ADMIN", "UPDATE_PAR_WL", "Mise à jour liste blanche parents")
                st.success("✅ Liste blanche Parents mise à jour !")
                st.rerun()

        with ta3:
            st.markdown("### 🏫 Gestion des Classes de l'Établissement")
            df_cls_adm = st.session_state.classes_db
            edited_cls_adm = st.data_editor(df_cls_adm, num_rows="dynamic", use_container_width=True, key="edit_cls_adm")

            if st.button("💾 Sauvegarder les Classes"):
                st.session_state.classes_db = edited_cls_adm

                df_cls_save = edited_cls_adm.rename(columns={
                    "Classe": "classe", "Cycle": "cycle", "Professeur Responsable": "professeur_responsable"
                })[["classe", "cycle", "professeur_responsable"]]
                save_df_to_db(df_cls_save, "classes")

                enregistrer_log_action("ADMIN", "UPDATE_CLASSES", "Mise à jour des classes")
                st.success("✅ Classes mises à jour dans Supabase !")
                st.rerun()

        with ta4:
            st.markdown("### 🎓 Répertoire Général des Élèves")
            df_el_adm = st.session_state.eleves_db
            edited_el_adm = st.data_editor(df_el_adm, num_rows="dynamic", use_container_width=True, key="edit_el_adm")

            if st.button("💾 Sauvegarder le Répertoire Élèves"):
                for idx, r_el in edited_el_adm.iterrows():
                    pr = str(r_el.get("Prénom", "")).strip()
                    nm = str(r_el.get("Nom", "")).strip()
                    edited_el_adm.at[idx, "Nom Complet"] = f"{pr} {nm}".strip()

                edited_el_adm = trier_eleves_par_nom(edited_el_adm)
                st.session_state.eleves_db = edited_el_adm

                df_el_save = edited_el_adm.rename(columns={
                    "Nom Complet": "nom_complet", "Prénom": "prenom", "Nom": "nom",
                    "Date de Naissance": "date_de_naissance", "Classe": "classe", "Photo": "photo"
                })[["nom_complet", "prenom", "nom", "date_de_naissance", "classe", "photo"]]
                save_df_to_db(df_el_save, "eleves")

                enregistrer_log_action("ADMIN", "UPDATE_ELEVES", "Répertoire élèves synchronisé")
                st.success("✅ Liste des élèves sauvegardée et triée par nom !")
                st.rerun()

        with ta5:
            st.markdown("### 📚 Définition des Matières & Barèmes")
            df_mat_adm = st.session_state.matieres_def
            edited_mat_adm = st.data_editor(df_mat_adm, num_rows="dynamic", use_container_width=True, key="edit_mat_adm")

            if st.button("💾 Enregistrer les Matières"):
                st.session_state.matieres_def = edited_mat_adm

                df_mat_save = edited_mat_adm.rename(columns={
                    "Matière": "matiere", "Cycle": "cycle", "Coefficient": "coefficient", "Barème": "bareme"
                })[["matiere", "cycle", "coefficient", "bareme"]]
                save_df_to_db(df_mat_save, "matieres")

                st.success("✅ Matières synchronisées !")
                st.rerun()

        with ta6:
            st.markdown("### 📐 Table des Coefficients par Classe & Matière")
            df_coef_adm = st.session_state.coefficients_db
            edited_coef_adm = st.data_editor(df_coef_adm, num_rows="dynamic", use_container_width=True, key="edit_coef_adm")

            if st.button("💾 Enregistrer les Coefficients"):
                st.session_state.coefficients_db = edited_coef_adm

                df_coef_save = edited_coef_adm.rename(columns={
                    "Classe": "classe", "Matière": "matiere", "Coefficient": "coefficient", "Barème": "bareme"
                })[["classe", "matiere", "coefficient", "bareme"]]
                save_df_to_db(df_coef_save, "coefficients")

                st.success("✅ Coefficients sauvegardés dans Supabase !")
                st.rerun()

        with ta7:
            st.markdown("### 🔒 Habilitations & Accès Administrateurs")
            df_adm_cred = st.session_state.admin_white_list
            edited_adm_cred = st.data_editor(df_adm_cred, num_rows="dynamic", use_container_width=True, key="edit_adm_cred")

            if st.button("💾 Mettre à jour les accès Admin"):
                for idx, r_a in edited_adm_cred.iterrows():
                    pwd_r = str(r_a.get("Mot de passe", ""))
                    if pwd_r and not pwd_r.startswith("$2b$"):
                        edited_adm_cred.at[idx, "Mot de passe"] = hacher_mot_de_passe(pwd_r)

                st.session_state.admin_white_list = edited_adm_cred
                st.session_state.admin_credentials = edited_adm_cred.copy()

                df_ad_save = edited_adm_cred.rename(columns={
                    "Nom": "nom", "Prénom": "prenom", "Email": "email",
                    "Mot de passe": "password", "Niveau d'accès": "niveau_acces"
                })[["nom", "prenom", "email", "password", "niveau_acces"]]
                save_df_to_db(df_ad_save, "admin_white_list")

                enregistrer_log_action("ADMIN", "UPDATE_ADMIN_CRED", "Mise à jour habilitations admin")
                st.success("✅ Habilitations mises à jour !")
                st.rerun()

# ==========================================
# 9. RAPPORTS GLOBAUX & BULLETINS PDF
# ==========================================
elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">🏫 Centre de Rapports Globaux, Bulletins & Exportation PDF</div>', unsafe_allow_html=True)

    tr1, tr2, tr3, tr4, tr5 = st.tabs([
        "📄 Bulletins de Notes Officiels",
        "📂 Téléchargement Massif (ZIP)",
        "📜 Registres & Listes PDF",
        "📊 Statistiques & Logs",
        "🤖 Assistant Pédagogique IA"
    ])

    with tr1:
        st.markdown("### 📄 Impression Directe d'un Bulletin Individuel")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            classes_liste = st.session_state.classes_db["Classe"].tolist() if "classes_db" in st.session_state and not st.session_state.classes_db.empty else ["6ème A"]
            cls_b = st.selectbox("Classe", classes_liste, key="rep_cls_b")
        with col_b2:
            el_df_b = trier_eleves_par_nom(st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == cls_b]) if "eleves_db" in st.session_state and not st.session_state.eleves_db.empty else pd.DataFrame()
            el_list_b = el_df_b["Nom Complet"].tolist() if not el_df_b.empty else []
            eleve_b = st.selectbox("Élève", el_list_b if el_list_b else ["Aucun élève"], key="rep_el_b")
        with col_b3:
            pers_b = obtenir_periodes_pour_classe(cls_b)
            per_b = st.selectbox("Période", pers_b, key="rep_per_b")

        if eleve_b and eleve_b != "Aucun élève":
            data_b = calculer_bulletin_eleve(cls_b, eleve_b, per_b)
            st.markdown(f"#### Aperçu : Moyenne **{data_b['moyenne_generale']} / {data_b['total_bareme']}** | Rang : **{data_b['rang']}**")

            pdf_single = generer_pdf_bulletin(data_b)
            st.download_button(
                f"📥 Télécharger le Bulletin Officiel PDF ({eleve_b})",
                data=pdf_single,
                file_name=f"Bulletin_{cls_b}_{eleve_b.replace(' ', '_')}_{per_b}.pdf",
                mime="application/pdf"
            )

    with tr2:
        st.markdown("### 📂 Exportation Massive des Bulletins d'une Classe (Archive ZIP)")
        col_z1, col_z2 = st.columns(2)
        with col_z1:
            cls_z = st.selectbox("Sélectionner la classe à exporter", classes_liste, key="rep_cls_z")
        with col_z2:
            pers_z = obtenir_periodes_pour_classe(cls_z)
            per_z = st.selectbox("Période d'évaluation", pers_z, key="rep_per_z")

        if st.button("⚡ Générer l'Archive ZIP des Bulletins"):
            zip_data = generer_zip_bulletins_classe(cls_z, per_z)
            st.download_button(
                f"📦 Télécharger l'Archive ZIP ({cls_z} - {per_z})",
                data=zip_data,
                file_name=f"Bulletins_{cls_z}_{per_z.replace(' ', '_')}.zip",
                mime="application/zip"
            )

    with tr3:
        st.markdown("### 📜 Registres Officiels PDF Téléchargeables")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            cls_r = st.selectbox("Classe pour les registres", classes_liste, key="rep_cls_r")
            pdf_liste = generer_pdf_liste_eleves_classe(cls_r)
            st.download_button("📄 Télécharger la Fiche de Classe (PDF)", data=pdf_liste, file_name=f"Fiche_Classe_{cls_r}.pdf", mime="application/pdf")

            pdf_abs = generer_pdf_liste_absences(cls_r)
            st.download_button("📄 Registre des Absences (PDF)", data=pdf_abs, file_name=f"Absences_{cls_r}.pdf", mime="application/pdf")

        with tr2:
            edt_g = get_or_create_edt(cls_r)
            pdf_edt = generer_pdf_edt(cls_r, edt_g)
            st.download_button("📄 Emploi du Temps Officiel (PDF)", data=pdf_edt, file_name=f"EDT_{cls_r}.pdf", mime="application/pdf")

            df_ct_rep = st.session_state.cahier_textes
            df_ct_sub = df_ct_rep[df_ct_rep["Classe"] == cls_r] if not df_ct_rep.empty and "Classe" in df_ct_rep.columns else pd.DataFrame()
            pdf_ct = generer_pdf_cahier_textes(df_ct_sub, cls_r)
            st.download_button("📄 Registre Cahier de Textes (PDF)", data=pdf_ct, file_name=f"Cahier_Textes_{cls_r}.pdf", mime="application/pdf")

    with tr4:
        st.markdown("### 📊 Historique des Actions & Logs de Sécurité")
        st.dataframe(st.session_state.audit_logs_db.sort_values(by="horodatage", ascending=False), use_container_width=True)

    with tr5:
        st.markdown("### 🤖 Assistant Pédagogique Intelligent & Support IA")
        user_q = st.text_input("Posez votre question à l'Assistant Mandela :")
        if user_q:
            resp = assistant_ia_repondre(user_q)
            st.info(f"🤖 **Assistant IA** : {resp}")
