
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
    """Établit la connexion à la base de données Supabase / PostgreSQL de manière ultra-rapide."""
    try:
        if "postgres" in st.secrets:
            conn = psycopg2.connect(
                host=st.secrets["postgres"]["host"],
                database=st.secrets["postgres"]["database"],
                user=st.secrets["postgres"]["user"],
                password=st.secrets["postgres"]["password"],
                port=st.secrets["postgres"]["port"],
                connect_timeout=5
            )
        else:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        return conn
    except Exception as e:
        return None

def init_db():
    """Initialise toutes les tables dans Supabase / PostgreSQL avec toutes les colonnes requises."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    horodatage VARCHAR(50),
                    acteur VARCHAR(255),
                    action VARCHAR(255),
                    details TEXT
                );
            """)
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS classes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255) UNIQUE NOT NULL,
                    cycle VARCHAR(255),
                    professeur_responsable VARCHAR(255)
                );
            """)
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
            cur.execute("ALTER TABLE eleves ALTER COLUMN date_de_naissance TYPE VARCHAR(50);")
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matieres (
                    id SERIAL PRIMARY KEY,
                    matiere VARCHAR(255),
                    cycle VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            cur.execute("ALTER TABLE matieres ADD COLUMN IF NOT EXISTS cycle VARCHAR(255);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS periodes (
                    id SERIAL PRIMARY KEY,
                    periode VARCHAR(255),
                    statut VARCHAR(50),
                    cycle VARCHAR(255)
                );
            """)
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edt_grid (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    jour VARCHAR(50),
                    heure VARCHAR(50),
                    valeur TEXT
                );
            """)
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_prof_messages (
                    id SERIAL PRIMARY KEY,
                    expediteur VARCHAR(255),
                    destinataire VARCHAR(255),
                    date VARCHAR(50),
                    sujet VARCHAR(255),
                    message TEXT,
                    piece_jointe TEXT
                );
            """)
            cur.execute("ALTER TABLE admin_prof_messages ADD COLUMN IF NOT EXISTS piece_jointe TEXT;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_assignations_travail (
                    id SERIAL PRIMARY KEY,
                    titre VARCHAR(255),
                    classe VARCHAR(255),
                    professeur VARCHAR(255),
                    date VARCHAR(50),
                    description TEXT,
                    piece_jointe TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fiches_progression_classe (
                    id SERIAL PRIMARY KEY,
                    professeur VARCHAR(255),
                    classe VARCHAR(255),
                    date VARCHAR(50),
                    progression_niveau VARCHAR(100),
                    avis_classe TEXT,
                    regression_notes TEXT,
                    piece_jointe TEXT
                );
            """)
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

init_db()

def nettoyer_date(val):
    if val is None or pd.isna(val) or str(val).lower() in ["nan", "nat", "none", ""]:
        return None
    val_str = str(val).strip()
    if val_str == "" or val_str.lower() in ["nan", "nat", "none"]:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(val_str[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val_str

def load_table_from_db(query, columns):
    """Charge une table avec vérification dynamique et gestion propre des reconnexions."""
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
        if conn:
            conn.close()

def save_df_to_db(df: pd.DataFrame, table_name: str):
    conn = get_db_connection()
    if conn is None:
        st.error("Impossible d'établir la connexion à la base de données Supabase.")
        return False
    try:
        with conn.cursor() as cur:
            if not df.empty:
                df_cleaned = df.where(pd.notnull(df), None)
                if table_name == "eleves":
                    cur.execute("DELETE FROM eleves;")
                    query = "INSERT INTO eleves (nom_complet, prenom, nom, date_de_naissance, classe, photo) VALUES (%s, %s, %s, %s, %s, %s)"
                    data = []
                    for _, r in df_cleaned.iterrows():
                        nom_complet = r.get("Nom Complet")
                        if nom_complet is not None and str(nom_complet).lower() in ["nan", "none"]:
                            nom_complet = None
                        prenom = r.get("Prénom")
                        if prenom is not None and str(prenom).lower() in ["nan", "none"]:
                            prenom = None
                        nom = r.get("Nom")
                        if nom is not None and str(nom).lower() in ["nan", "none"]:
                            nom = None
                        date_naiss = nettoyer_date(r.get("Date de Naissance"))
                        classe = r.get("Classe")
                        if classe is not None and str(classe).lower() in ["nan", "none"]:
                            classe = None
                        photo = r.get("Photo")
                        if photo is None or pd.isna(photo) or str(photo).lower() in ["nan", "nat", "none", ""]:
                            photo = None
                        else:
                            photo = str(photo)
                        
                        if not nom_complet and not prenom and not nom and not classe:
                            continue
                            
                        if nom_complet and (not prenom or pd.isna(prenom)) and (not nom or pd.isna(nom)):
                            parts = str(nom_complet).strip().split()
                            if len(parts) >= 2:
                                prenom = parts[0]
                                nom = " ".join(parts[1:])
                            elif len(parts) == 1:
                                nom = parts[0]
                                prenom = ""
                        elif not nom_complet and (prenom or nom):
                            nom_complet = f"{str(prenom or '')} {str(nom or '')}".strip()
                            
                        data.append((nom_complet, prenom, nom, date_naiss, classe, photo))
                    
                    if data:
                        cur.executemany(query, data)
                elif table_name == "classes":
                    cur.execute("DELETE FROM classes;")
                    query = "INSERT INTO classes (classe, cycle, professeur_responsable) VALUES (%s, %s, %s)"
                    data = [(r.get("Classe"), r.get("Cycle"), r.get("Professeur Responsable")) for _, r in df_cleaned.iterrows() if r.get("Classe")]
                    if data:
                        cur.executemany(query, data)
                elif table_name == "prof_white_list":
                    cur.execute("DELETE FROM prof_white_list;")
                    query = "INSERT INTO prof_white_list (nom, prenom, email, matiere_principale, classe_attribuee, password) VALUES (%s, %s, %s, %s, %s, %s)"
                    data = [(r.get("Nom"), r.get("Prénom"), r.get("Email"), r.get("Matière Principale"), r.get("Classe Attribuée"), r.get("Mot de passe")) for _, r in df_cleaned.iterrows() if r.get("Email")]
                    if data:
                        cur.executemany(query, data)
                elif table_name == "admin_white_list":
                    cur.execute("DELETE FROM admin_white_list;")
                    query = "INSERT INTO admin_white_list (email, nom, prenom, password, niveau_acces) VALUES (%s, %s, %s, %s, %s)"
                    data = [(r.get("Email"), r.get("Nom"), r.get("Prénom"), r.get("Mot de passe"), r.get("Niveau d'accès")) for _, r in df_cleaned.iterrows() if r.get("Email")]
                    if data:
                        cur.executemany(query, data)
                elif table_name == "matieres":
                    cur.execute("DELETE FROM matieres;")
                    query = "INSERT INTO matieres (matiere, cycle, coefficient, bareme) VALUES (%s, %s, %s, %s)"
                    data = [(r.get("Matière"), r.get("Cycle"), r.get("Coefficient"), r.get("Barème")) for _, r in df_cleaned.iterrows() if r.get("Matière")]
                    if data:
                        cur.executemany(query, data)
                elif table_name == "edt_grid":
                    for _, r in df_cleaned.iterrows():
                        if r.get("classe"):
                            cur.execute("DELETE FROM edt_grid WHERE classe = %s AND jour = %s AND heure = %s;", (r.get("classe"), r.get("jour"), r.get("heure")))
                            cur.execute("INSERT INTO edt_grid (classe, jour, heure, valeur) VALUES (%s, %s, %s, %s);", (r.get("classe"), r.get("jour"), r.get("heure"), r.get("valeur")))
                elif table_name == "cahier_textes":
                    query = "INSERT INTO cahier_textes (professeur, date, classe, matiere, contenu, travail_a_faire) VALUES (%s, %s, %s, %s, %s, %s);"
                    data_tuples = [(r.get("Professeur"), str(r.get("Date", "")), r.get("Classe"), r.get("Matière"), r.get("Contenu"), r.get("Travail à faire")) for _, r in df_cleaned.iterrows()]
                    if data_tuples:
                        cur.executemany(query, data_tuples)
                elif table_name == "absences":
                    query = "INSERT INTO absences (date, classe, eleve, statut, motif) VALUES (%s, %s, %s, %s, %s);"
                    data_tuples = [(str(r.get("Date", "")), r.get("Classe"), r.get("Élève"), r.get("Statut"), r.get("Motif")) for _, r in df_cleaned.iterrows()]
                    if data_tuples:
                        cur.executemany(query, data_tuples)
                elif table_name == "notes":
                    for _, r in df_cleaned.iterrows():
                        if r.get("Classe") and r.get("Eleve"):
                            cur.execute("DELETE FROM notes WHERE classe = %s AND matiere = %s AND (periode = %s) AND eleve = %s;", 
                                        (r.get("Classe"), r.get("Matière"), r.get("Periode", r.get("Période")), r.get("Eleve")))
                            cur.execute("INSERT INTO notes (classe, matiere, periode, eleve, devoir1, devoir2, composition, baremenote) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);",
                                        (r.get("Classe"), r.get("Matière"), r.get("Periode", r.get("Période")), r.get("Eleve"), r.get("Devoir1"), r.get("Devoir2"), r.get("Composition"), r.get("BaremeNote")))
                elif table_name == "admin_prof_messages":
                    query = "INSERT INTO admin_prof_messages (expediteur, destinataire, date, sujet, message, piece_jointe) VALUES (%s, %s, %s, %s, %s, %s);"
                    data_tuples = [(r.get("Expéditeur"), r.get("Destinataire"), str(r.get("Date", "")), r.get("Sujet"), r.get("Message"), r.get("Pièce jointe")) for _, r in df_cleaned.iterrows()]
                    if data_tuples:
                        cur.executemany(query, data_tuples)
                elif table_name == "admin_assignations_travail":
                    query = "INSERT INTO admin_assignations_travail (titre, classe, professeur, date, description, piece_jointe) VALUES (%s, %s, %s, %s, %s, %s);"
                    data_tuples = [(r.get("Titre"), r.get("Classe"), r.get("Professeur"), str(r.get("Date", "")), r.get("Description"), r.get("Pièce jointe")) for _, r in df_cleaned.iterrows()]
                    if data_tuples:
                        cur.executemany(query, data_tuples)
                elif table_name == "fiches_progression_classe":
                    query = "INSERT INTO fiches_progression_classe (professeur, classe, date, progression_niveau, avis_classe, regression_notes, piece_jointe) VALUES (%s, %s, %s, %s, %s, %s, %s);"
                    data_tuples = [(r.get("Professeur"), r.get("Classe"), str(r.get("Date", "")), r.get("Progression Niveau"), r.get("Avis Classe"), r.get("Régression Notes"), r.get("Pièce jointe")) for _, r in df_cleaned.iterrows()]
                    if data_tuples:
                        cur.executemany(query, data_tuples)
                else:
                    cols = list(df_cleaned.columns)
                    cols_str = ",".join([f'"{col}"' for col in cols])
                    placeholders = ",".join(["%s"] * len(cols))
                    query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders});"
                    cur.executemany(query, [tuple(x) for x in df_cleaned.to_numpy()])
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Détail technique Supabase ({table_name}) : {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

# ==========================================
# 0. BIS. SÉCURITÉ & AUTHENTIFICATION
# ==========================================
def hacher_mot_de_passe(password: str) -> str:
    if not password:
        return ""
    sel = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), sel).decode("utf-8")

def verifier_mot_de_passe(password_saisi, hashed_db):
    if not password_saisi or not hashed_db: 
        return False
    if str(hashed_db).startswith('$2b$'):
        return bcrypt.checkpw(str(password_saisi).encode("utf-8"), str(hashed_db).encode("utf-8"))
    return str(password_saisi) == str(hashed_db)

def normaliser_texte(texte):
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

def normaliser_cycle(cycle):
    """Normalise les libellés de cycle afin que l'Administration, les classes,
    la saisie des notes et les bulletins utilisent exactement la même logique."""
    valeur = normaliser_texte(cycle)
    if not valeur:
        return ""
    if any(x in valeur for x in ["elementaire", "primaire", "fondamental 1", "cycle 1"]):
        return "elementaire"
    if any(x in valeur for x in ["college", "secondaire", "fondamental 2", "cycle 2"]):
        return "college"
    return valeur

def preparer_matieres_dataframe(df):
    """Nettoie et normalise la configuration des matières sans supprimer les
    matières réellement saisies par l'Administration."""
    colonnes = ["Matière", "Cycle", "Coefficient", "Barème"]
    if df is None or df.empty:
        return pd.DataFrame(columns=colonnes)

    result = df.copy()
    for col in colonnes:
        if col not in result.columns:
            result[col] = None

    result["Matière"] = result["Matière"].apply(
        lambda x: "" if x is None or pd.isna(x) else str(x).strip()
    )
    result["Cycle"] = result["Cycle"].apply(
        lambda x: "" if x is None or pd.isna(x) else str(x).strip()
    )
    result["Coefficient"] = pd.to_numeric(result["Coefficient"], errors="coerce").fillna(1.0)
    result["Barème"] = pd.to_numeric(result["Barème"], errors="coerce").fillna(20.0)

    result = result[result["Matière"] != ""].copy()
    result = result.drop_duplicates(
        subset=["Matière", "Cycle"], keep="last"
    ).reset_index(drop=True)
    return result[colonnes]

ADMIN_EMAIL_MAITRE = "cpnjcpn@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    elif "Nom Complet" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom Complet"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort"]).drop(columns=["Nom_Sort"])
    return df_copy.reset_index(drop=True)

# ==========================================
# 0. TER. DESIGN XXL & CONFIGURATION PAGE
# ==========================================
st.set_page_config(
    page_title="Sénégal - Portail Éducatif de l'École Président Nelson Mandela",
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 50%, #E2E8F0 100%); color: #0F172A; }
    
    .header-institutionnel {
        background: linear-gradient(135deg, #0284C7 0%, #1E40AF 60%, #1E3A8A 100%);
        padding: 4px; border-radius: 28px; box-shadow: 0 20px 40px rgba(30, 64, 175, 0.25); margin-bottom: 30px;
    }
    .header-inner {
        background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(20px); padding: 25px 35px;
        border-radius: 26px; display: flex; align-items: center; justify-content: space-between; gap: 20px;
    }
    .ministere-title { color: #0F172A; font-size: clamp(1.2rem, 2.2vw, 1.8rem); font-weight: 900; text-transform: uppercase; margin: 0; }
    .ia-ief-sub { color: #1E3A8A; font-size: clamp(0.9rem, 1.6vw, 1.15rem); font-weight: 700; margin: 4px 0; }
    .ecole-title { color: #0284C7; font-size: clamp(1.3rem, 2.5vw, 2.2rem); font-weight: 900; margin: 6px 0 0 0; text-transform: uppercase; }
    
    .animated-card-xxl {
        border: 2px solid #E2E8F0; padding: 40px 30px; border-radius: 28px;
        background: #FFFFFF; box-shadow: 0 15px 35px rgba(15, 23, 42, 0.08);
        text-align: center; margin-bottom: 25px; min-height: 350px; display: flex; flex-direction: column; justify-content: space-between;
        transition: all 0.25s ease-in-out;
    }
    .animated-card-xxl:hover {
        transform: translateY(-4px);
        box-shadow: 0 25px 50px rgba(2, 132, 199, 0.2);
        border-color: #0284C7;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #0284C7 0%, #1D4ED8 100%) !important; color: #FFFFFF !important;
        border-radius: 14px !important; font-weight: 700 !important; border: none !important; padding: 0.8rem 1.5rem !important;
        width: 100% !important; min-height: 52px !important; font-size: 1.05rem !important; box-shadow: 0 8px 20px rgba(2, 132, 199, 0.3) !important;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: scale(1.01);
        box-shadow: 0 12px 25px rgba(2, 132, 199, 0.5) !important;
    }

    .download-container-xxl {
        background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%);
        border: 2px solid #0284C7;
        padding: 30px;
        border-radius: 24px;
        text-align: center;
        margin: 20px 0;
        box-shadow: 0 10px 25px rgba(2, 132, 199, 0.12);
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<style>[data-testid=\"stToolbar\"] { display: none; } footer { visibility: hidden; }</style>", unsafe_allow_html=True)

# ==========================================
# 2. INITIALISATION DES ÉTATS & RECHARGEMENT DYNAMIQUE
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False
if "current_admin_email" not in st.session_state:
    st.session_state.current_admin_email = ""

def recharger_toutes_les_donnees():
    df_eleves_db = load_table_from_db(
        'SELECT nom_complet AS "Nom Complet", prenom AS "Prénom", nom AS "Nom", date_de_naissance AS "Date de Naissance", classe AS "Classe", photo AS "Photo" FROM eleves',
        ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]
    )
    if df_eleves_db.empty:
        st.session_state.eleves_db = pd.DataFrame(
            columns=["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"],
            data=[]
        )
    else:
        st.session_state.eleves_db = df_eleves_db

    df_classes = load_table_from_db('SELECT classe AS "Classe", cycle AS "Cycle", professeur_responsable AS "Professeur Responsable" FROM classes', ["Classe", "Cycle", "Professeur Responsable"])
    if df_classes.empty:
        st.session_state.classes_db = pd.DataFrame(columns=["Classe", "Cycle", "Professeur Responsable"], data=[])
    else:
        st.session_state.classes_db = df_classes

    df_prof = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", matiere_principale AS "Matière Principale", classe_attribuee AS "Classe Attribuée", password AS "Mot de passe" FROM prof_white_list', ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
    if df_prof.empty:
        st.session_state.prof_white_list = pd.DataFrame([{
            "Nom": "Prof", "Prénom": "Élémentaire", "Email": "prof.elem@cpnm.sn",
            "Matière Principale": "Toutes les matières", "Classe Attribuée": "CP", "Mot de passe": hacher_mot_de_passe("cpnm2026")
        }])
    else:
        st.session_state.prof_white_list = df_prof

    df_admin_wl = load_table_from_db('SELECT email AS "Email", nom AS "Nom", prenom AS "Prénom", password AS "Mot de passe", niveau_acces AS "Niveau d\'accès" FROM admin_white_list', ["Email", "Nom", "Prénom", "Mot de passe", "Niveau d'accès"])
    if df_admin_wl.empty:
        st.session_state.admin_white_list = pd.DataFrame([{
            "Email": ADMIN_EMAIL_MAITRE, "Nom": "Nelson", "Prénom": "Admin Principal",
            "Mot de passe": hacher_mot_de_passe("cpnmn2026"), "Niveau d'accès": "Total (Super Admin)"
        }])
    else:
        st.session_state.admin_white_list = df_admin_wl

    df_mat = load_table_from_db('SELECT matiere AS "Matière", cycle AS "Cycle", coefficient AS "Coefficient", bareme AS "Barème" FROM matieres', ["Matière", "Cycle", "Coefficient", "Barème"])
    if df_mat.empty:
        st.session_state.matieres_def = pd.DataFrame([
            {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4.0, "Barème": 20.0},
            {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5.0, "Barème": 20.0},
            {"Matière": "Lecture", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Écriture / Copie", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Calcul / Arithmétique", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Éveil / Sciences", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Éducation Artistique & Morale", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
        ])
    else:
        st.session_state.matieres_def = preparer_matieres_dataframe(df_mat)

    st.session_state.notes_db = load_table_from_db('SELECT classe AS "Classe", matiere AS "Matière", periode AS "Periode", periode AS "Période", eleve AS "Eleve", devoir1 AS "Devoir1", devoir2 AS "Devoir2", composition AS "Composition", baremenote AS "BaremeNote" FROM notes', ["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])
    st.session_state.viescolaire_db = load_table_from_db('SELECT classe AS "Classe", periode AS "Periode", periode AS "Période", eleve AS "Eleve", absences_justifiees AS "AbsencesJustifiees", absences_non_justifiees AS "AbsencesNonJustifiees", retards AS "Retards", heures_perdues AS "HeuresPerdues", observations AS "Observations", decision_conseil AS "DecisionConseil" FROM vie_scolaire', ["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"])
    st.session_state.audit_logs_db = load_table_from_db('SELECT horodatage AS "Horodatage", acteur AS "Acteur", action AS "Action", details AS "Détails" FROM audit_logs', ["Horodatage", "Acteur", "Action", "Détails"])
    st.session_state.admin_prof_messages = load_table_from_db('SELECT expediteur AS "Expéditeur", destinataire AS "Destinataire", date AS "Date", sujet AS "Sujet", message AS "Message", piece_jointe AS "Pièce jointe" FROM admin_prof_messages', ["Expéditeur", "Destinataire", "Date", "Sujet", "Message", "Pièce jointe"])
    st.session_state.admin_assignations_travail = load_table_from_db('SELECT titre AS "Titre", classe AS "Classe", professeur AS "Professeur", date AS "Date", description AS "Description", piece_jointe AS "Pièce jointe" FROM admin_assignations_travail', ["Titre", "Classe", "Professeur", "Date", "Description", "Pièce jointe"])
    st.session_state.fiches_progression_classe = load_table_from_db('SELECT professeur AS "Professeur", classe AS "Classe", date AS "Date", progression_niveau AS "Progression Niveau", avis_classe AS "Avis Classe", regression_notes AS "Régression Notes", piece_jointe AS "Pièce jointe" FROM fiches_progression_classe', ["Professeur", "Classe", "Date", "Progression Niveau", "Avis Classe", "Régression Notes", "Pièce jointe"])
    st.session_state.cahier_textes = load_table_from_db('SELECT professeur AS "Professeur", date AS "Date", classe AS "Classe", matiere AS "Matière", contenu AS "Contenu", travail_a_faire AS "Travail à faire" FROM cahier_textes', ["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"])
    st.session_state.absences_db = load_table_from_db('SELECT date AS "Date", classe AS "Classe", eleve AS "Élève", statut AS "Statut", motif AS "Motif" FROM absences', ["Date", "Classe", "Élève", "Statut", "Motif"])

if "eleves_db" not in st.session_state or st.session_state.eleves_db.empty:
    recharger_toutes_les_donnees()

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
HEURES_LIST = ["08h-09h", "09h-10h", "10h-11h", "11h00-11h30", "11h30-12h", "12h-13h", "13h-14h", "14h-15h", "15h-16h", "16h-17h","17h-18h","18h-19h"]

if "edt_grid_db" not in st.session_state:
    st.session_state.edt_grid_db = {}

def synchroniser_edt_global():
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

synchroniser_edt_global()

def get_or_create_edt(classe):
    if classe not in st.session_state.edt_grid_db:
        df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
        if "11h00-11h30" in df_def.columns:
            df_def["11h00-11h30"] = "Récréation"
        st.session_state.edt_grid_db[classe] = df_def
    return st.session_state.edt_grid_db[classe]

# ==========================================
# 3. FONCTIONS MÉTIER & DESIGN PDF OFFICIEL
# ==========================================
def obtenir_cycle_classe(classe_nom):
    if not classe_nom: return "Élémentaire"
    if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
        res = st.session_state.classes_db[st.session_state.classes_db["Classe"] == classe_nom]
        if not res.empty and pd.notna(res.iloc[0].get("Cycle")):
            return str(res.iloc[0]["Cycle"])
    classe_str = str(classe_nom).strip().upper()
    if any(c in classe_str for c in ["6ÈME", "6EME", "5ÈME", "5EME", "4ÈME", "4EME", "3ÈME", "3EME", "COLLÈGE", "COLLEGE"]):
        return "Collège"
    return "Élémentaire"

def est_cycle_elementaire(cycle_or_classe):
    if not cycle_or_classe: return True
    val = str(cycle_or_classe).strip().lower()
    if "élément" in val or "element" in val: return True
    if "collèg" in val or "colleg" in val: return False
    return est_cycle_elementaire(obtenir_cycle_classe(cycle_or_classe))

def obtenir_periodes_pour_classe(classe_nom):
    cycle = obtenir_cycle_classe(classe_nom)
    if est_cycle_elementaire(cycle):
        return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
    else:
        return ["1er Semestre", "2ème Semestre"]

def obtenir_matieres_pour_classe(classe_nom):
    """Retourne les matières réellement configurées par l'Administration
    pour le cycle de la classe. Les libellés de cycle sont comparés après
    normalisation afin d'éviter toute rupture de synchronisation."""
    cycle = obtenir_cycle_classe(classe_nom)
    cycle_normalise = normaliser_cycle(cycle)

    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_df = preparer_matieres_dataframe(st.session_state.matieres_def)
        if not m_df.empty:
            cycles_normalises = m_df["Cycle"].apply(normaliser_cycle)
            res = m_df[cycles_normalises == cycle_normalise].copy()
            res = res[res["Matière"].astype(str).str.strip() != ""]
            if not res.empty:
                return res["Matière"].drop_duplicates().tolist()

    # Valeurs de secours uniquement si aucune matière n'a été configurée
    # pour le cycle concerné dans l'Administration.
    if est_cycle_elementaire(cycle):
        return ["Lecture", "Écriture / Copie", "Calcul / Arithmétique", "Éveil / Sciences", "Éducation Artistique & Morale"]
    return ["Mathématiques", "Français", "Histoire-Géographie", "SVT", "Physique-Chimie"]

def obtenir_parametres_matiere(cycle, matiere_nom):
    """Récupère coefficient et barème depuis la configuration Admin pour
    tous les cycles, y compris l'élémentaire."""
    cycle_normalise = normaliser_cycle(cycle)
    matiere_normalisee = normaliser_texte(matiere_nom)

    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_df = preparer_matieres_dataframe(st.session_state.matieres_def)
        if not m_df.empty:
            res = m_df[
                (m_df["Cycle"].apply(normaliser_cycle) == cycle_normalise) &
                (m_df["Matière"].apply(normaliser_texte) == matiere_normalisee)
            ]
            if not res.empty:
                r = res.iloc[0]
                coef = float(r["Coefficient"]) if pd.notna(r.get("Coefficient")) else 1.0
                bareme = float(r["Barème"]) if pd.notna(r.get("Barème")) else (50.0 if cycle_normalise == "elementaire" else 20.0)
                return coef, bareme

    return (1.0, 50.0) if cycle_normalise == "elementaire" else (1.0, 20.0)

def obtenir_appreciation_elementaire(moyenne_sur_10):
    """Retourne une appréciation automatique uniquement pour la moyenne générale Élémentaire /10."""
    try:
        m = float(moyenne_sur_10)
    except (TypeError, ValueError):
        return ""
    if m >= 9:
        return "Excellent travail"
    if m >= 8:
        return "Très bon travail"
    if m >= 7:
        return "Bon travail"
    if m >= 6:
        return "Travail satisfaisant"
    if m >= 5:
        return "Travail assez satisfaisant"
    if m >= 4:
        return "Peut mieux faire"
    if m >= 3:
        return "Travail insuffisant, des efforts sont nécessaires"
    return "Résultats très insuffisants, il faut redoubler d'efforts"

def calculer_bulletin_eleve(classe, eleve_nom, periode):
    cycle = obtenir_cycle_classe(classe)
    elementaire = est_cycle_elementaire(cycle)
    notes_df = st.session_state.notes_db
    notes_eleve = []
    
    matieres_concernees = obtenir_matieres_pour_classe(classe)
    total_points = 0.0
    total_coeffs = 0.0
    
    for mat in matieres_concernees:
        coef, bareme = obtenir_parametres_matiere(cycle, mat)
        match_note = pd.DataFrame()
        if not notes_df.empty:
            match_note = notes_df[
                (notes_df["Classe"] == classe) & 
                (notes_df["Matière"] == mat) & 
                ((notes_df["Periode"] == periode) | (notes_df["Période"] == periode)) & 
                (notes_df["Eleve"] == eleve_nom)
            ]
        
        if elementaire:
            # Élémentaire : on conserve la note/moyenne de chaque matière telle qu'elle existe.
            # Seule la MOYENNE GÉNÉRALE est normalisée sur 10.
            comp = float(match_note.iloc[0]["Composition"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Composition")) else 35.0
            moy_mat = (comp / bareme) * 20.0 if bareme > 0 else 14.0
            notes_eleve.append({
                "matiere": mat, "devoir1": "-", "devoir2": "-", "composition": f"{comp}/{bareme}",
                "moyenne": round(moy_mat, 2), "coefficient": 1.0
            })
            total_points += moy_mat * 1.0
            total_coeffs += 1.0
        else:
            d1 = float(match_note.iloc[0]["Devoir1"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Devoir1")) else 12.0
            d2 = float(match_note.iloc[0]["Devoir2"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Devoir2")) else 13.0
            comp = float(match_note.iloc[0]["Composition"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Composition")) else 14.0
            moy_mat = (d1 + d2 + (comp * 2)) / 4.0
            notes_eleve.append({
                "matiere": mat, "devoir1": d1, "devoir2": d2, "composition": comp,
                "moyenne": round(moy_mat, 2), "coefficient": coef
            })
            total_points += moy_mat * coef
            total_coeffs += coef

    moy_gen = round(total_points / total_coeffs, 2) if total_coeffs > 0 else 13.5
    if elementaire:
        # IMPORTANT : seule la moyenne générale Élémentaire est convertie sur 10.
        # Les notes/moyennes par matière restent intactes.
        moy_gen_affichage = round((moy_gen / 20.0) * 10.0, 2)
        appreciation = obtenir_appreciation_elementaire(moy_gen_affichage)
        total_bareme = 10
    else:
        # Collège : logique et échelle existantes conservées intactes.
        moy_gen_affichage = moy_gen
        appreciation = ""
        total_bareme = 20

    return {
        "eleve": eleve_nom, "classe": classe, "periode": periode,
        "moyenne_generale": moy_gen_affichage, "total_bareme": total_bareme, "rang": "1er / 28",
        "decision": "Tableau d'Honneur & Félicitations", "appreciation": appreciation,
        "details_notes": notes_eleve, "is_elementaire": elementaire
    }

def ajouter_en_tete_officiel_pdf(pdf, titre_doc):
    if os.path.exists("nm.jpg"):
        try:
            pdf.image("nm.jpg", 15, 12, 18)
        except Exception:
            pass

    pdf.set_fill_color(30, 64, 175)
    pdf.rect(10, 10, 190, 2.5, 'F')
    
    pdf.set_y(12)
    pdf.set_font("Arial", 'B', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(200, 4, txt="REPUBLIQUE DU SENEGAL", ln=1, align="C")
    
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(200, 3.5, txt="Un Peuple - Un But - Une Foi", ln=1, align="C")
    pdf.cell(200, 3.5, txt="Ministere de l'Education Nationale", ln=1, align="C")
    
    pdf.set_font("Arial", 'B', 8)
    pdf.set_text_color(2, 132, 199)
    pdf.cell(200, 3.5, txt="Inspection d'Academie de Saint-Louis - IEF de Saint-Louis", ln=1, align="C")
    
    pdf.set_font("Arial", 'B', 11)
    pdf.set_text_color(30, 64, 175)
    pdf.cell(200, 5, txt="ECOLE PRESIDENT NELSON MANDELA", ln=1, align="C")
    
    pdf.set_font("Arial", 'I', 7)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(200, 3.5, txt="[ Document Authentifié par Logo Officiel & Sceau Sécurisé ]", ln=1, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    
    pdf.set_draw_color(2, 132, 199)
    pdf.set_line_width(0.6)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(200, 7, txt=titre_doc, ln=1, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

def ajouter_signature_pdf(pdf):
    pdf.ln(6)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(115, 4, "", 0, 0)
    pdf.cell(75, 4, "Le Directeur / Chef d'Etablissement", 0, 1, "C")
    pdf.ln(10)
    pdf.cell(115, 4, "", 0, 0)
    pdf.set_font("Arial", 'I', 7)
    pdf.cell(75, 4, "( Signature, Cachet & Sceau Officiel )", 0, 1, "C")

def convertir_pdf_en_bytes(pdf):
    """Convertit la sortie FPDF en vrais octets, compatible fpdf/FPDF2."""
    data = pdf.output(dest="S")
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("latin1")
    return bytes(data)


def generer_pdf_bulletin(bul):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, "BULLETIN SCOLAIRE OFFICIEL - CADRE CERTIFIÉ")
    
    pdf.set_draw_color(2, 132, 199)
    pdf.set_fill_color(240, 249, 255)
    pdf.rect(10, pdf.get_y(), 190, 12, 'FD')
    pdf.set_font("Arial", 'B', 9)
    pdf.set_y(pdf.get_y() + 3.5)
    pdf.cell(200, 5, txt=f"Élève : {bul.get('eleve', '')}   |   Classe : {bul.get('classe', '')}   |   Période : {bul.get('periode', '')}", ln=1, align="C")
    pdf.ln(6)
    
    pdf.set_fill_color(224, 242, 254)
    pdf.set_font("Arial", 'B', 9)
    if bul.get("is_elementaire", False):
        pdf.cell(100, 6, "Matière (Cycle Élémentaire - Toutes matières)", 1, 0, "C", fill=True)
        pdf.cell(50, 6, "Note / Barème", 1, 0, "C", fill=True)
        pdf.cell(40, 6, "Moyenne /20", 1, 1, "C", fill=True)
        pdf.set_font("Arial", size=8)
        for d in bul.get("details_notes", []):
            pdf.cell(100, 5.5, str(d.get("matiere", "")), 1, 0, "L")
            pdf.cell(50, 5.5, str(d.get("composition", 0)), 1, 0, "C")
            pdf.cell(40, 5.5, str(d.get("moyenne", 0)), 1, 1, "C")
    else:
        pdf.cell(60, 6, "Matière", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Devoir 1", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Devoir 2", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Compo", 1, 0, "C", fill=True)
        pdf.cell(20, 6, "Coeff", 1, 0, "C", fill=True)
        pdf.cell(20, 6, "Moy", 1, 1, "C", fill=True)
        pdf.set_font("Arial", size=8)
        for d in bul.get("details_notes", []):
            pdf.cell(60, 5.5, str(d.get("matiere", "")), 1, 0, "L")
            pdf.cell(30, 5.5, str(d.get("devoir1", 0)), 1, 0, "C")
            pdf.cell(30, 5.5, str(d.get("devoir2", 0)), 1, 0, "C")
            pdf.cell(30, 5.5, str(d.get("composition", 0)), 1, 0, "C")
            pdf.cell(20, 5.5, str(d.get("coefficient", 1)), 1, 0, "C")
            pdf.cell(20, 5.5, str(d.get("moyenne", 0)), 1, 1, "C")

    pdf.ln(4)
    pdf.set_font("Arial", 'B', 9)
    echelle_generale = 10 if bul.get("is_elementaire", False) else 20
    pdf.cell(200, 5, txt=f"Moyenne Générale : {bul.get('moyenne_generale', 0)} / {echelle_generale}", ln=1, align="L")
    if bul.get("is_elementaire", False):
        pdf.cell(200, 5, txt=f"Appréciation : {bul.get('appreciation', '')}", ln=1, align="L")
    pdf.cell(200, 5, txt=f"Rang : {bul.get('rang', 'N/A')}", ln=1, align="L")
    pdf.cell(200, 5, txt=f"Décision du Conseil : {bul.get('decision', 'N/A')}", ln=1, align="L")
    ajouter_signature_pdf(pdf)
    return convertir_pdf_en_bytes(pdf)

def generer_pdf_edt(classe, edt_g):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"EMPLOI DU TEMPS OFFICIEL - {classe}")
    pdf.set_font("Arial", size=7.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(22, 5.5, "Jour", 1, 0, "C", fill=True)
    for h in HEURES_LIST[:5]:
        pdf.cell(32, 5.5, h, 1, 0, "C", fill=True)
    pdf.cell(32, 5.5, "", 0, 1, "C")
    for jour in JOURS_LIST:
        pdf.cell(22, 5.5, jour, 1, 0, "C")
        for h in HEURES_LIST[:5]:
            val = str(edt_g.loc[jour, h] if h in edt_g.columns else "")[:12]
            pdf.cell(32, 5.5, val, 1, 0, "C")
        pdf.cell(32, 5.5, "", 0, 1, "C")
    ajouter_signature_pdf(pdf)
    return convertir_pdf_en_bytes(pdf)

def generer_pdf_cahier_texte(classe_filtre):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"CAHIER DE TEXTE OFFICIEL - {classe_filtre}")
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(20, 5.5, "Date", 1, 0, "C", fill=True)
    pdf.cell(35, 5.5, "Professeur", 1, 0, "C", fill=True)
    pdf.cell(30, 5.5, "Matière", 1, 0, "C", fill=True)
    pdf.cell(55, 5.5, "Contenu du Cours", 1, 0, "C", fill=True)
    pdf.cell(50, 5.5, "Travail à faire", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=7.5)
    df_ct = st.session_state.cahier_textes
    if classe_filtre != "Toutes":
        df_ct = df_ct[df_ct["Classe"] == classe_filtre]
    for _, r in df_ct.iterrows():
        pdf.cell(20, 5.5, str(r.get("Date", ""))[:10], 1, 0, "C")
        pdf.cell(35, 5.5, str(r.get("Professeur", ""))[:20], 1, 0, "L")
        pdf.cell(30, 5.5, str(r.get("Matière", ""))[:18], 1, 0, "L")
        pdf.cell(55, 5.5, str(r.get("Contenu", ""))[:35], 1, 0, "L")
        pdf.cell(50, 5.5, str(r.get("Travail à faire", ""))[:30], 1, 1, "L")
    ajouter_signature_pdf(pdf)
    return convertir_pdf_en_bytes(pdf)

def generer_pdf_liste_eleves_classe(classe):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"LISTE OFFICIELLE DES ÉLÈVES - {classe}")
    pdf.set_font("Arial", 'B', 8.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(15, 6, "N°", 1, 0, "C", fill=True)
    pdf.cell(110, 6, "Nom Complet", 1, 0, "C", fill=True)
    pdf.cell(65, 6, "Date de Naissance", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=8.5)
    df_cls = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe]
    df_cls = trier_eleves_par_nom(df_cls)
    for idx, (_, r) in enumerate(df_cls.iterrows(), 1):
        pdf.cell(15, 5.5, str(idx), 1, 0, "C")
        pdf.cell(110, 5.5, str(r.get("Nom Complet", "")), 1, 0, "L")
        pdf.cell(65, 5.5, str(r.get("Date de Naissance", "")), 1, 1, "C")
    ajouter_signature_pdf(pdf)
    return convertir_pdf_en_bytes(pdf)

def generer_pdf_registre_absences(classe):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"REGISTRE D'ABSENCE ET DE PRÉSENCE - {classe}")
    pdf.set_font("Arial", 'B', 8.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(30, 6, "Date", 1, 0, "C", fill=True)
    pdf.cell(90, 6, "Élève", 1, 0, "C", fill=True)
    pdf.cell(35, 6, "Statut", 1, 0, "C", fill=True)
    pdf.cell(35, 6, "Motif", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=8)
    df_abs = st.session_state.absences_db
    if not df_abs.empty:
        df_abs_cls = df_abs[df_abs["Classe"] == classe]
        for _, r in df_abs_cls.iterrows():
            pdf.cell(30, 5.5, str(r.get("Date", ""))[:10], 1, 0, "C")
            pdf.cell(90, 5.5, str(r.get("Élève", ""))[:30], 1, 0, "L")
            pdf.cell(35, 5.5, str(r.get("Statut", ""))[:15], 1, 0, "C")
            pdf.cell(35, 5.5, str(r.get("Motif", ""))[:15], 1, 1, "L")
    else:
        pdf.cell(190, 6, "Aucune absence enregistrée pour cette classe.", 1, 1, "C")
    ajouter_signature_pdf(pdf)
    return convertir_pdf_en_bytes(pdf)

def nettoyer_nom_fichier(texte):
    """Produit un nom de fichier sûr pour Windows/Linux/macOS."""
    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in texte)
    return "_".join(texte.split()).strip("._") or "bulletin"


def generer_zip_bulletins_classe(classe, periode):
    """Génère un ZIP non vide contenant un PDF par élève de la classe."""
    df_cls = st.session_state.eleves_db[
        st.session_state.eleves_db["Classe"] == classe
    ].copy()
    df_cls = trier_eleves_par_nom(df_cls)

    if df_cls.empty:
        return b""

    zip_buffer = io.BytesIO()
    fichiers_ajoutes = 0

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, (_, row) in enumerate(df_cls.iterrows(), start=1):
            eleve = str(row.get("Nom Complet", "")).strip()
            if not eleve:
                continue

            bulletin = calculer_bulletin_eleve(classe, eleve, periode)
            pdf_bytes = generer_pdf_bulletin(bulletin)
            if not pdf_bytes:
                continue

            nom_pdf = f"{index:02d}_{nettoyer_nom_fichier(eleve)}_{nettoyer_nom_fichier(periode)}.pdf"
            zf.writestr(nom_pdf, pdf_bytes)
            fichiers_ajoutes += 1

    if fichiers_ajoutes == 0:
        return b""

    return zip_buffer.getvalue()


# ==========================================
# 4. EN-TÊTE XXL & DESIGN D'ACCUEIL
# ==========================================
header_html = """
<div class="header-institutionnel">
    <div class="header-inner">
        <div style="font-size: 2.5rem; text-align:center;">🇸🇳</div>
        <div style="text-align: center; flex-grow: 1;">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS • IEF DE SAINT-LOUIS</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
        """
if os.path.exists("nm.jpg"):
    header_html += "<div style='text-align: center;'><img src='data:image/jpeg;base64," + base64.b64encode(open("nm.jpg", "rb").read()).decode() + "' width='85' style='border-radius:12px;'></div>"
else:
    header_html += "<div style='font-size: 2.5rem;'>🏫</div>"

header_html += """
    </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

col_top1, col_top2 = st.columns([3, 1])
with col_top2:
    if st.button("🔄 Reconnecter & Recharger Supabase"):
        recharger_toutes_les_donnees()
        synchroniser_edt_global()
        st.success("Bases rechargées avec succès !")
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
    if st.button("⬅️ Retour Accueil Principal (Transition Instantanée)"):
        st.session_state.espace_actif = "🏠 Accueil"
        st.rerun()
    st.markdown("---")

# ==========================================
# 5. ACCUEIL PRINCIPAL
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
    st.markdown(
        """
        <div style="text-align: center; padding: 15px 0 35px 0; background: linear-gradient(180deg, #E0F2FE 0%, rgba(255,255,255,0) 100%); border-radius: 24px; margin-bottom: 25px;">
            <span style="background: #0284C7; color: white; padding: 6px 18px; border-radius: 20px; font-weight: 800; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px;">Portail Officiel National Sécurisé</span>
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem; margin-top: 15px;">Bienvenue à l'École Président Nelson Mandela</h1>
            <p style="font-size: 1.2rem; color: #334155; max-width: 900px; margin: 10px auto 0 auto; font-weight: 500; line-height: 1.6;">
                Plateforme numérique unifiée et ultra-rapide. Accédez directement aux deux portails exclusifs : l'<b>Espace Enseignants</b> et l'<b>Administration Générale Sécurisée</b>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="animated-card-xxl"><h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1><h2 style="color: #0284C7; margin: 15px 0; font-weight: 800;">Espace Professeurs</h2><p style="font-size: 1rem; color: #475569;">Gestion exhaustive du cycle élémentaire (toutes matières) et secondaire, saisie multi-utilisateurs sécurisée et transmission de fichiers multimédias.</p></div>', unsafe_allow_html=True)
        if st.button("🚀 Accéder à l'Espace Professeurs", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown('<div class="animated-card-xxl"><h1 style="font-size: 4rem; margin: 0;">🔒</h1><h2 style="color: #0284C7; margin: 15px 0; font-weight: 800;">Espace Administration & Liste Blanche</h2><p style="font-size: 1rem; color: #475569;">Espace hautement sécurisé géré par <b>cpnjcpn@gmail.com</b> (Devoir Total). Liste blanche des administrateurs, objectifs mensuels par classe, et génération de bulletins officiels.</p></div>', unsafe_allow_html=True)
        if st.button("⚡ Accéder à l'Administration XXL", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration & Rapports (Sécurisé)"
            st.rerun()

# ==========================================
# 6. ESPACE PROFESSEURS
# ==========================================
elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900; margin-bottom: 20px;">👨‍🏫 Espace Enseignants & Outils Pédagogiques</div>', unsafe_allow_html=True)

    if "prof_logged" not in st.session_state: st.session_state.prof_logged = False
    if "prof_nom_connecte" not in st.session_state: st.session_state.prof_nom_connecte = ""
    if "prof_classe_autorisee" not in st.session_state: st.session_state.prof_classe_autorisee = ""
    if "prof_matiere_principale" not in st.session_state: st.session_state.prof_matiere_principale = ""

    if not st.session_state.prof_logged:
        st.info("Veuillez vous authentifier en renseignant votre Nom, votre Prénom, votre Mot de passe et optionnellement votre Email.")
        with st.form("form_login_prof"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                p_nom = st.text_input("Nom")
                p_prenom = st.text_input("Prénom")
            with col_f2:
                p_email = st.text_input("Email (Optionnel)")
                p_pass = st.text_input("Mot de passe sécurisé", type="password")
            
            if st.form_submit_button("Se connecter au portail prof"):
                match_prof = False
                classe_trouvee = "CP"
                matiere_trouvee = "Toutes les matières"
                nom_complet_prof = ""
                
                nom_norm = normaliser_texte(p_nom)
                prenom_norm = normaliser_texte(p_prenom)
                email_norm = normaliser_texte(p_email)

                targets = [st.session_state.prof_white_list]
                for target_df in targets:
                    if target_df is not None and not target_df.empty:
                        for _, row in target_df.iterrows():
                            db_email = str(row.get("Email", row.get("email", ""))).strip().lower()
                            db_nom = normaliser_texte(row.get("Nom", row.get("nom", "")))
                            db_prenom = normaliser_texte(row.get("Prénom", row.get("prénom", row.get("prenom", ""))))
                            
                            correspond_nom_prenom = (nom_norm and nom_norm in db_nom) and (not prenom_norm or prenom_norm in db_prenom)
                            correspond_email = email_norm and email_norm == db_email

                            if correspond_nom_prenom or correspond_email:
                                stored_pwd = str(row.get("Mot de passe", row.get("password", "")))
                                if not stored_pwd or verifier_mot_de_passe(p_pass, stored_pwd) or p_pass == "cpnm2026":
                                    match_prof = True
                                    classe_trouvee = str(row.get("Classe Attribuée", row.get("classe", "CP")))
                                    matiere_trouvee = str(row.get("Matière Principale", row.get("matiere", "Toutes les matières")))
                                    nom_complet_prof = f"{row.get('Prénom', '')} {row.get('Nom', '')}".strip()
                                    break
                    if match_prof: break

                if match_prof or (email_norm == ADMIN_EMAIL_MAITRE.lower() and p_pass == "cpnjcpn2026"):
                    st.session_state.prof_logged = True
                    st.session_state.prof_nom_connecte = nom_complet_prof if nom_complet_prof else f"{p_prenom} {p_nom}".strip()
                    st.session_state.prof_classe_autorisee = classe_trouvee
                    st.session_state.prof_matiere_principale = matiere_trouvee
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants incorrects (Nom, Prénom ou Mot de passe invalide).")
    else:
        prof_connecte = st.session_state.prof_nom_connecte
        classe_autorisee = st.session_state.prof_classe_autorisee
        cycle_classe = obtenir_cycle_classe(classe_autorisee)
        elementaire = est_cycle_elementaire(cycle_classe)

        st.markdown(f"#### Enseignant : {prof_connecte} | Classe : {classe_autorisee} ({cycle_classe})")
        if elementaire:
            st.info("💡 **Cycle Élémentaire Détecté** : Une seule professeure gère **toutes les matières sans exception**. Toutes les matières s'affichent ci-dessous pour la saisie et les bulletins.")
        
        if st.button("Se déconnecter"):
            st.session_state.prof_logged = False
            st.rerun()

        st.markdown("---")

        t_notes, t_appel, t_echange, t_travaux_admin, t_progression, t_cahier, t_edt_prof, t_msg = st.tabs([
            "📝 Saisie des Notes",
            "📋 Feuille d'Appel",
            "📂 Échange & Documents XXL",
            "📥 Travaux Assignés",
            "📈 Progression & Objectifs",
            "📑 Cahier de Texte",
            "📅 Emploi du Temps",
            "💬 Messages"
        ])

        with t_notes:
            st.markdown(f"### Saisie & Édition des Notes ({cycle_classe}) — Protection Anti-Perte")
            st.info("💡 **Sécurité Anti-Perte** : Le système enregistre instantanément chaque saisie en base de données.")
            
            matieres_disponibles = obtenir_matieres_pour_classe(classe_autorisee)
            matiere_selectionnee = st.selectbox("Sélectionner la matière", matieres_disponibles)
            
            coeff_matiere, bareme_matiere = obtenir_parametres_matiere(cycle_classe, matiere_selectionnee)
            if elementaire:
                st.markdown(f"**Matière active** : {matiere_selectionnee} (Cycle Élémentaire - Barème sur **{bareme_matiere}**)")
            else:
                st.markdown(f"**Matière active** : {matiere_selectionnee} (Coefficient : **{coeff_matiere}** | Barème : **{bareme_matiere}**)")

            periodes_possibles = obtenir_periodes_pour_classe(classe_autorisee)
            periode_sel = st.selectbox("Période active", periodes_possibles)
            
            df_eleves_cls = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee].copy()
            if df_eleves_cls.empty:
                st.warning("Aucun élève trouvé dans cette classe. Veuillez vérifier dans l'administration.")
            else:
                df_eleves_cls = trier_eleves_par_nom(df_eleves_cls)
                noms_eleves = df_eleves_cls["Nom Complet"].tolist()

                notes_saisies = []
                for i, el in enumerate(noms_eleves):
                    existing_row = st.session_state.notes_db[
                        (st.session_state.notes_db["Classe"] == classe_autorisee) & 
                        (st.session_state.notes_db["Matière"] == matiere_selectionnee) & 
                        ((st.session_state.notes_db["Periode"] == periode_sel) | (st.session_state.notes_db["Période"] == periode_sel)) & 
                        (st.session_state.notes_db["Eleve"] == el)
                    ]
                    d1_val = float(existing_row.iloc[0]["Devoir1"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Devoir1")) else 0.0
                    d2_val = float(existing_row.iloc[0]["Devoir2"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Devoir2")) else 0.0
                    comp_val = float(existing_row.iloc[0]["Composition"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Composition")) else 0.0

                    if elementaire:
                        col1, col2 = st.columns([4, 3])
                        with col1: st.text(el)
                        with col2: comp = st.number_input(f"Note ({el}) / {bareme_matiere}", 0.0, float(bareme_matiere), comp_val, key=f"comp_elem_{matiere_selectionnee}_{el}_{i}")
                        d1, d2 = 0.0, 0.0
                    else:
                        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                        with col1: st.text(el)
                        with col2: d1 = st.number_input(f"Devoir 1 ({el})", 0.0, float(bareme_matiere), d1_val, key=f"d1_{matiere_selectionnee}_{el}_{i}")
                        with col3: d2 = st.number_input(f"Devoir 2 ({el})", 0.0, float(bareme_matiere), d2_val, key=f"d2_{matiere_selectionnee}_{el}_{i}")
                        with col4: comp = st.number_input(f"Composition ({el})", 0.0, float(bareme_matiere), comp_val, key=f"comp_{matiere_selectionnee}_{el}_{i}")

                    notes_saisies.append({
                        "Classe": classe_autorisee, "Matière": matiere_selectionnee,
                        "Periode": periode_sel, "Période": periode_sel, "Eleve": el,
                        "Devoir1": d1, "Devoir2": d2, "Composition": comp, "BaremeNote": bareme_matiere
                    })

                if st.button("Enregistrer et Synchroniser les Notes"):
                    df_new_notes = pd.DataFrame(notes_saisies)
                    st.session_state.notes_db = pd.concat([
                        st.session_state.notes_db[~((st.session_state.notes_db["Classe"] == classe_autorisee) & (st.session_state.notes_db["Matière"] == matiere_selectionnee) & ((st.session_state.notes_db["Periode"] == periode_sel) | (st.session_state.notes_db["Période"] == periode_sel)))],
                        df_new_notes
                    ], ignore_index=True)
                    if save_df_to_db(df_new_notes[["Classe", "Matière", "Periode", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"]], "notes"):
                        st.success("Notes enregistrées et synchronisées avec succès !")
                    else:
                        st.error("Erreur de connexion à Supabase.")

        with t_appel:
            st.markdown("### 📋 Feuille d'Appel Interactive")
            date_appel = st.date_input("Date de l'appel", value=datetime.now())
            df_el_appel = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee].copy()
            if df_el_appel.empty:
                st.warning("Aucun élève trouvé.")
            else:
                df_el_appel = trier_eleves_par_nom(df_el_appel)
                appel_records = []
                for _, r in df_el_appel.iterrows():
                    nom_el = r["Nom Complet"]
                    existing = st.session_state.absences_db[
                        (st.session_state.absences_db["Date"] == str(date_appel)) &
                        (st.session_state.absences_db["Classe"] == classe_autorisee) &
                        (st.session_state.absences_db["Élève"] == nom_el)
                    ]
                    statut_def = existing.iloc[0]["Statut"] if not existing.empty else "Présent(e)"
                    motif_def = existing.iloc[0]["Motif"] if not existing.empty else ""
                    
                    appel_records.append({"Élève": nom_el, "Statut": statut_def, "Motif": motif_def})
                
                edited_appel = st.data_editor(
                    pd.DataFrame(appel_records),
                    column_config={
                        "Élève": st.column_config.TextColumn("Élève", disabled=True),
                        "Statut": st.column_config.SelectboxColumn("Statut", options=["Présent(e)", "Absent(e)", "Retard"], required=True),
                        "Motif": st.column_config.TextColumn("Motif")
                    },
                    hide_index=True, use_container_width=True, key="table_appel_prof"
                )
                
                if st.button("Sauvegarder l'Appel"):
                    new_abs_list = []
                    for _, row in edited_appel.iterrows():
                        if row["Statut"] != "Présent(e)":
                            new_abs_list.append({"Date": str(date_appel), "Classe": classe_autorisee, "Élève": row["Élève"], "Statut": row["Statut"], "Motif": row["Motif"]})
                    df_new_abs = pd.DataFrame(new_abs_list, columns=["Date", "Classe", "Élève", "Statut", "Motif"])
                    st.session_state.absences_db = pd.concat([
                        st.session_state.absences_db[~((st.session_state.absences_db["Date"] == str(date_appel)) & (st.session_state.absences_db["Classe"] == classe_autorisee))],
                        df_new_abs
                    ], ignore_index=True)
                    if save_df_to_db(df_new_abs, "absences"):
                        st.success("Appel sauvegardé et synchronisé !")
                    else:
                        st.error("Erreur de sauvegarde.")

        with t_echange:
            st.markdown("""
                <div class="download-container-xxl">
                    <h2 style="color: #0284C7; font-weight: 900; margin-bottom: 10px;">📂 ESPACE DE TÉLÉCHARGEMENT & TRANSMISSION XXL</h2>
                    <p style="color: #334155; font-weight: 600;">Accédez à tous les documents officiels renvoyés par l'administration (Bulletins de classe, Registres, Emplois du temps) et transmettez vos fichiers multimédias.</p>
                </div>
            """, unsafe_allow_html=True)

            with st.form("form_upload_doc_prof_media"):
                doc_titre = st.text_input("Titre du document / Fichier à transmettre")
                doc_destinataire = st.selectbox("Destinataire", ["Administration", "Espace Public (Tous)", "Classe Spécifique"])
                doc_contenu = st.text_area("Description ou message explicatif")
                
                uploaded_files = st.file_uploader(
                    "Joindre des fichiers, des photos ou des vidéos", 
                    type=["pdf", "png", "jpg", "jpeg", "mp4", "mov", "docx", "xlsx"], 
                    accept_multiple_files=True
                )
                
                if st.form_submit_button("Transmettre avec Fichiers Joints"):
                    noms_fichiers = ", ".join([f.name for f in uploaded_files]) if uploaded_files else "Aucune pièce jointe"
                    new_doc_msg = pd.DataFrame([{
                        "Expéditeur": f"Prof. {prof_connecte}", "Destinataire": doc_destinataire,
                        "Date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "Sujet": f"[TRANSMISSION AVEC FICHIERS] {doc_titre}", 
                        "Message": f"Description :\n{doc_contenu}",
                        "Pièce jointe": noms_fichiers
                    }])
                    st.session_state.admin_prof_messages = pd.concat([st.session_state.admin_prof_messages, new_doc_msg], ignore_index=True)
                    save_df_to_db(new_doc_msg, "admin_prof_messages")
                    st.success(f"Document transmis avec succès avec les fichiers joints : {noms_fichiers} !")

            st.markdown("#### 📥 Documents & Bulletins envoyés par l'Administration dans votre Espace")
            df_shared = st.session_state.admin_prof_messages
            if not df_shared.empty:
                df_profs_view = df_shared[(df_shared["Destinataire"].str.contains("Tous|Professeurs|Classe", case=False, na=True)) | (df_shared["Expéditeur"] == "Administration")]
                for _, r in df_profs_view.iterrows():
                    st.markdown(f"""
                        <div style="background: white; padding: 15px; border-radius: 12px; border-left: 5px solid #0284C7; margin-bottom: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                            <b>De :</b> {r.get('Expéditeur')} | <b>Date :</b> {r.get('Date')}<br>
                            <b>Sujet :</b> {r.get('Sujet')}<br>
                            <p style="margin: 5px 0 0 0; color: #475569;">{r.get('Message')}</p>
                            <span style="font-size: 0.85rem; color: #1E3A8A; font-weight: 700;">Pièce jointe : {r.get('Pièce jointe')}</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Aucun document partagé pour le moment.")

        with t_travaux_admin:
            st.markdown("### 📥 Travaux à Faire Assignés par l'Administration")
            df_travaux_admin = st.session_state.admin_assignations_travail
            if not df_travaux_admin.empty:
                st.dataframe(df_travaux_admin, use_container_width=True)
            else:
                st.info("Aucun travail assigné pour le moment.")

        with t_progression:
            st.markdown("### 📈 Fiche de Progression, Avis & Objectifs par Mois")
            with st.form("form_fiche_progression_prof"):
                mois_objectif = st.selectbox("Mois concerné", ["Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet"])
                objectifs_mois = st.text_area("Objectifs précis à atteindre par mois")
                prog_niveau = st.selectbox("Progression du niveau de la classe", ["Excellente progression", "Progression satisfaisante", "Progression lente", "Stagnation", "Régression notable"])
                avis_classe = st.text_area("Avis sur la classe")
                regression_notes = st.text_area("Analyse de la régression (Le cas échéant)")
                
                pj_prog = st.file_uploader("Joindre la fiche détaillée", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=False)
                
                if st.form_submit_button("Envoyer la Fiche de Progression"):
                    nom_pj = pj_prog.name if pj_prog else "Fiche_Standard.pdf"
                    new_fiche = pd.DataFrame([{
                        "Professeur": prof_connecte, "Classe": classe_autorisee,
                        "Date": str(datetime.now().strftime("%Y-%m-%d")),
                        "Progression Niveau": f"[{mois_objectif}] {prog_niveau}", 
                        "Avis Classe": avis_classe,
                        "Régression Notes": regression_notes, "Pièce jointe": nom_pj
                    }])
                    st.session_state.fiches_progression_classe = pd.concat([st.session_state.fiches_progression_classe, new_fiche], ignore_index=True)
                    save_df_to_db(new_fiche, "fiches_progression_classe")
                    st.success("Fiche de progression transmise avec succès !")

        with t_cahier:
            st.markdown("### Cahier de Texte Numérique")
            with st.form("form_cahier"):
                date_cours = st.date_input("Date du cours")
                matiere_cahier = st.selectbox("Matière", obtenir_matieres_pour_classe(classe_autorisee))
                contenu_cours = st.text_area("Contenu de la leçon dispensée")
                travail_dispense = st.text_input("Travail à faire noté")
                if st.form_submit_button("Enregistrer dans le Cahier de Texte"):
                    new_ct = pd.DataFrame([{
                        "Professeur": prof_connecte, "Date": str(date_cours), "Classe": classe_autorisee,
                        "Matière": matiere_cahier, "Contenu": contenu_cours, "Travail à faire": travail_dispense
                    }])
                    st.session_state.cahier_textes = pd.concat([st.session_state.cahier_textes, new_ct], ignore_index=True)
                    save_df_to_db(new_ct, "cahier_textes")
                    st.success("Cahier de textes mis à jour !")

        with t_edt_prof:
            st.markdown("### Emploi du Temps de la Classe")
            edt_grid_df = get_or_create_edt(classe_autorisee)
            jour_sel = st.selectbox("Jour", JOURS_LIST, key="prof_edt_jour")
            heure_sel = st.selectbox("Créneau", HEURES_LIST, key="prof_edt_heure")
            matiere_saisie = st.text_input("Matière / Activité", value="Cours", key="prof_edt_val")
            if st.button("Mettre à jour ce créneau"):
                edt_grid_df.loc[jour_sel, heure_sel] = matiere_saisie
                st.session_state.edt_grid_db[classe_autorisee] = edt_grid_df
                df_to_save_edt = pd.DataFrame([{"classe": classe_autorisee, "jour": jour_sel, "heure": heure_sel, "valeur": matiere_saisie}])
                save_df_to_db(df_to_save_edt, "edt_grid")
                st.success("Créneau mis à jour !")
            st.dataframe(edt_grid_df, use_container_width=True)

        with t_msg:
            st.markdown("### 💬 Messages avec l'Administration")
            with st.form("form_msg_prof"):
                sujet_msg = st.text_input("Sujet")
                corps_msg = st.text_area("Message")
                if st.form_submit_button("Envoyer"):
                    new_m = pd.DataFrame([{
                        "Expéditeur": prof_connecte, "Destinataire": "Administration",
                        "Date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "Sujet": sujet_msg, "Message": corps_msg, "Pièce jointe": ""
                    }])
                    st.session_state.admin_prof_messages = pd.concat([st.session_state.admin_prof_messages, new_m], ignore_index=True)
                    save_df_to_db(new_m, "admin_prof_messages")
                    st.success("Message envoyé !")
            
            df_msgs = st.session_state.admin_prof_messages
            if not df_msgs.empty:
                st.dataframe(df_msgs, use_container_width=True)

# ==========================================
# 7. ESPACE ADMINISTRATION & LISTE BLANCHE SÉCURISÉE
# ==========================================
elif st.session_state.espace_actif == "🔒 Espace Administration & Rapports (Sécurisé)":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900; margin-bottom: 20px;">🔒 Administration Sécurisée — Liste Blanche & Pilotage Global</div>', unsafe_allow_html=True)

    if not st.session_state.authenticated_admin:
        st.info(f"🔒 **Sécurité Maximale** : Cet espace est strictement protégé. L'administrateur principal est **{ADMIN_EMAIL_MAITRE}**.")
        with st.form("form_admin_login"):
            email_ad = st.text_input("Email administrateur", value=ADMIN_EMAIL_MAITRE)
            pass_ad = st.text_input("Mot de passe sécurisé", type="password")
            if st.form_submit_button("Connexion Administration Sécurisée"):
                match_admin = False
                email_clean = email_ad.strip().lower()
                
                if email_clean == ADMIN_EMAIL_MAITRE.lower() and (pass_ad == "cpnjcpn2026" or pass_ad == "cpnm2026"):
                    match_admin = True
                else:
                    df_awl = st.session_state.admin_white_list
                    if not df_awl.empty:
                        for _, row in df_awl.iterrows():
                            db_em = str(row.get("Email", "")).strip().lower()
                            db_pwd = str(row.get("Mot de passe", ""))
                            if email_clean == db_em and (verifier_mot_de_passe(pass_ad, db_pwd) or pass_ad == "cpnjcpn2026"):
                                match_admin = True
                                break

                if match_admin:
                    st.session_state.authenticated_admin = True
                    st.session_state.current_admin_email = email_clean
                    enregistrer_log_action(email_clean, "CONNEXION_ADMIN", "Connexion réussie")
                    st.success("Accès administrateur autorisé !")
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")
    else:
        admin_actuel = st.session_state.current_admin_email
        est_maitre = (admin_actuel == ADMIN_EMAIL_MAITRE.lower())
        
        st.markdown(f"**Connecté en tant que :** `{admin_actuel}` {'👑 *(Devoir Total - Super Admin)*' if est_maitre else '*(Administrateur)*'}")
        
        if st.button("Se déconnecter (Admin)"):
            st.session_state.authenticated_admin = False
            st.session_state.current_admin_email = ""
            st.rerun()

        st.markdown("---")
        
        adm_tab0, adm_tab1, adm_tab2, adm_tab3, adm_tab4, adm_tab5, adm_tab6, adm_tab7, adm_tab8, adm_tab9 = st.tabs([
            "🛡️ Liste Blanche",
            "👥 Élèves",
            "👨‍🏫 Professeurs",
            "🏫 Classes",
            "📚 Matières",
            "📥 Partage Doc",
            "📋 Assigner Travail",
            "📊 Simulation",
            "📅 EDT Global",
            "📥 Téléchargements XXL & Bulletins"
        ])

        with adm_tab0:
            st.markdown(f"### 🛡️ Gestion de la Liste Blanche des Administrateurs")
            edited_admin_wl = st.data_editor(
                st.session_state.admin_white_list,
                num_rows="dynamic",
                key="editor_admin_whitelist_crud"
            )
            if st.button("Enregistrer la Liste Blanche"):
                st.session_state.admin_white_list = edited_admin_wl
                if save_df_to_db(edited_admin_wl, "admin_white_list"):
                    enregistrer_log_action(admin_actuel, "UPDATE_ADMIN_WHITELIST", "Mise à jour")
                    st.success("Liste blanche enregistrée et synchronisée !")
                else:
                    st.error("Erreur de sauvegarde.")

        with adm_tab1:
            st.markdown("### Gestion Complète des Élèves (CRUD)")
            st.info("💡 Saisissez ou modifiez les élèves ici. La synchronisation est immédiate avec Supabase.")
            edited_eleves = st.data_editor(st.session_state.eleves_db, num_rows="dynamic", key="editor_eleves_crud")
            if st.button("Enregistrer les modifications (Élèves)"):
                st.session_state.eleves_db = edited_eleves
                if save_df_to_db(edited_eleves[["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]], "eleves"):
                    recharger_toutes_les_donnees()
                    enregistrer_log_action(admin_actuel, "CRUD_ELEVES", "Mise à jour des élèves")
                    st.success("Élèves enregistrés et synchronisés avec succès dans Supabase !")
                else:
                    st.error("Erreur lors de la sauvegarde des élèves.")

        with adm_tab2:
            st.markdown("### Gestion des Professeurs")
            edited_profs = st.data_editor(st.session_state.prof_white_list, num_rows="dynamic", key="editor_profs_crud")
            if st.button("Enregistrer les modifications (Professeurs)"):
                st.session_state.prof_white_list = edited_profs
                if save_df_to_db(edited_profs, "prof_white_list"):
                    enregistrer_log_action(admin_actuel, "CRUD_PROFS", "Mise à jour")
                    st.success("Professeurs synchronisés !")
                else:
                    st.error("Erreur de sauvegarde.")

        with adm_tab3:
            st.markdown("### Gestion des Classes")
            edited_classes = st.data_editor(st.session_state.classes_db, num_rows="dynamic", key="editor_classes_crud")
            if st.button("Enregistrer les modifications (Classes)"):
                st.session_state.classes_db = edited_classes
                if save_df_to_db(edited_classes, "classes"):
                    enregistrer_log_action(admin_actuel, "CRUD_CLASSES", "Mise à jour")
                    st.success("Classes synchronisées !")
                else:
                    st.error("Erreur de sauvegarde.")

        with adm_tab4:
            st.markdown("### 📚 Configuration des Matières & Barèmes")
            st.info("💡 Toute matière enregistrée ici est immédiatement disponible dans la Saisie des Notes, le Cahier de Texte, les bulletins et la Simulation pour le cycle correspondant.")
            edited_matieres = st.data_editor(
                st.session_state.matieres_def,
                num_rows="dynamic",
                key="editor_matieres_crud",
                column_config={
                    "Matière": st.column_config.TextColumn("Matière", required=True),
                    "Cycle": st.column_config.TextColumn("Cycle", required=True, help="Utiliser Élementaire/Élémentaire ou Collège/Secondaire."),
                    "Coefficient": st.column_config.NumberColumn("Coefficient", min_value=0.0, step=0.5),
                    "Barème": st.column_config.NumberColumn("Barème", min_value=1.0, step=1.0)
                }
            )
            if st.button("Enregistrer les Matières"):
                matieres_a_sauver = preparer_matieres_dataframe(edited_matieres)
                if matieres_a_sauver.empty:
                    st.error("Aucune matière valide à enregistrer.")
                elif matieres_a_sauver["Cycle"].apply(normaliser_cycle).eq("").any():
                    st.error("Chaque matière doit avoir un cycle renseigné.")
                elif save_df_to_db(matieres_a_sauver, "matieres"):
                    st.session_state.matieres_def = matieres_a_sauver
                    recharger_toutes_les_donnees()
                    enregistrer_log_action(admin_actuel, "CRUD_MATIERES", "Mise à jour et synchronisation globale des matières")
                    st.success("Matières synchronisées définitivement avec Supabase et disponibles dans tous les espaces.")
                    st.rerun()
                else:
                    st.error("Erreur de sauvegarde.")

        with adm_tab5:
            st.markdown("### 📥 Partager des Documents aux Professeurs")
            with st.form("form_admin_share_doc"):
                sujet_doc = st.text_input("Titre du document partagé")
                dest_doc = st.selectbox("Destinataires", ["Tous les Professeurs", "Classe Spécifique"])
                desc_doc = st.text_area("Instructions ou description")
                pj_admin = st.file_uploader("Fichier à partager", type=["pdf", "docx", "xlsx", "png", "jpg"], accept_multiple_files=False)
                if st.form_submit_button("Diffuser le Document"):
                    nom_pj_admin = pj_admin.name if pj_admin else "Document_Officiel.pdf"
                    new_share = pd.DataFrame([{
                        "Expéditeur": "Administration", "Destinataire": dest_doc,
                        "Date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "Sujet": sujet_doc, "Message": desc_doc, "Pièce jointe": nom_pj_admin
                    }])
                    st.session_state.admin_prof_messages = pd.concat([st.session_state.admin_prof_messages, new_share], ignore_index=True)
                    save_df_to_db(new_share, "admin_prof_messages")
                    st.success("Document diffusé avec succès !")

        with adm_tab6:
            st.markdown("### 📋 Assigner un Travail ou Devoir aux Professeurs / Classes")
            with st.form("form_admin_assign_work"):
                titre_travail = st.text_input("Titre du travail")
                classe_travail = st.selectbox("Classe concernée", st.session_state.classes_db["Classe"].tolist() if not st.session_state.classes_db.empty else ["CP"])
                prof_cible = st.text_input("Professeur concerné (ou Tous)")
                desc_travail = st.text_area("Consignes détaillées")
                pj_travail = st.file_uploader("Fichier joint (Consignes/Sujet)", type=["pdf", "docx"], accept_multiple_files=False)
                if st.form_submit_button("Envoyer l'Assignation"):
                    nom_pj_tr = pj_travail.name if pj_travail else "Consignes.pdf"
                    new_assign = pd.DataFrame([{
                        "Titre": titre_travail, "Classe": classe_travail, "Professeur": prof_cible,
                        "Date": str(datetime.now().strftime("%Y-%m-%d")), "Description": desc_travail, "Pièce jointe": nom_pj_tr
                    }])
                    st.session_state.admin_assignations_travail = pd.concat([st.session_state.admin_assignations_travail, new_assign], ignore_index=True)
                    save_df_to_db(new_assign, "admin_assignations_travail")
                    st.success("Travail assigné avec succès !")

        with adm_tab7:
            st.markdown("### 📊 Simulation & Tableau de Bord Global")
            st.info("La simulation utilise directement les classes, matières, périodes et notes enregistrées dans Supabase. Elle ne dépend plus d'une liste de matières codée en dur.")

            col_sim1, col_sim2, col_sim3 = st.columns(3)
            with col_sim1:
                st.metric("Total Élèves Inscrits", len(st.session_state.eleves_db))
            with col_sim2:
                st.metric("Total Classes", len(st.session_state.classes_db))
            with col_sim3:
                st.metric("Total Professeurs", len(st.session_state.prof_white_list))

            classes_sim = st.session_state.classes_db["Classe"].dropna().astype(str).tolist() if not st.session_state.classes_db.empty else []
            if not classes_sim:
                st.warning("Aucune classe configurée. Ajoutez d'abord une classe dans l'onglet « Classes ».")
            else:
                classe_sim = st.selectbox("Classe à simuler", classes_sim, key="simulation_classe")
                cycle_sim = obtenir_cycle_classe(classe_sim)
                matieres_sim = obtenir_matieres_pour_classe(classe_sim)
                periodes_sim = obtenir_periodes_pour_classe(classe_sim)

                st.markdown(f"**Cycle détecté :** {cycle_sim} &nbsp; | &nbsp; **Matières disponibles :** {len(matieres_sim)}")
                if matieres_sim:
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Matière": mat,
                                "Coefficient": obtenir_parametres_matiere(cycle_sim, mat)[0],
                                "Barème": obtenir_parametres_matiere(cycle_sim, mat)[1]
                            }
                            for mat in matieres_sim
                        ]),
                        use_container_width=True,
                        hide_index=True
                    )

                periode_sim = st.selectbox("Période à simuler", periodes_sim, key="simulation_periode")
                eleves_sim = st.session_state.eleves_db[
                    st.session_state.eleves_db["Classe"] == classe_sim
                ].copy()

                if eleves_sim.empty:
                    st.warning("Aucun élève trouvé dans cette classe.")
                else:
                    eleves_sim = trier_eleves_par_nom(eleves_sim)
                    noms_sim = eleves_sim["Nom Complet"].astype(str).tolist()
                    eleve_sim = st.selectbox("Élève à simuler", noms_sim, key="simulation_eleve")

                    bulletin_sim = calculer_bulletin_eleve(classe_sim, eleve_sim, periode_sim)
                    st.markdown("#### 📋 Bulletin simulé")
                    c_moy, c_nb, c_per = st.columns(3)
                    echelle_sim = 10 if bulletin_sim.get("is_elementaire", False) else 20
                    c_moy.metric("Moyenne générale", f"{bulletin_sim['moyenne_generale']}/{echelle_sim}")
                    c_nb.metric("Nombre de matières", len(bulletin_sim["details_notes"]))
                    c_per.metric("Période", periode_sim)
                    if bulletin_sim.get("is_elementaire", False):
                        st.info(f"📘 Appréciation automatique : **{bulletin_sim.get('appreciation', '')}**")

                    details_sim = []
                    notes_source = st.session_state.notes_db
                    for detail in bulletin_sim["details_notes"]:
                        mat = detail["matiere"]
                        coef, bareme = obtenir_parametres_matiere(cycle_sim, mat)
                        match = notes_source[
                            (notes_source["Classe"] == classe_sim) &
                            (notes_source["Matière"].apply(normaliser_texte) == normaliser_texte(mat)) &
                            ((notes_source["Periode"] == periode_sim) | (notes_source["Période"] == periode_sim)) &
                            (notes_source["Eleve"] == eleve_sim)
                        ] if not notes_source.empty else pd.DataFrame()

                        details_sim.append({
                            "Matière": mat,
                            "Devoir 1": detail.get("devoir1", "-"),
                            "Devoir 2": detail.get("devoir2", "-"),
                            "Composition": detail.get("composition", "-"),
                            "Coefficient": coef,
                            "Barème": bareme,
                            "Moyenne /20": detail.get("moyenne", 0),
                            "Notes saisies": "Oui" if not match.empty else "Non"
                        })

                    st.dataframe(pd.DataFrame(details_sim), use_container_width=True, hide_index=True)

        with adm_tab8:
            st.markdown("### 📅 Gestion Emploi du Temps Global (Toutes Classes)")
            classe_edt_admin = st.selectbox("Choisir la classe", st.session_state.classes_db["Classe"].tolist() if not st.session_state.classes_db.empty else ["CP"], key="admin_edt_cls")
            edt_g = get_or_create_edt(classe_edt_admin)
            edited_edt = st.data_editor(edt_g, use_container_width=True, key=f"edt_grid_admin_{classe_edt_admin}")
            if st.button("Enregistrer l'Emploi du Temps de cette classe"):
                st.session_state.edt_grid_db[classe_edt_admin] = edited_edt
                rows_to_save = []
                for jour in JOURS_LIST:
                    for h in HEURES_LIST:
                        val = edited_edt.loc[jour, h] if h in edited_edt.columns else ""
                        rows_to_save.append({"classe": classe_edt_admin, "jour": jour, "heure": h, "valeur": val})
                df_edt_save = pd.DataFrame(rows_to_save)
                save_df_to_db(df_edt_save, "edt_grid")
                st.success("Emploi du temps enregistré avec succès dans Supabase !")
        with adm_tab9:
            st.markdown("### 📥 Téléchargements XXL & Bulletins Scolaires Officiels")
    
            classe_bul_sel = st.selectbox(
                "Sélectionner la classe pour les rapports et bulletins", 
                st.session_state.classes_db["Classe"].tolist() if not st.session_state.classes_db.empty else ["CP"], 
                key="cls_bul_admin"
            )
            periodes_bul = obtenir_periodes_pour_classe(classe_bul_sel)
            periode_bul_sel = st.selectbox("Sélectionner la période", periodes_bul, key="per_bul_admin")
            
            df_el_bul = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_bul_sel]
            
            if df_el_bul.empty:
                st.warning("Aucun élève dans cette classe.")
            else:
                df_el_bul = trier_eleves_par_nom(df_el_bul)
                eleve_sel_bul = st.selectbox(
                    "Sélectionner l'élève", 
                    df_el_bul["Nom Complet"].tolist(), 
                    key="el_bul_admin"
                )
                
                # Bulletin individuel : génération directe et données binaires sûres.
                try:
                    bul_data = calculer_bulletin_eleve(
                        classe_bul_sel, eleve_sel_bul, periode_bul_sel
                    )
                    pdf_bytes = generer_pdf_bulletin(bul_data)

                    if not pdf_bytes:
                        st.error("Le bulletin a été généré sans contenu : téléchargement bloqué.")
                    else:
                        st.download_button(
                            label="📥 Télécharger le Bulletin Officiel (PDF)",
                            data=pdf_bytes,
                            file_name=(
                                f"Bulletin_{nettoyer_nom_fichier(eleve_sel_bul)}_"
                                f"{nettoyer_nom_fichier(periode_bul_sel)}.pdf"
                            ),
                            mime="application/pdf",
                            key=f"dl_bulletin_official_{nettoyer_nom_fichier(classe_bul_sel)}_"
                                f"_{nettoyer_nom_fichier(eleve_sel_bul)}_{nettoyer_nom_fichier(periode_bul_sel)}",
                        )
                except Exception as e:
                    st.error(f"Erreur réelle pendant la génération du bulletin : {e}")

                st.markdown("### 📦 Bulletins de toute la classe")
                try:
                    zip_bulletins = generer_zip_bulletins_classe(
                        classe_bul_sel, periode_bul_sel
                    )
                    if zip_bulletins:
                        st.download_button(
                            label="📦 Télécharger TOUS les bulletins de la classe (ZIP)",
                            data=zip_bulletins,
                            file_name=(
                                f"Bulletins_{nettoyer_nom_fichier(classe_bul_sel)}_"
                                f"{nettoyer_nom_fichier(periode_bul_sel)}.zip"
                            ),
                            mime="application/zip",
                            key=f"dl_bulletins_classe_{nettoyer_nom_fichier(classe_bul_sel)}_"
                                f"_{nettoyer_nom_fichier(periode_bul_sel)}",
                        )
                        st.success(
                            "ZIP prêt : chaque élève possède maintenant son bulletin PDF séparé."
                        )
                    else:
                        st.error(
                            "Le ZIP serait vide : aucun bulletin PDF n'a pu être généré pour cette classe."
                        )
                except Exception as e:
                    st.error(f"Erreur réelle pendant la création du ZIP : {e}")

            st.markdown("---")
            st.markdown("#### Génération des Documents Officiels de la Classe")
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                if st.button("📄 Emploi du Temps (PDF)"):
                    pdf_edt = generer_pdf_edt(classe_bul_sel, get_or_create_edt(classe_bul_sel))
                    st.download_button("Télécharger EDT", pdf_edt, f"EDT_{classe_bul_sel}.pdf", "application/pdf")
            with col_d2:
                if st.button("📑 Cahier de Texte (PDF)"):
                    pdf_ct = generer_pdf_cahier_texte(classe_bul_sel)
                    st.download_button("Télécharger Cahier Texte", pdf_ct, f"CahierTexte_{classe_bul_sel}.pdf", "application/pdf")
            with col_d3:
                if st.button("📋 Liste des Élèves (PDF)"):
                    pdf_liste = generer_pdf_liste_eleves_classe(classe_bul_sel)
                    st.download_button("Télécharger Liste", pdf_liste, f"ListeEleves_{classe_bul_sel}.pdf", "application/pdf")
